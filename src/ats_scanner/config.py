"""Limits, versions, paths.

All values here are the product-level constants from SPEC §5 and §2. The
app version comes from installed package metadata; nothing else in this
module performs I/O.
"""

from importlib.metadata import PackageNotFoundError, version


def _try_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return ""


APP_VERSION: str = _try_version("ats-scanner") or "0"

# Live in memory: 5 MB, 10 pages, 20k JD characters (SPEC §5 Limits).
MAX_FILE_BYTES: int = 5 * 1024 * 1024
MAX_PAGES: int = 10
MAX_JD_CHARS: int = 20_000

# The scoring engine and the curated dictionary evolve independently of the
# app release (SPEC §3 Determinism).
ENGINE_VERSION: str = "0.1.0"
DICTIONARY_VERSION: int = 0  # matches src/ats_scanner/data/dictionary.json
