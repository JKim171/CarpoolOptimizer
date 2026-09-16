# Resolved at apply time so that building from nothing always gets a current,
# patched AMI. Note the namespace is ami-amazon-linux-latest — there is no
# ami-al2023-latest, and asking for one fails with a confusing "not a valid
# namespace" error rather than a not-found.
data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "app" {
  # nonsensitive() because aws_ssm_parameter always marks `value` sensitive —
  # parameters *can* be SecureString — and that would otherwise propagate to
  # aws_instance.ami and to any output reading it. A public AMI id is not a
  # secret. Do not copy this to a parameter that actually holds one.
  ami           = nonsensitive(data.aws_ssm_parameter.al2023_arm64.value)
  instance_type = var.instance_type

  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  # IMDSv2 required. The instance role's credentials are served by the metadata
  # endpoint, and IMDSv1's unauthenticated GET is the classic path from an SSRF
  # bug in the app to those credentials.
  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  # standard, not the burstable default. Under `unlimited` a sustained burst
  # silently buys surplus credits and shows up as a surprise line on the bill;
  # under `standard` it throttles to baseline instead. For a box that is idle
  # almost always and solves in bursts of seconds (design §10.1), a visible
  # slowdown is the better failure than an invisible charge. Setting it
  # explicitly also means the AWS default does not matter.
  credit_specification {
    cpu_credits = "standard"
  }

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true

    tags = {
      Name = "carpool-root"
    }
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    swap_size_mb    = var.swap_size_mb
    compose_version = var.compose_version
  })

  lifecycle {
    # Without this, every plan after AWS publishes a new AL2023 image would
    # propose destroying and recreating the instance — and the root volume holds
    # Postgres. An OS upgrade must be a deliberate act (terraform apply
    # -replace=aws_instance.app), taken with a fresh backup in hand, not
    # something a routine plan offers to do in passing. Same reasoning as the
    # hardcoded availability zone.
    ignore_changes = [ami]
  }

  tags = {
    Name = "carpool"
  }
}

# A stable address. AWS bills every public IPv4 attached to a running instance
# at the same rate whether it is auto-assigned or elastic, so this costs nothing
# extra while the box is up — and an auto-assigned IP changes on every stop/start,
# which would break DNS the first time the instance is ever stopped.
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = {
    Name = "carpool"
  }

  depends_on = [aws_internet_gateway.main]
}
