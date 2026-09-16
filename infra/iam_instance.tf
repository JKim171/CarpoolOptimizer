# The instance's own identity. It exists in this slice rather than the next one
# because without it there is no SSM agent registration, and therefore no shell —
# the box would boot unreachable, since there is no SSH port to fall back on.
#
# This is the SSM minimum only. The S3 backup policy belongs with the backup
# bucket in the next slice, so the role starts with exactly what makes the
# instance reachable and gains permissions as things exist for it to reach.

resource "aws_iam_role" "instance" {
  name        = "carpool-instance"
  description = "Instance role: SSM registration. No long-lived credentials on the box."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# AWS-managed, and the right call here: it is the documented minimum for Session
# Manager and AWS keeps it correct as SSM's own API surface changes. Hand-rolling
# an equivalent would be a policy to maintain forever for no security gain.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "instance" {
  name = "carpool-instance"
  role = aws_iam_role.instance.name
}
