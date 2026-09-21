import re
import html
import unicodedata
from typing import Optional, Any

def strip_html(text: Optional[str]) -> str:
    """Remove HTML tags and decode HTML entities."""
    if not text:
        return ""
    # Decode HTML entities first e.g. &nbsp;, &amp;
    text = html.unescape(text)
    # Replace <br>, <p>, </div> with newlines to preserve separation
    text = re.sub(r'<(?:br|/p|/div|/li)>', '\n', text, flags=re.IGNORECASE)
    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    return text

def clean_text(text: Optional[str], preserve_newlines: bool = True) -> Optional[str]:
    """
    Clean text:
    - Unicode NFC normalization
    - Strip HTML
    - Trim trailing and leading whitespace
    - Normalize excessive whitespace
    - Preserve meaningful newlines if requested
    """
    if text is None:
        return None
    
    # 1. Unicode NFC normalization
    norm = unicodedata.normalize('NFC', str(text))
    
    # 2. Strip HTML
    norm = strip_html(norm)
    
    # 3. Clean whitespace
    if preserve_newlines:
        # Normalize carriage returns
        norm = norm.replace('\r\n', '\n').replace('\r', '\n')
        # Normalize multiple horizontal spaces into single space per line
        lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in norm.split('\n')]
        # Drop excessive consecutive empty lines (max 2 consecutive newlines)
        cleaned_lines = []
        consecutive_empty = 0
        for line in lines:
            if not line:
                consecutive_empty += 1
                if consecutive_empty <= 1:
                    cleaned_lines.append('')
            else:
                consecutive_empty = 0
                cleaned_lines.append(line)
        result = '\n'.join(cleaned_lines).strip()
    else:
        result = re.sub(r'\s+', ' ', norm).strip()
        
    return result if result else None

def normalize_id(val: Optional[Any]) -> Optional[str]:
    """
    Normalize record identifiers (e.g. converting numeric IDs from Excel like 3082.0 to '3082').
    """
    if val is None:
        return None
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        prefix = val_str[:-2]
        if prefix.isdigit() or (prefix.startswith("-") and prefix[1:].isdigit()):
            return prefix
    return val_str if val_str else None
