resource "random_password" "jwt_secret" {
  length  = 48
  special = true
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.project}/db_password"
  type  = "SecureString"
  value = random_password.db.result
}

resource "aws_ssm_parameter" "jwt_secret" {
  name  = "/${var.project}/jwt_secret"
  type  = "SecureString"
  value = random_password.jwt_secret.result
}

resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/${var.project}/anthropic_api_key"
  type  = "SecureString"
  value = coalesce(var.anthropic_api_key, "unset")
}

resource "aws_ssm_parameter" "admin_password" {
  name  = "/${var.project}/admin_password"
  type  = "SecureString"
  value = var.bootstrap_admin_password
}
