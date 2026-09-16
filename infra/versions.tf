terraform {
  # 1.10 is the floor: it is the release that locks state natively in S3 via
  # use_lockfile, which is why this configuration has no DynamoDB lock table.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # The bucket is created by hand, outside this configuration, and deliberately
  # stays unmanaged by it: Terraform cannot create the bucket that holds its own
  # state, and a managed bucket would put `terraform destroy` in a position to
  # delete the record of everything it is destroying.
  #
  # Backend blocks take literals only — no variables, no locals.
  backend "s3" {
    bucket       = "carpool-tfstate-238971168139"
    key          = "infra/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
