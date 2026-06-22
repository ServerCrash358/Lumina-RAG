# Network foundation: a VPC with public + private subnets across two AZs.
# EKS nodes, RDS, and ElastiCache all live in the PRIVATE subnets; only the
# load balancer sits in public. A single NAT gateway keeps cost down (use one
# per-AZ for real HA).
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project}-vpc"
  cidr = var.vpc_cidr
  azs  = ["${var.region}a", "${var.region}b"]

  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true

  # Tags the EKS load-balancer controller looks for.
  public_subnet_tags  = { "kubernetes.io/role/elb" = "1" }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = "1" }
}
