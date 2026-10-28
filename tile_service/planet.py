import logging
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

import requests

logger = logging.getLogger(__name__)

ORDERS_URL = "https://api.planet.com/compute/ops/orders/v2"
SUCCESS_STATES = {"success", "partial"}
FAILED_STATES = {"failed", "cancelled"}


class PlanetError(Exception):
    pass


def parse_order_ids(pcf_output: str) -> List[str]:
    # dict.fromkeys de-duplicates while keeping pcf's output order.
    return list(dict.fromkeys(re.findall(r"Order ID ([\w-]+)", pcf_output)))


def find_orders(aoi_path: str, date: str, min_cover: int, work_dir: str) -> List[str]:
    """Run planetcoveragefinder for one date and place orders for the AOIs it can cover."""
    command = ["pcf", aoi_path, date, "-t", str(min_cover), "--order"]
    logger.info("Running %s", " ".join(command))
    result = subprocess.run(command, cwd=work_dir, capture_output=True, text=True)
    logger.info("pcf output:\n%s", result.stdout)
    if result.returncode != 0:
        raise PlanetError(f"pcf exited with {result.returncode}: {result.stderr.strip()}")
    return parse_order_ids(result.stdout)


class OrdersClient:
    def __init__(
        self,
        api_key: str,
        session: Optional[requests.Session] = None,
        poll_seconds: int = 30,
        timeout_seconds: int = 4 * 60 * 60,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.session = session or requests.Session()
        self.session.auth = (api_key, "")
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.sleep = sleep
        self.clock = clock

    def get(self, order_id: str) -> dict:
        response = self.session.get(f"{ORDERS_URL}/{order_id}", timeout=60)
        response.raise_for_status()
        return response.json()

    def wait(self, order_id: str) -> dict:
        deadline = self.clock() + self.timeout_seconds
        while True:
            order = self.get(order_id)
            state = order.get("state")
            if state in SUCCESS_STATES:
                logger.info("Order %s finished with state %s", order_id, state)
                return order
            if state in FAILED_STATES:
                raise PlanetError(f"Order {order_id} ended with state {state}")
            if self.clock() >= deadline:
                raise PlanetError(f"Order {order_id} still {state} after {self.timeout_seconds}s")
            logger.info("Order %s is %s; checking again in %ss", order_id, state, self.poll_seconds)
            self.sleep(self.poll_seconds)

    def download(self, order: dict, dest_dir: Path) -> List[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for result in order.get("_links", {}).get("results") or []:
            path = dest_dir / Path(result["name"]).name
            with self.session.get(result["location"], stream=True, timeout=300) as response:
                response.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
            paths.append(path)
        return paths


def fetch_composites(client: OrdersClient, order_ids: List[str], download_dir: str, dest_dir: str) -> List[Path]:
    """Wait for each order, download it, and collect its composite.tif as <dest_dir>/<order_id>[_n].tif."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    composites = []
    for order_id in order_ids:
        order_dir = Path(download_dir) / order_id
        order = client.wait(order_id)
        for path in client.download(order, order_dir):
            if path.suffix == ".zip":
                with zipfile.ZipFile(path) as archive:
                    archive.extractall(order_dir / path.stem)
        found = sorted(order_dir.rglob("composite.tif"))
        if not found:
            logger.warning("Order %s has no composite.tif", order_id)
        for i, tif in enumerate(found):
            target = dest / (f"{order_id}.tif" if i == 0 else f"{order_id}_{i}.tif")
            shutil.move(str(tif), target)
            composites.append(target)
        shutil.rmtree(order_dir, ignore_errors=True)
    return composites
