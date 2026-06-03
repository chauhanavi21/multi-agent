output "app_public_ip" {
  description = "EC2 public IP — point your DNS A record here, or use directly"
  value       = aws_instance.app.public_ip
}

output "app_public_dns" {
  description = "EC2 public DNS"
  value       = aws_instance.app.public_dns
}

output "db_endpoint" {
  description = "Postgres host (private; only reachable from EC2 SG)"
  value       = aws_db_instance.app.address
}

output "frontend_bucket" {
  description = "S3 bucket for the React build"
  value       = aws_s3_bucket.frontend.bucket
}

output "frontend_website_url" {
  description = "Direct S3 website URL (HTTP only; use Caddy on EC2 for HTTPS)"
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

output "backups_bucket" {
  description = "S3 bucket for pg_dump backups"
  value       = aws_s3_bucket.backups.bucket
}

output "ssh_command" {
  description = "SSH into the app box"
  value       = "ssh ubuntu@${aws_instance.app.public_ip}"
}

output "estimated_monthly_cost_after_free_tier" {
  description = "Rough estimate AFTER the 12mo free tier expires"
  value       = "EC2 ~$8 + RDS ~$15 + S3 ~$0.50 + Bedrock = $24/mo + inference"
}
