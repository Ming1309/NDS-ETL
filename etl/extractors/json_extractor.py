import json
from pathlib import Path
from typing import List, Dict, Any, Union

def read_json_records(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Read JSON array into list of dicts.
    Assigns '__line_number__' as element index (1-indexed).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        data = [data]

    for idx, item in enumerate(data, start=1):
        if isinstance(item, dict):
            item["__line_number__"] = idx

    return data
