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
