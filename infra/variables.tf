variable "region" {
  description = "AWS region for every resource. Matches the Identity Center home region."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = <<-EOT
    The single AZ everything lives in. Hardcoded rather than read from
    aws_availability_zones so that a re-plan can never quietly propose moving
    the subnet — and with it the instance and its EBS volume — to a different AZ.
  EOT
  type        = string
  default     = "us-east-1a"
}

variable "vpc_cidr" {
  description = "CIDR for the VPC. Private range; nothing peers with this, so the choice is free."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the one public subnet. Must sit inside var.vpc_cidr."
  type        = string
  default     = "10.0.1.0/24"
}

variable "instance_type" {
  description = <<-EOT
    Graviton/arm64, matching the Apple Silicon dev machine so images run natively
    in both places. Burstable suits a box that is idle almost always and solves
    in bursts of seconds. ~$12.26/month on-demand in us-east-1.
  EOT
  type        = string
  default     = "t4g.small"
}

variable "root_volume_gb" {
  description = "Root EBS volume in GB. 20 GB gp3 is ~$1.60/month (design §10.1)."
  type        = number
  default     = 20
}

variable "swap_size_mb" {
  description = "Swap file size. 2 GB against 2 GB of RAM, as the margin design §10.1 calls for."
  type        = number
  default     = 2048
}

variable "cpu_credit_alarm_threshold" {
  description = <<-EOT
    Warn below this many CPU credits. A t4g.small accrues 24/hour and caps at
    576, so 50 is roughly two hours of accrual left - early enough to look at
    what is burning them before the box throttles to baseline.
  EOT
  type        = number
  default     = 50
}

variable "github_repository" {
  description = <<-EOT
    owner/repo exactly as GitHub spells it, including case. This is half of the
    OIDC trust boundary: it is what stops any other repository's workflow from
    assuming the deploy role.
  EOT
  type        = string
  default     = "JKim171/CarpoolOptimizer"
}

variable "deploy_branch" {
  description = <<-EOT
    The only branch whose workflows may deploy. Scoping the OIDC subject to a
    branch means a pull request from a fork - workflow code a stranger wrote -
    gets a token that does not match and cannot deploy.
  EOT
  type        = string
  default     = "main"
}

variable "app_dir" {
  description = "Where the compose project lives on the instance."
  type        = string
  default     = "/opt/carpool"
}

variable "backup_retention_days" {
  description = <<-EOT
    How far back a restore can reach. Dumps are KB-to-low-MB, so this is a
    recoverability decision rather than a cost one: the window has to outlast
    the time it might take to notice a corruption that happened quietly.
  EOT
  type        = number
  default     = 90
}

variable "compose_version" {
  description = "Pinned Docker Compose CLI plugin release tag, fetched at first boot."
  type        = string
  default     = "v5.5.1"
}
