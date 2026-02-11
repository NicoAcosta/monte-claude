# ---------- VPC ----------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "monteclaude-${var.environment}"
  cidr = var.vpc_cidr

  azs              = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnets   = [cidrsubnet(var.vpc_cidr, 8, 1), cidrsubnet(var.vpc_cidr, 8, 2)]
  private_subnets  = [cidrsubnet(var.vpc_cidr, 8, 10), cidrsubnet(var.vpc_cidr, 8, 11)]
  database_subnets = [cidrsubnet(var.vpc_cidr, 8, 20), cidrsubnet(var.vpc_cidr, 8, 21)]

  # NAT is handled by a t3.nano instance (see below), not a managed NAT Gateway.
  enable_nat_gateway = false

  create_database_subnet_group       = true
  create_database_subnet_route_table = true

  enable_dns_hostnames = true
  enable_dns_support   = true
}

# ---------- NAT instance (t3.nano, ~$4/mo vs $35/mo NAT Gateway) ----------

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "nat" {
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = var.nat_instance_type
  subnet_id                   = module.vpc.public_subnets[0]
  associate_public_ip_address = true
  source_dest_check           = false
  vpc_security_group_ids      = [aws_security_group.nat.id]

  user_data = <<-EOF
    #!/bin/bash
    set -e
    echo 1 > /proc/sys/net/ipv4/ip_forward
    echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
    dnf install -y iptables-services
    iptables -t nat -A POSTROUTING -o ens5 -j MASQUERADE
    iptables -A FORWARD -i ens5 -o ens5 -m state --state RELATED,ESTABLISHED -j ACCEPT
    iptables -A FORWARD -i ens5 -o ens5 -j ACCEPT
    service iptables save
    systemctl enable iptables
  EOF

  tags = { Name = "monteclaude-nat-${var.environment}" }
}

resource "aws_security_group" "nat" {
  name_prefix = "monteclaude-nat-"
  description = "NAT instance - allows outbound for private subnets"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "All traffic from private subnets"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Route private subnet traffic through NAT instance
resource "aws_route" "private_nat" {
  count                  = length(module.vpc.private_route_table_ids)
  route_table_id         = module.vpc.private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_instance.nat.primary_network_interface_id
}
