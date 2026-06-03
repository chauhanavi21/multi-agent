resource "aws_key_pair" "main" {
  key_name   = "${var.project}-key"
  public_key = file(pathexpand(var.public_key_path))
}

resource "aws_security_group" "ec2" {
  name        = "${var.project}-ec2"
  description = "Sales Agent EC2 — SSH, HTTP, HTTPS"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_cidr]
  }

  ingress {
    description = "HTTP (Caddy redirects to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-ec2-sg" }
}

# Latest Ubuntu 24.04 LTS AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "app" {
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = var.instance_type
  key_name             = aws_key_pair.main.key_name
  subnet_id            = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile = aws_iam_instance_profile.app.name

  root_block_device {
    volume_size = 20      # GB; free tier is 30GB
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    region              = var.region
    db_endpoint         = aws_db_instance.app.address
    db_name             = aws_db_instance.app.db_name
    db_username         = var.db_username
    ssm_db_password     = aws_ssm_parameter.db_password.name
    ssm_jwt_secret      = aws_ssm_parameter.jwt_secret.name
    ssm_anthropic_key   = aws_ssm_parameter.anthropic_api_key.name
    ssm_admin_password  = aws_ssm_parameter.admin_password.name
    admin_email         = var.bootstrap_admin_email
    frontend_bucket     = aws_s3_bucket.frontend.bucket
    tailscale_auth_key  = var.tailscale_auth_key
  })
  # Re-run user_data when the script changes (does NOT recreate the instance)
  user_data_replace_on_change = false

  tags = { Name = "${var.project}-app" }

  depends_on = [
    aws_db_instance.app,
    aws_ssm_parameter.db_password,
    aws_ssm_parameter.jwt_secret,
    aws_ssm_parameter.anthropic_api_key,
    aws_ssm_parameter.admin_password,
  ]
}
