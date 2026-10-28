import os
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    bucket: str
    planet_api_key: str
    aoi_key: str = "data/svr_quad_13.geojson"
    state_key: str = "data/ps_daily.txt"
    tiles_prefix: str = "data/planet_daily"
    # YYYY-MM-DD; defaults to today's UTC date when unset.
    run_date: Optional[str] = None
    # Coverage percentage pcf requires before it places an order (pcf -t).
    min_cover: int = 75
    # Skip the run when fewer than this fraction of AOI features got an order.
    min_order_fraction: float = 0.5
    zoom: str = "8-15"
    processes: int = os.cpu_count() or 1
    order_timeout_seconds: int = 4 * 60 * 60
    order_poll_seconds: int = 30
    work_dir: str = "/tmp/tile-service"
    gdal2tiles_cmd: str = "gdal2tiles"
    upload_workers: int = 32

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        def require(name):
            value = env.get(name, "").strip()
            if not value:
                raise ConfigError(f"Environment variable {name} is required")
            return value

        overrides = {}
        string_vars = {
            "AOI_KEY": "aoi_key",
            "STATE_KEY": "state_key",
            "TILES_PREFIX": "tiles_prefix",
            "RUN_DATE": "run_date",
            "ZOOM_LEVELS": "zoom",
            "WORK_DIR": "work_dir",
            "GDAL2TILES_CMD": "gdal2tiles_cmd",
        }
        int_vars = {
            "MIN_COVER": "min_cover",
            "TILE_PROCESSES": "processes",
            "ORDER_TIMEOUT_SECONDS": "order_timeout_seconds",
            "ORDER_POLL_SECONDS": "order_poll_seconds",
            "UPLOAD_WORKERS": "upload_workers",
        }
        for name, field in string_vars.items():
            if env.get(name):
                overrides[field] = env[name].strip()
        for name, field in int_vars.items():
            if env.get(name):
                try:
                    overrides[field] = int(env[name])
                except ValueError:
                    raise ConfigError(f"{name} must be an integer, got {env[name]!r}")
        if env.get("MIN_ORDER_FRACTION"):
            overrides["min_order_fraction"] = float(env["MIN_ORDER_FRACTION"])
        if "tiles_prefix" in overrides:
            overrides["tiles_prefix"] = overrides["tiles_prefix"].strip("/")
        if "run_date" in overrides:
            try:
                date.fromisoformat(overrides["run_date"])
            except ValueError:
                raise ConfigError(f"RUN_DATE must be YYYY-MM-DD, got {overrides['run_date']!r}")

        return cls(
            bucket=require("TILE_BUCKET"),
            planet_api_key=require("PL_API_KEY"),
            **overrides,
        )
