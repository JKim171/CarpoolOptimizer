# 80 and 443 in, everything out. There is no port 22 and no SSH key anywhere in
# this configuration — shell access is SSM Session Manager, authenticated by IAM
# (design §10.1). If a rule for 22 ever appears here, something has gone wrong.

resource "aws_security_group" "app" {
  name        = "carpool-app"
  description = "Caddy on 80/443; no SSH. Shell access is via SSM."
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "carpool-app"
  }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.app.id
  # AWS restricts rule descriptions to a-zA-Z0-9 and a fixed punctuation set;
  # an em dash here fails the apply with InvalidParameterValue.
  description       = "HTTP: Caddy redirects to HTTPS and serves ACME challenges"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# Egress stays open. The instance has to reach SSM (which is what makes the
# absence of an inbound shell port workable), GHCR for images, ORS for routing,
# S3 for backups, and the package mirrors. Narrowing this to prefix lists would
# buy little and break quietly.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  description       = "All outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
