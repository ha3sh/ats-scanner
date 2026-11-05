"""Load and validate the skills dictionary (wiring, not core; SPEC §3).

core/ never touches the filesystem: this loader reads
src/ats_scanner/data/dictionary.json, validates it against the Pydantic
models in core/dictionary.py, and hands the Dictionary to the caller
(main.py wiring, tests).
"""

import json
from pathlib import Path

from ats_scanner.core.dictionary import Dictionary

DICTIONARY_PATH = Path(__file__).resolve().parent.parent / "data" / "dictionary.json"


def load_dictionary(path: Path = DICTIONARY_PATH) -> Dictionary:
    """Read and validate the dictionary file."""
    return Dictionary.model_validate(json.loads(path.read_text(encoding="utf-8")))
