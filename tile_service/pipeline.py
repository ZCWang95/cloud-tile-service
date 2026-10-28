import json
import logging
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tile_service.config import ConfigError, Settings
from tile_service.planet import OrdersClient, fetch_composites, find_orders
from tile_service.storage import S3Storage, file_count
from tile_service.tiles import build_tiles

logger = logging.getLogger(__name__)

SKIPPED_EXISTS = "Skipped - date already exists"
SKIPPED_COVERAGE = "Skipped - less coverage"
SUCCESS = "Tiles generated successfully"


def processed_dates(state: str) -> set:
    return {line.strip() for line in state.splitlines() if line.strip()}


def run(settings: Settings, storage: S3Storage, orders: OrdersClient, today: Optional[str] = None) -> str:
    run_date = settings.run_date or today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("Starting tile run for %s", run_date)

    state = storage.read_text(settings.state_key) or ""
    if run_date in processed_dates(state):
        logger.info("The date %s exists already.", run_date)
        return SKIPPED_EXISTS

    aoi = storage.read_text(settings.aoi_key)
    if aoi is None:
        raise RuntimeError(f"AOI s3://{settings.bucket}/{settings.aoi_key} not found")
    work = Path(settings.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    aoi_path = work / "aoi.geojson"
    aoi_path.write_text(aoi, encoding="utf-8")
    feature_count = len(json.loads(aoi).get("features", []))

    order_ids = find_orders(str(aoi_path), run_date, settings.min_cover, str(work))
    logger.info("Orders placed: %s", order_ids)
    if len(order_ids) < math.floor(feature_count * settings.min_order_fraction):
        logger.info("Skipping: %d orders for %d AOI features.", len(order_ids), feature_count)
        return SKIPPED_COVERAGE

    composites = fetch_composites(orders, order_ids, str(work / "downloads"), str(work / "basemaps"))
    if not composites:
        raise RuntimeError("Orders completed but produced no composite.tif files")

    date_folder = run_date.replace("-", "")
    out_dir = work / date_folder
    build_tiles(
        composites,
        str(out_dir),
        str(work / "scratch"),
        zoom=settings.zoom,
        processes=settings.processes,
        gdal2tiles_cmd=settings.gdal2tiles_cmd,
    )
    if not out_dir.exists() or file_count(str(out_dir)) == 0:
        raise RuntimeError("gdal2tiles produced no output")

    storage.upload_dir(str(out_dir), f"{settings.tiles_prefix}/{date_folder}", workers=settings.upload_workers)
    # Only record the date once every tile is uploaded, so a failed run is retried next time.
    storage.write_text(settings.state_key, f"{state}\n{run_date}" if state else run_date)
    return SUCCESS


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        settings = Settings.from_env()
    except ConfigError as e:
        logger.error("%s", e)
        return 2

    storage = S3Storage(settings.bucket)
    orders = OrdersClient(
        settings.planet_api_key,
        poll_seconds=settings.order_poll_seconds,
        timeout_seconds=settings.order_timeout_seconds,
    )
    try:
        message = run(settings, storage, orders)
    except Exception:
        logger.exception("Tile run failed")
        return 1
    finally:
        shutil.rmtree(settings.work_dir, ignore_errors=True)
    logger.info(message)
    return 0
