# Container registry for the app image. (You can also keep using GHCR from CI;
# ECR is the native choice when the cluster is on AWS — nodes pull it via their
# IAM role with no imagePullSecret.)
resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}
