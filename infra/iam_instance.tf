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

# Backups: write and read, but NOT delete.
#
# This is the whole point of the instance having a role rather than a stored key,
# and the permission set is deliberately asymmetric. If the box is compromised,
# the attacker already has the live database — reading the backups tells them
# nothing new. What they must not be able to do is destroy the only off-machine
# copy, so s3:DeleteObject and s3:DeleteObjectVersion are withheld, and bucket
# versioning (backups.tf) means even an overwrite leaves the older object intact.
#
# Retention still happens: the bucket's own lifecycle rule expires old dumps,
# and a lifecycle rule is evaluated by S3 itself, so it works without granting
# anyone delete rights and a compromised instance cannot switch it off.
resource "aws_iam_role_policy" "backups" {
  name = "carpool-backups-write"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:AbortMultipartUpload",
        ]
        Resource = "${aws_s3_bucket.backups.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = aws_s3_bucket.backups.arn
      },
    ]
  })
}
