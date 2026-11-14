"""Shared plumbing for the record lookups: polite HTTP with retries + on-disk cache, geometry helpers, safe results.

Cache: every successful response is stored as raw bytes under ``CACHE_DIR`` (default ``data/cache/context/``), keyed
by a hash of method + URL + parameters. Tests point ``CACHE_DIR`` at ``tests/fixtures/context/`` and set ``OFFLINE``,
so the saved sample responses *are* the cache and no request leaves the machine.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import shape

_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = Path(os.environ.get("SARWATCH_CONTEXT_CACHE", _ROOT / "data" / "cache" / "context"))
OFFLINE = os.environ.get("SARWATCH_OFFLINE", "") not in ("", "0")
TIMEOUT = 30          # seconds per request
RETRIES = 2           # extra attempts after the first one
USER_AGENT = "sarwatch/0.1 (NASA Space Apps 2026 research prototype)"

# Every Catalan / Spanish service below speaks ETRS89 / UTM 31N (EPSG:25831): metres, x = easting, y = northing.
UTM = 25831
_to_utm = Transformer.from_crs(4326, UTM, always_xy=True).transform


class OfflineMiss(RuntimeError):
    """OFFLINE is set and the response is not in the cache."""


def fetch(source: str, url: str, params: dict | None = None, *, method: str = "GET", cache: bool = True,
          timeout: float | None = None) -> bytes:
    """Return the response body. Retries on network errors / 5xx, caches successes, raises on final failure."""
    params = dict(params or {})
    key = hashlib.sha256(json.dumps([method, url, sorted(params.items())], ensure_ascii=False).encode()).hexdigest()
    path = Path(CACHE_DIR) / f"{source}-{key[:16]}.bin"
    if cache and path.exists():
        return path.read_bytes()
    if OFFLINE:
        raise OfflineMiss(f"offline and not cached: {source} {url}")
    last = None
    for attempt in range(RETRIES + 1):
        try:
            kw = {"params": params} if method == "GET" else {"data": params}
            r = requests.request(method, url, timeout=timeout or TIMEOUT, headers={"User-Agent": USER_AGENT}, **kw)
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            body = r.content
            _check_body(body)
            if cache:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            return body
        except (requests.RequestException, ServiceError) as e:
            last = e
            if attempt < RETRIES:
                time.sleep(1.5 * (attempt + 1))
    raise last


class ServiceError(RuntimeError):
    """The service answered 200 but with an error document (ArcGIS JSON error, OGC exception, empty body)."""


def _check_body(body: bytes) -> None:
    head = body[:600].lstrip()
    if not head:
        raise ServiceError("empty response")
    if head.startswith(b"{") and b'"error"' in head[:20]:
        raise ServiceError(json.loads(body).get("error", {}).get("message", "error"))
    if b"ExceptionReport" in head:
        raise ServiceError(head.decode("latin-1", "replace"))


def to_utm(geometry: dict):
    """GeoJSON Polygon / MultiPolygon in EPSG:4326 (lon, lat) -> shapely geometry in EPSG:25831 metres."""
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("geometry must be a GeoJSON Polygon or MultiPolygon")
    g = shapely.transform(shape(geometry), lambda xy: np.column_stack(_to_utm(xy[:, 0], xy[:, 1])))  # shapely ≥ 2.0
    if g.is_empty:
        raise ValueError("empty geometry")
    if g.is_valid:
        return g
    fixed = shapely.make_valid(g)  # not buffer(0): that drops a lobe of a self-crossing (bowtie) polygon
    parts = [p for p in getattr(fixed, "geoms", [fixed]) if p.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else g.buffer(0)


def safe(source: str, default_url: str):
    """Decorator: the lookup never raises; failures come back as ``checked: False`` + ``error``."""
    def wrap(fn):
        @functools.wraps(fn)
        def run(geometry: dict, **options) -> dict:
            try:
                out = fn(geometry, **options)
                return {"source": source, "url": default_url, "checked": True, **out}
            except Exception as e:  # noqa: BLE001 (contract: never raise to the caller)
                return {"source": source, "url": default_url, "checked": False, "error": f"{type(e).__name__}: {e}"}
        return run
    return wrap
