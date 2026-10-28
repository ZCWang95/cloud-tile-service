output "bucket" {
  value = aws_s3_bucket.tiles.bucket
}

output "tiles_url_template" {
  description = "Tile URL for the front end; replace {date} with YYYYMMDD. gdal2tiles writes TMS (y-flipped) tiles, so set tms: true in Leaflet."
  value       = "https://${aws_cloudfront_distribution.tiles.domain_name}/${var.tiles_prefix}/{date}/{z}/{x}/{y}.png"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "planet_api_key_secret_arn" {
  value = local.planet_secret_arn
}

output "log_group" {
  value = aws_cloudwatch_log_group.app.name
}

output "run_task_command" {
  description = "Start a run immediately, outside the schedule."
  value = join(" ", [
    "aws ecs run-task --region ${var.region}",
    "--cluster ${aws_ecs_cluster.main.name}",
    "--task-definition ${aws_ecs_task_definition.app.family}",
    "--launch-type FARGATE",
    "--network-configuration 'awsvpcConfiguration={subnets=[${join(",", local.subnet_ids)}],securityGroups=[${aws_security_group.task.id}],assignPublicIp=${var.assign_public_ip ? "ENABLED" : "DISABLED"}}'",
  ])
}
