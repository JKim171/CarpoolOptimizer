# One VPC, one public subnet, an internet gateway, and a route to it.
#
# There is deliberately no NAT gateway (~$32/month) and no private subnet. The
# only instance sits in the public subnet with a public IP, which is what lets
# it reach SSM, GHCR, ORS and S3 over the internet gateway at no hourly cost.
# The instance is not protected by being unroutable — it is protected by a
# security group that opens 80/443 only, and by having no SSH port at all.

resource "aws_vpc" "main" {
  cidr_block = var.vpc_cidr

  # Both are required for the instance to resolve the S3, SSM and ECR endpoints
  # it talks to, and for SSM to register it by hostname.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "carpool"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "carpool"
  }
}

# A single AZ on purpose. This is one instance with local Postgres on its own
# EBS volume; spreading subnets across AZs would suggest a redundancy the design
# does not have and cannot have while the database lives on the box.
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true

  tags = {
    Name = "carpool-public"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "carpool-public"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
