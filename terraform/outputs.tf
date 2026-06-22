output "cluster_name" {
  description = "EKS cluster name (use: aws eks update-kubeconfig --name <this>)"
  value       = module.eks.cluster_name
}

output "rds_endpoint" {
  description = "Postgres host — put in the app's DATABASE_URL"
  value       = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  description = "Redis host — put in the app's REDIS_URL"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "ecr_repository_url" {
  description = "Push the app image here"
  value       = aws_ecr_repository.api.repository_url
}
