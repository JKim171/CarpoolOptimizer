# How GitHub Actions deploys without an AWS key existing anywhere.
#
# The workflow presents a short-lived OIDC token that GitHub signs and AWS
# verifies, and exchanges it for temporary credentials. There is nothing to
# store in the repository, which matters doubly because the repository is
# public (design §10.1).

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # Empty because AWS trusts this endpoint natively and no longer verifies
  # thumbprints for it. AWS then populates one of its own, which Terraform would
  # otherwise propose removing on every single plan from now on — and a
  # configuration that always shows a diff is one where real drift goes unread.
  # Hardcoding the current value instead is the trap old tutorials fall into:
  # thumbprints rotate, and a stale one breaks deploys.
  thumbprint_list = []

  lifecycle {
    ignore_changes = [thumbprint_list]
  }
}

# The trust policy is the security boundary, and the `sub` condition is the
# load-bearing line. Without it, ANY GitHub repository in the world could
# present a valid token for this provider and assume this role — the single
# most common way OIDC setups are catastrophically misconfigured.
#
# Scoped to this repository AND to its main branch: a pull request from a fork,
# which runs workflow code a stranger wrote, gets a token whose sub does not
# match and therefore cannot deploy.
data "aws_iam_policy_document" "deploy_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/${var.deploy_branch}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "carpool-deploy"
  description        = "Assumed by GitHub Actions via OIDC. May send one SSM document to one instance."
  assume_role_policy = data.aws_iam_policy_document.deploy_trust.json

  # A deploy is minutes, not hours. The token is exchanged per run.
  max_session_duration = 3600
}

# What the role may do, which is deliberately almost nothing.
#
# AWS's stock AWS-RunShellScript runs arbitrary commands as root, so a role
# allowed to send it is effectively root on the instance. This role may send
# exactly one document, to exactly one instance. A compromised workflow can at
# worst deploy another build of this repository (design §10.1).
data "aws_iam_policy_document" "deploy" {
  statement {
    sid     = "SendOnlyTheDeployDocument"
    effect  = "Allow"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_ssm_document.deploy.arn,
      "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/${aws_instance.app.id}",
    ]
  }

  # CI waits for the command's exit status so a failed deploy fails the
  # workflow. These actions carry no resource-level permissions in IAM, so "*"
  # is not laziness — there is no ARN to name. They are read-only.
  statement {
    sid    = "ReadCommandResult"
    effect = "Allow"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
      "ssm:ListCommands",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "carpool-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

# The one thing the deploy role may run.
#
# ImageTag is interpolated into a shell command, so allowedPattern is not
# cosmetic validation — it is what stops a tag like `abc; rm -rf /` from
# becoming a shell injection with root on the instance. Forty hex characters is
# exactly a git commit SHA and nothing else.
resource "aws_ssm_document" "deploy" {
  name            = "carpool-deploy"
  document_type   = "Command"
  document_format = "YAML"

  content = yamlencode({
    schemaVersion = "2.2"
    description   = "Pull the image for one commit SHA, migrate, and restart the app."
    parameters = {
      ImageTag = {
        type           = "String"
        description    = "Git commit SHA of the image to deploy."
        allowedPattern = "^[0-9a-f]{40}$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "deploy"
      inputs = {
        timeoutSeconds = "600"
        runCommand = [
          "set -euo pipefail",
          "cd ${var.app_dir}",
          "export IMAGE_TAG='{{ ImageTag }}'",
          "docker compose pull api worker",
          "docker compose run --rm api alembic -c apps/api/alembic.ini upgrade head",
          "docker compose up -d --no-deps api worker",
          "docker image prune -f",
        ]
      }
    }]
  })

  tags = {
    Name = "carpool-deploy"
  }
}
