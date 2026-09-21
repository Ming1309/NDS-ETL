import re
from datetime import datetime, date, time
from typing import Optional, Union
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def parse_datetime(dt_val: Optional[Union[str, datetime, date]]) -> Optional[datetime]:
    """
    Parse a datetime value:
    - If already datetime: if naive, localize to Asia/Ho_Chi_Minh
    - If date: convert to datetime at 00:00:00 Asia/Ho_Chi_Minh
    - If string:
      - Try ISO 8601 format (e.g. 2026-09-19T12:55:07.272412+00:00 or 2026-10-22T12:00:00)
      - Try DD/MM/YYYY or YYYY-MM-DD
    """
    if dt_val is None:
        return None
    
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=VN_TZ)
        return dt_val
        
    if isinstance(dt_val, date):
        return datetime.combine(dt_val, time(0, 0, 0, tzinfo=VN_TZ))

    val_str = str(dt_val).strip()
    if not val_str:
        return None

    # Try ISO format
    try:
        dt = datetime.fromisoformat(val_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt
    except ValueError:
        pass

    # Try DD/MM/YYYY HH:MM:SS or DD/MM/YYYY
    patterns = [
        ("%d/%m/%Y %H:%M:%S", False),
        ("%d/%m/%Y %H:%M", False),
        ("%d/%m/%Y", True),
        ("%Y-%m-%d %H:%M:%S", False),
        ("%Y-%m-%d %H:%M", False),
        ("%Y-%m-%d", True),
    ]

    for pattern, is_date_only in patterns:
        try:
            dt = datetime.strptime(val_str, pattern)
            if is_date_only:
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=VN_TZ)
            else:
                dt = dt.replace(tzinfo=VN_TZ)
            return dt
        except ValueError:
            continue

    return None

def parse_date(date_val: Optional[Union[str, date, datetime]]) -> Optional[date]:
    """Extract date part from value."""
    dt = parse_datetime(date_val)
    return dt.date() if dt else None
