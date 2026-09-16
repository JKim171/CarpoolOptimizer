output "vpc_id" {
  description = "VPC id, for console lookups and for confirming what a plan is about to change."
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "The one public subnet the instance will launch into."
  value       = aws_subnet.public.id
}
