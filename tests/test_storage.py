import boto3
import pytest
from moto import mock_aws

from tile_service.storage import S3Storage

BUCKET = "test-tiles"


@pytest.fixture
def storage():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3Storage(BUCKET, client=client)


def test_read_missing_key_returns_none(storage):
    assert storage.read_text("data/missing.txt") is None


def test_write_then_read(storage):
    storage.write_text("data/ps_daily.txt", "2024-01-01\n2024-01-02")
    assert storage.read_text("data/ps_daily.txt") == "2024-01-01\n2024-01-02"


def test_upload_dir_keeps_tile_layout(storage, tmp_path):
    (tmp_path / "8" / "40").mkdir(parents=True)
    (tmp_path / "8" / "40" / "97.png").write_bytes(b"png")
    (tmp_path / "leaflet.html").write_text("<html>")

    count = storage.upload_dir(str(tmp_path), "/data/planet_daily/20240101/", workers=4)

    assert count == 2
    head = storage.client.head_object(Bucket=BUCKET, Key="data/planet_daily/20240101/8/40/97.png")
    assert head["ContentType"] == "image/png"
    keys = {o["Key"] for o in storage.client.list_objects_v2(Bucket=BUCKET)["Contents"]}
    assert keys == {"data/planet_daily/20240101/8/40/97.png", "data/planet_daily/20240101/leaflet.html"}
