import io
import zipfile

import pytest

from tile_service.planet import OrdersClient, PlanetError, fetch_composites, parse_order_ids


class FakeResponse:
    def __init__(self, json_data=None, content=b""):
        self._json = json_data
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._json

    def iter_content(self, chunk_size):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, states, files):
        self.states = list(states)
        self.files = files
        self.auth = None

    def get(self, url, **kwargs):
        if url in self.files:
            return FakeResponse(content=self.files[url])
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        results = [{"name": f"order/{name}", "location": name} for name in self.files]
        return FakeResponse({"state": state, "_links": {"results": results}})


def zip_with_composite():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("files/composite.tif", b"tif")
        archive.writestr("files/composite_metadata.json", b"{}")
    return buf.getvalue()


def test_parse_order_ids_dedupes_in_order():
    output = "1: SUCCESS Order ID abc-1\n2: SUCCESS Order ID def-2\n3: Order ID abc-1\n"
    assert parse_order_ids(output) == ["abc-1", "def-2"]


def test_wait_polls_until_success():
    sleeps = []
    client = OrdersClient("key", session=FakeSession(["queued", "running", "success"], {}), sleep=sleeps.append)
    assert client.wait("o1")["state"] == "success"
    assert len(sleeps) == 2


def test_wait_raises_on_failed_order():
    client = OrdersClient("key", session=FakeSession(["failed"], {}), sleep=lambda s: None)
    with pytest.raises(PlanetError, match="failed"):
        client.wait("o1")


def test_wait_times_out():
    ticks = iter([0, 10, 20])
    client = OrdersClient(
        "key", session=FakeSession(["running"], {}), timeout_seconds=15, sleep=lambda s: None, clock=lambda: next(ticks)
    )
    with pytest.raises(PlanetError, match="still running"):
        client.wait("o1")


def test_fetch_composites_extracts_one_tif_per_order(tmp_path):
    session = FakeSession(["success"], {"bundle.zip": zip_with_composite(), "manifest.json": b"{}"})
    client = OrdersClient("key", session=session, sleep=lambda s: None)

    paths = fetch_composites(client, ["o1", "o2"], str(tmp_path / "dl"), str(tmp_path / "out"))

    assert sorted(p.name for p in paths) == ["o1.tif", "o2.tif"]
    assert all(p.read_bytes() == b"tif" for p in paths)
    assert not (tmp_path / "dl" / "o1").exists()
