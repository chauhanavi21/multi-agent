resource "aws_db_subnet_group" "app" {
  name       = "${var.project}-db-subnets"
  subnet_ids = aws_subnet.public[*].id
  tags       = { Name = "${var.project}-db-subnets" }
}

resource "aws_security_group" "db" {
  name        = "${var.project}-db"
  description = "Postgres — accessible only from the EC2 SG"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from app"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-db-sg" }
}

resource "random_password" "db" {
  length  = 28
  special = false   # avoids URL-encoding headaches in the DATABASE_URL
}

resource "aws_db_instance" "app" {
  identifier             = "${var.project}-db"
  engine                 = "postgres"
  engine_version         = "16.4"
  instance_class         = var.db_instance_type
  allocated_storage      = 20         # free tier: up to 20GB
  storage_type           = "gp2"
  storage_encrypted      = true
  db_name                = "salesagent"
  username               = var.db_username
  password               = random_password.db.result
  db_subnet_group_name   = aws_db_subnet_group.app.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  skip_final_snapshot    = true       # set to false in real prod
  backup_retention_period = 7
  apply_immediately      = true
  deletion_protection    = false      # set true in real prod
  tags = { Name = "${var.project}-db" }
}
