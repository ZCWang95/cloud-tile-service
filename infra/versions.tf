terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Configure remote state before sharing this stack, e.g.:
  # backend "s3" {
  #   bucket = "my-terraform-state"
  #   key    = "cloud-tile-service/terraform.tfstate"
  #   region = "us-west-2"
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.name
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
