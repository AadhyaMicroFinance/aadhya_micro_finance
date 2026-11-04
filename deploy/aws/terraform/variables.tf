variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Short name used for AWS resource names."
  type        = string
  default     = "finance-chitti"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.project_name))
    error_message = "Use 3-31 lowercase letters, digits or hyphens."
  }
}

variable "environment" {
  description = "Environment label for tags."
  type        = string
  default     = "production"
}

variable "instance_type" {
  description = "EC2 size. t3.medium (2 vCPU / 4 GB) runs the whole stack."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_gb" {
  description = "Encrypted gp3 root volume size."
  type        = number
  default     = 40
}

variable "ssh_public_key_path" {
  description = "Public key registered with EC2 (deploy.sh generates it if missing)."
  type        = string
  default     = "~/.ssh/finance-chitti-aws.pub"
}

variable "admin_cidr" {
  description = "CIDR allowed to SSH (e.g. 203.0.113.4/32). Empty = no SSH ingress; use SSM instead."
  type        = string
  default     = ""
}

variable "public_http_cidrs" {
  description = "CIDRs allowed to reach ports 80/443."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "backup_retention_days" {
  description = "Days to keep database dumps in S3."
  type        = number
  default     = 30
}
