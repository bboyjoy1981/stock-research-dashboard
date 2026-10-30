"""Atomic, version-preserving local observation storage."""

import os
from pathlib import Path
import tempfile
import threading

import pandas as pd

from src.temperature_data import validate_observations

_STORE_LOCK = threading.RLock()


def load_observations(directory: Path) -> pd.DataFrame:
    path = Path(directory) / 'observations.json'
    if not path.exists():
        return validate_observations(pd.DataFrame())
    with path.open(encoding='utf-8') as handle:
        import json
        records = json.load(handle)
    return validate_observations(pd.DataFrame(records))


def save_observations(frame: pd.DataFrame, directory: Path) -> None:
    import json

    incoming = validate_observations(frame)
    if incoming.empty:
        return
    directory = Path(directory)
    with _STORE_LOCK:
        previous = load_observations(directory)
        combined = validate_observations(pd.concat([previous, incoming], ignore_index=True))
        records = combined.to_dict('records')
        for record in records:
            for key, value in record.items():
                if value is pd.NaT or value is pd.NA:
                    record[key] = None
                elif isinstance(value, pd.Timestamp):
                    record[key] = value.isoformat()
                elif isinstance(value, float) and pd.isna(value):
                    # Optional provenance differs by source. JSON null represents
                    # absent metadata; required numeric inputs were validated above.
                    record[key] = None
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='observations-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump(records, handle, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, directory / 'observations.json')
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
