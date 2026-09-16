output "vpc_id" {
  description = "VPC id, for console lookups and for confirming what a plan is about to change."
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "The one public subnet the instance will launch into."
  value       = aws_subnet.public.id
}

output "instance_id" {
  description = "Instance id — the argument to `aws ssm start-session --target`."
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Stable Elastic IP. This is what an A record will eventually point at."
  value       = aws_eip.app.public_ip
}

output "backup_bucket" {
  description = "Nightly pg_dump destination. The only off-machine copy of the database."
  value       = aws_s3_bucket.backups.bucket
}

output "deploy_role_arn" {
  description = "Role the GitHub Actions workflow assumes via OIDC. Not a secret; it is an ARN."
  value       = aws_iam_role.deploy.arn
}

output "deploy_document_name" {
  description = "The only SSM document the deploy role may send."
  value       = aws_ssm_document.deploy.name
}

output "alerts_topic_arn" {
  description = <<-EOT
    Alarm destination. Nothing is subscribed by Terraform: subscribe an address
    by hand so it never enters this public repository, then confirm the email.
  EOT
  value       = aws_sns_topic.alerts.arn
}

output "ami_id" {
  description = <<-EOT
    The AMI actually in use. Worth an output because aws_instance.ami is
    lifecycle-ignored, so this is the only convenient way to see how far behind
    the current AL2023 image the running box has drifted.
  EOT
  value       = aws_instance.app.ami
}
