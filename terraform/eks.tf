# The EKS cluster that replaces the local kind cluster. Same manifests (k8s/)
# deploy here unchanged — that's the payoff of doing it on kind first.
#
# Node sizing: t3.large (2 vCPU / 8GB) because the API pod loads torch
# (embedder + reranker). Generation no longer runs on a host GPU here — switch
# LLM_BASE_URL to Amazon Bedrock or another cloud LLM (the generator is
# OpenAI-compatible, so it's a config change, not code).
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.project
  cluster_version = "1.31"

  cluster_endpoint_public_access = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.large"]
      min_size       = 2
      max_size       = 5
      desired_size   = 2
    }
  }
}
