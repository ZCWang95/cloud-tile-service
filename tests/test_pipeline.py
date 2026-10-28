import json
from pathlib import Path

import pytest

from tile_service import pipeline
from tile_service.config import ConfigError, Settings

AOI = json.dumps({"type": "FeatureCollection", "features": [{}, {}, {}, {}]})


class FakeStorage:
    def __init__(self, objects):
        self.objects = dict(objects)
        self.uploads = []

    def read_text(self, key):
        return self.objects.get(key)

    def write_text(self, key, text):
        self.objects[key] = text

    def upload_dir(self, local_dir, prefix, workers=32):
        self.uploads.append(prefix)
        return 1


@pytest.fixture
def settings(tmp_path):
    return Settings(bucket="b", planet_api_key="k", work_dir=str(tmp_path / "work"))


def test_skips_when_date_already_processed(settings, monkeypatch):
    storage = FakeStorage({settings.state_key: "2024-01-01\n2024-01-02"})
    monkeypatch.setattr(pipeline, "find_orders", lambda *a: pytest.fail("should not order"))
    assert pipeline.run(settings, storage, None, today="2024-01-02") == pipeline.SKIPPED_EXISTS


def test_skips_when_too_few_orders(settings, monkeypatch):
    storage = FakeStorage({settings.state_key: "", settings.aoi_key: AOI})
    monkeypatch.setattr(pipeline, "find_orders", lambda *a: ["only-one"])
    assert pipeline.run(settings, storage, None, today="2024-01-03") == pipeline.SKIPPED_COVERAGE
    assert storage.objects[settings.state_key] == ""


def test_success_uploads_then_records_date(settings, monkeypatch):
    storage = FakeStorage({settings.state_key: "2024-01-01", settings.aoi_key: AOI})
    calls = {}
    monkeypatch.setattr(pipeline, "find_orders", lambda aoi, date, cover, work: calls.setdefault("date", date) and ["a", "b"])
    monkeypatch.setattr(pipeline, "fetch_composites", lambda *a: [Path("a.tif")])

    def fake_build_tiles(tifs, out_dir, scratch, **kwargs):
        Path(out_dir, "8").mkdir(parents=True)
        Path(out_dir, "8", "1.png").write_bytes(b"x")

    monkeypatch.setattr(pipeline, "build_tiles", fake_build_tiles)

    assert pipeline.run(settings, storage, None, today="2024-01-05") == pipeline.SUCCESS
    assert calls["date"] == "2024-01-05"
    assert storage.uploads == ["data/planet_daily/20240105"]
    assert storage.objects[settings.state_key] == "2024-01-01\n2024-01-05"


def test_failed_tiling_does_not_record_date(settings, monkeypatch):
    storage = FakeStorage({settings.state_key: "", settings.aoi_key: AOI})
    monkeypatch.setattr(pipeline, "find_orders", lambda *a: ["a", "b"])
    monkeypatch.setattr(pipeline, "fetch_composites", lambda *a: [Path("a.tif")])
    monkeypatch.setattr(pipeline, "build_tiles", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="no output"):
        pipeline.run(settings, storage, None, today="2024-01-05")
    assert storage.objects[settings.state_key] == ""
    assert storage.uploads == []


def test_settings_from_env():
    s = Settings.from_env({"TILE_BUCKET": "b", "PL_API_KEY": "k", "TILES_PREFIX": "/x/y/", "TILE_PROCESSES": "4"})
    assert (s.bucket, s.tiles_prefix, s.processes) == ("b", "x/y", 4)


@pytest.mark.parametrize("env", [{"PL_API_KEY": "k"}, {"TILE_BUCKET": "b", "PL_API_KEY": "k", "RUN_DATE": "01/02/2024"}])
def test_settings_rejects_bad_env(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)
