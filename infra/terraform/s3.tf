resource "random_string" "bucket_suffix" {
  length  = 8
  upper   = false
  special = false
}

locals {
  frontend_bucket_name = "${var.project}-frontend-${coalesce(var.frontend_bucket_suffix, random_string.bucket_suffix.result)}"
}

resource "aws_s3_bucket" "frontend" {
  bucket        = local.frontend_bucket_name
  force_destroy = true
  tags          = { Name = "${var.project}-frontend" }
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  index_document { suffix = "index.html" }
  error_document { key = "index.html" } # SPA fallback
}

# Required to disable account-level "block public access" effects on this bucket
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "frontend_public" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicRead"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

# Backup bucket for pg_dump snapshots
resource "aws_s3_bucket" "backups" {
  bucket        = "${var.project}-backups-${coalesce(var.frontend_bucket_suffix, random_string.bucket_suffix.result)}"
  force_destroy = true
  tags          = { Name = "${var.project}-backups" }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    id     = "purge-old-backups"
    status = "Enabled"
    filter {}
    expiration { days = 30 }
  }
}
