variable "region" {
  description = "AWS region for every resource in this stack."
  type        = string
  default     = "us-west-2"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "cloud-tile-service"
}

variable "bucket_name" {
  description = "Globally unique S3 bucket holding the AOI, the processed-dates log, and the tiles."
  type        = string
}

variable "aoi_key" {
  description = "S3 key of the AOI GeoJSON passed to planetcoveragefinder."
  type        = string
  default     = "data/svr_quad_13.geojson"
}

variable "state_key" {
  description = "S3 key of the newline-separated list of dates already processed."
  type        = string
  default     = "data/ps_daily.txt"
}

variable "tiles_prefix" {
  description = "S3 prefix tiles are written under (<prefix>/<YYYYMMDD>/<z>/<x>/<y>.png). Only this prefix is served by CloudFront."
  type        = string
  default     = "data/planet_daily"
}

variable "image_tag" {
  description = "Tag of the image in ECR that the task runs."
  type        = string
  default     = "latest"
}

variable "task_cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU)."
  type        = number
  default     = 4096
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 16384
}

variable "ephemeral_storage_gib" {
  description = "Fargate scratch disk for downloads and tiles (21-200 GiB)."
  type        = number
  default     = 100
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression for the daily run."
  type        = string
  default     = "cron(0 12 * * ? *)"
}

variable "schedule_timezone" {
  description = "Time zone the schedule expression is evaluated in."
  type        = string
  default     = "UTC"
}

variable "schedule_enabled" {
  description = "Set to false to deploy everything without starting the daily runs yet."
  type        = bool
  default     = true
}

variable "extra_environment" {
  description = "Extra environment variables for the container (e.g. MIN_COVER, ZOOM_LEVELS, ORDER_TIMEOUT_SECONDS)."
  type        = map(string)
  default     = {}
}

variable "planet_api_key_secret_arn" {
  description = "Existing Secrets Manager secret holding the Planet API key. Leave empty to create one (you then set its value)."
  type        = string
  default     = ""
}

variable "vpc_id" {
  description = "VPC to run the task in. Empty uses the default VPC."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Subnets for the task. They need internet access (public subnet, or private with NAT). Empty uses the default VPC's subnets."
  type        = list(string)
  default     = []
}

variable "assign_public_ip" {
  description = "Give the task a public IP. Required in public subnets without NAT."
  type        = bool
  default     = true
}

variable "cors_allowed_origins" {
  description = "Origins allowed to fetch tiles cross-origin through CloudFront."
  type        = list(string)
  default     = ["*"]
}

variable "alert_email" {
  description = "Email notified when a run fails. Empty disables the subscription (the SNS topic is still created)."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for task logs."
  type        = number
  default     = 30
}
