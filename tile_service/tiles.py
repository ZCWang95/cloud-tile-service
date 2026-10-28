import logging
import shlex
import subprocess
from pathlib import Path
from typing import List, Sequence

import numpy as np
import rasterio

logger = logging.getLogger(__name__)


def run(command: Sequence[str]) -> None:
    logger.info("Running %s", " ".join(command))
    subprocess.run(list(command), check=True)


def band_range(path: Path):
    """Min/max of band 1, ignoring zero (nodata) pixels; None if the band is empty."""
    with rasterio.open(path) as src:
        band = src.read(1)
    valid = band[band != 0]
    if valid.size == 0:
        return None
    return float(np.min(valid)), float(np.max(valid))


def to_display_rgb(src: Path, dst: Path, scratch_dir: Path) -> bool:
    """Reorder BGR to RGB, apply a square-root stretch, and convert to 8-bit."""
    rgb = scratch_dir / f"{src.stem}_rgb.tif"
    stretched = scratch_dir / f"{src.stem}_stretched.tif"
    run(["gdal_translate", str(src), str(rgb), "-b", "3", "-b", "2", "-b", "1",
         "-co", "COMPRESS=DEFLATE", "-co", "PHOTOMETRIC=RGB"])
    value_range = band_range(rgb)
    if value_range is None:
        logger.warning("Skipping %s: no valid pixels", src.name)
        rgb.unlink()
        return False
    minval, maxval = value_range
    run(["gdal_translate", str(rgb), str(stretched), "-scale", str(minval), str(maxval), "0", "65535",
         "-exponent", "0.5", "-co", "COMPRESS=DEFLATE", "-co", "PHOTOMETRIC=RGB"])
    run(["gdal_translate", "-ot", "Byte", "-scale", "0", "65535", "0", "255", str(stretched), str(dst)])
    rgb.unlink()
    stretched.unlink()
    return True


def build_tiles(
    tif_paths: List[Path],
    out_dir: str,
    scratch_dir: str,
    zoom: str = "8-15",
    processes: int = 1,
    gdal2tiles_cmd: str = "gdal2tiles",
) -> None:
    scratch = Path(scratch_dir)
    processed_dir = scratch / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    processed = []
    for tif in tif_paths:
        dst = processed_dir / tif.name
        if to_display_rgb(tif, dst, scratch):
            processed.append(dst)
    if not processed:
        raise RuntimeError("No usable basemap rasters to tile")

    vrt = scratch / "planet_merged.vrt"
    run(["gdalbuildvrt", str(vrt)] + [str(p) for p in processed])
    run(shlex.split(gdal2tiles_cmd) + ["-z", zoom, f"--processes={processes}", str(vrt), out_dir])
