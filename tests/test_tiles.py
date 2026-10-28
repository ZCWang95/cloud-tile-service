from pathlib import Path

import numpy as np
import pytest
import rasterio

from tile_service import tiles


def write_tif(path, band):
    with rasterio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0],
                       count=1, dtype=band.dtype) as dst:
        dst.write(band, 1)


def test_band_range_ignores_zero(tmp_path):
    path = tmp_path / "a.tif"
    write_tif(path, np.array([[0, 5], [9, 0]], dtype=np.uint16))
    assert tiles.band_range(path) == (5.0, 9.0)


def test_band_range_empty(tmp_path):
    path = tmp_path / "a.tif"
    write_tif(path, np.zeros((2, 2), dtype=np.uint16))
    assert tiles.band_range(path) is None


def test_build_tiles_passes_gdal2tiles_arguments(tmp_path, monkeypatch):
    commands = []

    def fake_run(command):
        commands.append(list(command))
        if command[0] == "gdal_translate":
            # Create the output file so the later unlink() calls succeed.
            out = command[2] if command[1] != "-ot" else command[-1]
            Path(out).write_bytes(b"")

    monkeypatch.setattr(tiles, "run", fake_run)
    monkeypatch.setattr(tiles, "band_range", lambda path: (1.0, 100.0))

    tiles.build_tiles([Path("o1.tif")], str(tmp_path / "out"), str(tmp_path / "scratch"),
                      zoom="8-15", processes=6, gdal2tiles_cmd="/usr/bin/python3 -m osgeo_utils.gdal2tiles")

    assert commands[-1] == ["/usr/bin/python3", "-m", "osgeo_utils.gdal2tiles", "-z", "8-15", "--processes=6",
                            str(tmp_path / "scratch" / "planet_merged.vrt"), str(tmp_path / "out")]
    assert commands[-2][:2] == ["gdalbuildvrt", str(tmp_path / "scratch" / "planet_merged.vrt")]
    assert ["-scale", "1.0", "100.0", "0", "65535"] == commands[1][3:8]


def test_build_tiles_fails_without_usable_rasters(tmp_path, monkeypatch):
    def fake_run(command):
        Path(command[2]).write_bytes(b"")

    monkeypatch.setattr(tiles, "run", fake_run)
    monkeypatch.setattr(tiles, "band_range", lambda path: None)
    with pytest.raises(RuntimeError, match="No usable"):
        tiles.build_tiles([Path("o1.tif")], str(tmp_path / "out"), str(tmp_path / "scratch"))
