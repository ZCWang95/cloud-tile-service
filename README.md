# cloud-tile-service

Daily pipeline that turns Planet basemaps into web map tiles, running on AWS.

Each run:

1. Reads the list of processed dates (`data/ps_daily.txt`) from S3 and stops if today is already there.
2. Downloads the AOI GeoJSON (`data/svr_quad_13.geojson`) from S3.
3. Runs `pcf` (planetcoveragefinder, vendored in `planetcoveragefinder-main/`) to find full-coverage
   PlanetScope imagery for the date and place orders. The run stops if fewer than half the AOI
   features got an order.
4. Waits for each order through the Planet Orders API, downloads it, and extracts `composite.tif`.
5. Converts each composite to 8-bit RGB with a square-root stretch, mosaics them into a VRT, and runs
   `gdal2tiles` for zoom levels 8–15.
6. Uploads the tiles to `s3://<bucket>/data/planet_daily/<YYYYMMDD>/`, then adds the date to
   `ps_daily.txt`. A failed run doesn't record the date, so the next run tries again.

## AWS architecture

```
EventBridge Scheduler (daily) ──► ECS Fargate task (this image, from ECR)
                                     │  PL_API_KEY from Secrets Manager
                                     │  logs to CloudWatch /ecs/cloud-tile-service
                                     ▼
                                   S3 bucket ──► CloudFront (serves data/planet_daily/* only)
ECS task stopped with error ──► EventBridge rule ──► SNS ──► email
```

Everything is defined in Terraform under `infra/`. Fargate fits this workload: one long batch job a
day, with no 15-minute limit (unlike Lambda), up to 200 GiB of scratch disk, and no cost between runs.

## Code layout

| Path | Purpose |
|---|---|
| `tile_service/pipeline.py` | Orchestrates a run; `python -m tile_service` is the container entry point |
| `tile_service/config.py` | Settings from environment variables |
| `tile_service/storage.py` | S3 reads/writes and parallel tile upload |
| `tile_service/planet.py` | Runs `pcf`, waits for and downloads Planet orders |
| `tile_service/tiles.py` | GDAL processing and `gdal2tiles` |
| `infra/` | Terraform: S3, CloudFront, ECR, ECS, Scheduler, IAM, Secrets Manager, alerts |
| `scripts/push_image.sh` | Build and push the image to ECR |
| `scripts/migrate_from_gcs.sh` | One-time copy of existing data from GCS |

## Configuration

Set on the ECS task by Terraform; override or add values with `extra_environment` in `terraform.tfvars`.

| Variable | Default | Meaning |
|---|---|---|
| `TILE_BUCKET` | (required) | S3 bucket |
| `PL_API_KEY` | (required) | Planet API key; injected from Secrets Manager |
| `AOI_KEY` | `data/svr_quad_13.geojson` | AOI GeoJSON key |
| `STATE_KEY` | `data/ps_daily.txt` | Processed-dates log key |
| `TILES_PREFIX` | `data/planet_daily` | Where tiles are written |
| `RUN_DATE` | today (UTC) | Process a specific `YYYY-MM-DD` instead |
| `MIN_COVER` | `75` | Coverage percentage `pcf` requires (`pcf -t`) |
| `MIN_ORDER_FRACTION` | `0.5` | Skip when fewer AOI features than this got an order |
| `ZOOM_LEVELS` | `8-15` | `gdal2tiles -z` |
| `TILE_PROCESSES` | vCPU count | `gdal2tiles --processes` |
| `ORDER_TIMEOUT_SECONDS` | `14400` | Give up waiting for a Planet order after this long |
| `ORDER_POLL_SECONDS` | `30` | Order status polling interval |
| `UPLOAD_WORKERS` | `32` | Parallel S3 uploads |

## Deploying

Prerequisites: AWS CLI with credentials, Terraform >= 1.5, Docker.

```bash
# 1. Infrastructure
cd infra
cp terraform.tfvars.example terraform.tfvars   # set bucket_name, alert_email, schedule...
terraform init
terraform apply -var schedule_enabled=false    # hold the schedule until the image and key exist
cd ..

# 2. Planet API key
aws secretsmanager put-secret-value \
  --secret-id "$(terraform -chdir=infra output -raw planet_api_key_secret_arn)" \
  --secret-string 'YOUR_PLANET_API_KEY'

# 3. Image
scripts/push_image.sh

# 4. Inputs: copy the existing data from GCS (or upload the AOI and an empty ps_daily.txt)
scripts/migrate_from_gcs.sh shrey-snowviz-platform "$(terraform -chdir=infra output -raw bucket)" data

# 5. Try one run, then enable the schedule
eval "$(terraform -chdir=infra output -raw run_task_command)"
aws logs tail "$(terraform -chdir=infra output -raw log_group)" --follow
terraform -chdir=infra apply
```

To deploy a code change, run `scripts/push_image.sh` again. The task uses `:latest`, so the next run
picks up the new image. Use `image_tag` to pin a specific version.

### Pointing the front end at AWS

Tiles keep the same path layout as on GCS, so only the host changes:

```
https://<cloudfront-domain>/data/planet_daily/<YYYYMMDD>/{z}/{x}/{y}.png
```

`terraform output tiles_url_template` prints the exact URL. `gdal2tiles` writes TMS (y-flipped)
tiles, so in Leaflet keep `tms: true`. The AOI and `ps_daily.txt` are not exposed through CloudFront.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt ./planetcoveragefinder-main
pytest
```

The tests mock S3 (moto), the Planet API, and the GDAL commands, so they need neither AWS nor Planet
credentials. CI (`.github/workflows/ci.yml`) also validates the Terraform and builds the image.

## Notes

- `pcf --order` places orders before the coverage check, so a skipped run can still use Planet quota.
  This is how the previous version behaved too.
- Costs at the defaults (4 vCPU / 16 GB, about 1 hour a day): about $7/month for Fargate, plus S3 storage
  ($0.023/GB-month), S3 PUT requests ($0.005 per 1,000 tiles), and CloudFront transfer.
