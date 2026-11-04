output "public_ip" {
  description = "Elastic IP of the app host."
  value       = aws_eip.app.public_ip
}

output "app_url" {
  description = "Open this in a browser (http until a domain + TLS are added)."
  value       = "http://${aws_eip.app.public_ip}"
}

output "instance_id" {
  description = "EC2 instance id (use with SSM Session Manager)."
  value       = aws_instance.app.id
}

output "ssh_command" {
  description = "SSH command, when admin_cidr is set."
  value       = "ssh -i ~/.ssh/finance-chitti-aws ec2-user@${aws_eip.app.public_ip}"
}

output "backup_bucket" {
  description = "S3 bucket for nightly Postgres dumps."
  value       = aws_s3_bucket.backup.bucket
}

output "ssm_start_session" {
  description = "Shell access without SSH."
  value       = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.aws_region}"
}
