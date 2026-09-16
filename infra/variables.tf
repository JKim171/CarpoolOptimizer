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
