import openpyxl
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

def read_excel_sheet(
    file_path: Union[str, Path],
    sheet_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Read an Excel sheet into a list of dicts:
    - Skips completely empty rows
    - Records row number in '__line_number__'
    - Converts cell values to clean strings/numbers
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {path}")

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if sheet_name:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' not found in {path}. Available sheets: {wb.sheetnames}")
        ws = wb[sheet_name]
    else:
        ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        return []

    # Clean header names
    clean_header = [str(h).strip() if h is not None else f"col_{idx}" for idx, h in enumerate(header)]

    records = []
    for row_idx, row in enumerate(rows_iter, start=2):
        # Skip completely empty row
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue
            
        record = {}
        for col_idx, cell_value in enumerate(row):
            if col_idx < len(clean_header):
                col_name = clean_header[col_idx]
                record[col_name] = cell_value
        record["__line_number__"] = row_idx
        records.append(record)

    wb.close()
    return records
