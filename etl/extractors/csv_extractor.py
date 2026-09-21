import csv
from pathlib import Path
from typing import List, Dict, Any, Union

def read_csv_records(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Read CSV file into a list of dicts:
    - Uses utf-8-sig to automatically handle BOM (\ufeff)
    - Supports multi-line strings in quoted fields
    - Trims column names
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Clean field names of whitespace / stray BOM
        cleaned_fieldnames = [k.strip() if k else "" for k in (reader.fieldnames or [])]
        for row_idx, row in enumerate(reader, start=2):
            clean_row = {}
            for k, v in row.items():
                clean_k = k.strip() if k else ""
                clean_row[clean_k] = v
            clean_row["__line_number__"] = row_idx
            records.append(clean_row)
    return records
