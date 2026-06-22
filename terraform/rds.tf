# Managed Postgres (replaces the in-cluster postgres pod). RDS Postgres 16
# supports pgvector — after creation, connect once and run:
#     CREATE EXTENSION IF NOT EXISTS vector;
# then apply migrations/001_init.sql.
resource "aws_db_subnet_group" "pg" {
  name       = "${var.project}-pg"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name   = "${var.project}-rds"
  vpc_id = module.vpc.vpc_id

  ingress {
    description = "Postgres from within the VPC (EKS nodes)"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.project}-pg"
  engine                 = "postgres"
  engine_version         = "16.4"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  storage_encrypted      = true
  db_name                = "lumina"
  username               = "lumina"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.pg.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az               = false # set true for HA in prod
  skip_final_snapshot    = true  # set false in prod
}
