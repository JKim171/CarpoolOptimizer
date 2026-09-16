# The nightly pg_dump destination. Self-hosted Postgres on the instance's own
# EBS volume means this is the ONLY off-machine copy of the database (trap 16),
# so the properties that matter here are durability and the instance's inability
# to destroy it.
#
# Unlike the state bucket, this one is Terraform-managed. The state bucket is
# hand-made only because Terraform cannot create the bucket holding its own
# state; that exception does not extend to anything else.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "backups" {
  # S3 bucket names are globally unique across all of AWS, so the account id is
  # the suffix that makes this one available. Account ids are not secret.
  bucket = "carpool-backups-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "carpool-backups"
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket = aws_s3_bucket.backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning is what turns "the instance cannot delete backups" into a real
# guarantee: without it, an overwrite of yesterday's key would destroy the older
# object even with s3:DeleteObject withheld.
resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3, not a customer-managed KMS key — free, and the same call made for the
# state bucket and against Multi-Region Identity Center.
resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-old-dumps"
    status = "Enabled"

    filter {}

    # How far back a restore can reach. Dumps of this database are KB-to-low-MB,
    # so a longer window costs pennies a year; the limit is about the bucket not
    # growing forever unwatched rather than about money.
    expiration {
      days = var.backup_retention_days
    }

    # A dump overwritten in place (a re-run on the same night) leaves the old one
    # as a noncurrent version. Those are the copies nobody is tracking.
    noncurrent_version_expiration {
      noncurrent_days           = 30
      newer_noncurrent_versions = 5
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  # Sweeping delete markers has to be its own rule: S3 allows one expiration
  # block per rule, and rejects expired_object_delete_marker combined with days.
  # Without this, expiring a dump leaves a tombstone behind forever.
  rule {
    id     = "sweep-delete-markers"
    status = "Enabled"

    filter {}

    expiration {
      expired_object_delete_marker = true
    }
  }

  depends_on = [aws_s3_bucket_versioning.backups]
}

# Same hardening as the state bucket: refuse anything that did not arrive over
# TLS. The SDK already uses HTTPS, so this enforces what is already true.
resource "aws_s3_bucket_policy" "backups" {
  bucket = aws_s3_bucket.backups.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.backups.arn,
        "${aws_s3_bucket.backups.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })

  # A public-access-block change racing a policy put is a common source of
  # confusing failures; make the ordering explicit.
  depends_on = [aws_s3_bucket_public_access_block.backups]
}
