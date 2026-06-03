data "aws_caller_identity" "current" {}

resource "aws_iam_role" "app" {
  name = "${var.project}-app-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.project}-app-profile"
  role = aws_iam_role.app.name
}

# Bedrock — invoke any anthropic model in this region
resource "aws_iam_policy" "bedrock" {
  name = "${var.project}-bedrock"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream",
      ]
      Resource = "arn:aws:bedrock:${var.region}::foundation-model/anthropic.*"
    }]
  })
}

# SSM — read parameters under our path
resource "aws_iam_policy" "ssm_read" {
  name = "${var.project}-ssm-read"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath",
      ]
      Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project}/*"
    }]
  })
}

# S3 — read frontend bucket, read+write backups bucket
resource "aws_iam_policy" "s3_app" {
  name = "${var.project}-s3"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.frontend.arn,
          "${aws_s3_bucket.frontend.arn}/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.backups.arn,
          "${aws_s3_bucket.backups.arn}/*",
        ]
      }
    ]
  })
}

# CloudWatch logs — already in AmazonSSMManagedInstanceCore, but explicit here
resource "aws_iam_role_policy_attachment" "ssm_managed" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_role_policy_attachment" "bedrock" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.bedrock.arn
}

resource "aws_iam_role_policy_attachment" "ssm_read" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.ssm_read.arn
}

resource "aws_iam_role_policy_attachment" "s3_app" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.s3_app.arn
}
