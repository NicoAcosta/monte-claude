variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "domain_name" {
  description = "Domain name for the service (leave empty to use ALB DNS)"
  type        = string
  default     = ""
}

# --- EC2 ---

variable "game_api_instance_type" {
  description = "EC2 instance type for Game API (must support Nitro Enclaves)"
  type        = string
  default     = "c6a.xlarge"
}

variable "data_api_instance_type" {
  description = "EC2 instance type for Data API"
  type        = string
  default     = "t3.medium"
}

variable "nat_instance_type" {
  description = "EC2 instance type for NAT instance"
  type        = string
  default     = "t3.nano"
}

variable "ssh_key_name" {
  description = "Name of existing EC2 key pair for SSH access (optional, SSM preferred)"
  type        = string
  default     = ""
}

# --- RDS ---

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "RDS storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "monteclaude"
}

# --- Escrow / Chain ---

variable "server_private_key" {
  description = "Hex private key for admin EOA (escrow signing)"
  type        = string
  sensitive   = true
}

variable "base_rpc_url" {
  description = "Base chain RPC endpoint"
  type        = string
}

variable "factory_address" {
  description = "Deployed EscrowFactory contract address"
  type        = string
}

variable "rake_bps" {
  description = "Rake in basis points"
  type        = string
  default     = "250"
}

variable "rake_beneficiary" {
  description = "Address for rake payouts"
  type        = string
  default     = ""
}

variable "chain_id" {
  description = "Chain ID for EIP-712"
  type        = string
  default     = "8453"
}

# --- Nitro Enclave ---

variable "enclave_enabled" {
  description = "Enable Nitro Enclave mode for Game API (KMS key, enclave user data)"
  type        = bool
  default     = false
}

variable "enclave_pcr0" {
  description = "PCR-0 value of the enclave image (required when enclave_enabled=true)"
  type        = string
  default     = ""
}

# --- WAF ---

variable "waf_rate_limit" {
  description = "Max requests per 5-minute window per IP"
  type        = number
  default     = 2000
}
