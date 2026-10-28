resource "aws_s3_bucket" "tiles" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "tiles" {
  bucket                  = aws_s3_bucket.tiles.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "tiles" {
  bucket = aws_s3_bucket.tiles.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tiles" {
  bucket = aws_s3_bucket.tiles.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "tiles" {
  bucket = aws_s3_bucket.tiles.id
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Tiles are served through CloudFront; the bucket itself stays private.
resource "aws_cloudfront_origin_access_control" "tiles" {
  name                              = "${var.name}-tiles"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_response_headers_policy" "cors" {
  name = "${var.name}-tiles-cors"
  cors_config {
    access_control_allow_credentials = false
    origin_override                  = true
    access_control_allow_headers {
      items = ["*"]
    }
    access_control_allow_methods {
      items = ["GET", "HEAD"]
    }
    access_control_allow_origins {
      items = var.cors_allowed_origins
    }
  }
}

resource "aws_cloudfront_distribution" "tiles" {
  enabled         = true
  comment         = "${var.name} tiles"
  is_ipv6_enabled = true
  price_class     = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.tiles.bucket_regional_domain_name
    origin_id                = "tiles-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.tiles.id
  }

  default_cache_behavior {
    target_origin_id           = "tiles-s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.cors.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "tiles_bucket" {
  statement {
    sid       = "CloudFrontReadTiles"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.tiles.arn}/${var.tiles_prefix}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.tiles.arn]
    }
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.tiles.arn, "${aws_s3_bucket.tiles.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tiles" {
  bucket     = aws_s3_bucket.tiles.id
  policy     = data.aws_iam_policy_document.tiles_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.tiles]
}
