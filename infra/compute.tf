resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_secretsmanager_secret" "planet_api_key" {
  count       = var.planet_api_key_secret_arn == "" ? 1 : 0
  name        = "${var.name}/planet-api-key"
  description = "Planet API key used by the tile pipeline. Set the value with: aws secretsmanager put-secret-value"
}

locals {
  planet_secret_arn = var.planet_api_key_secret_arn != "" ? var.planet_api_key_secret_arn : aws_secretsmanager_secret.planet_api_key[0].arn

  container_environment = merge(
    {
      TILE_BUCKET  = aws_s3_bucket.tiles.bucket
      AOI_KEY      = var.aoi_key
      STATE_KEY    = var.state_key
      TILES_PREFIX = var.tiles_prefix
      # gdal2tiles parallelism follows the task's vCPU count.
      TILE_PROCESSES = tostring(floor(var.task_cpu / 1024))
    },
    var.extra_environment,
  )
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "main" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Used by ECS itself: pull the image, write logs, read the secret into the container env.
resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.planet_secret_arn]
  }
}

resource "aws_iam_role_policy" "execution_secret" {
  name   = "read-planet-secret"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secret.json
}

# Used by the application code.
resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid     = "ReadInputs"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.tiles.arn}/${var.aoi_key}",
      "${aws_s3_bucket.tiles.arn}/${var.state_key}",
    ]
  }

  statement {
    sid       = "WriteState"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.tiles.arn}/${var.state_key}"]
  }

  statement {
    sid       = "WriteTiles"
    actions   = ["s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.tiles.arn}/${var.tiles_prefix}/*"]
  }

  # Lets a missing state file come back as 404 rather than 403.
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.tiles.arn]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "tile-bucket-access"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

resource "aws_ecs_task_definition" "app" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  ephemeral_storage {
    size_in_gib = var.ephemeral_storage_gib
  }

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "tile-service"
    image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential = true
    environment = [
      for k, v in local.container_environment : { name = k, value = v }
    ]
    secrets = [{
      name      = "PL_API_KEY"
      valueFrom = local.planet_secret_arn
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "run"
      }
    }
  }])
}

# Networking: outbound only (Planet API, S3, ECR). No inbound ports.
data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

locals {
  vpc_id = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
}

data "aws_subnets" "default" {
  count = length(var.subnet_ids) == 0 ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

locals {
  subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.default[0].ids
}

resource "aws_security_group" "task" {
  name        = "${var.name}-task"
  description = "Outbound-only access for the tile pipeline task"
  vpc_id      = local.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
