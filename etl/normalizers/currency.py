import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Union, Tuple

def parse_decimal(val: Optional[Union[str, int, float, Decimal]]) -> Optional[Decimal]:
    """
    Parse a numeric value into Decimal with 2 decimal places.
    Returns None if val is missing or invalid. Does not convert missing to 0.
    """
    if val is None:
        return None
        
    if isinstance(val, (int, Decimal)):
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
    if isinstance(val, float):
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
    val_str = str(val).strip()
    if not val_str:
        return None
        
    # Remove currency symbols and formatting like "19.990.000đ", "19,990,000 VND"
    clean_val = re.sub(r'[^\d.,]', '', val_str)
    if not clean_val:
        return None

    # Handle Vietnamese thousand separator "." vs decimal point "," or vice-versa
    # e.g. "19.990.000" -> "19990000"
    if clean_val.count('.') > 1:
        clean_val = clean_val.replace('.', '')
    elif clean_val.count(',') > 1:
        clean_val = clean_val.replace(',', '')
    elif '.' in clean_val and ',' in clean_val:
        if clean_val.find('.') < clean_val.find(','):
            # 1.234,56
            clean_val = clean_val.replace('.', '').replace(',', '.')
        else:
            # 1,234.56
            clean_val = clean_val.replace(',', '')
    elif ',' in clean_val:
        # Check if ',' is decimal or thousand separator
        parts = clean_val.split(',')
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            clean_val = clean_val.replace(',', '')
        else:
            clean_val = clean_val.replace(',', '.')

    try:
        dec = Decimal(clean_val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return dec
    except Exception:
        return None

def normalize_currency(currency_code: Optional[str], default: str = "VND") -> str:
    """Normalize currency code (e.g. 'đ', 'vnd' -> 'VND')."""
    if not currency_code:
        return default
    cur = str(currency_code).strip().upper()
    if cur in ("Đ", "VND", "VNĐ", "DONG", "ĐỒNG"):
        return "VND"
    if cur in ("USD", "$"):
        return "USD"
    return cur[:3]

def calculate_discounts(
    list_price: Optional[Decimal],
    sale_price: Optional[Decimal]
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Calculate (discount_percent, discount_amount).
    """
    if list_price is None or sale_price is None:
        return None, None
        
    if list_price > sale_price and list_price > Decimal("0"):
        amount = (list_price - sale_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        percent = ((amount / list_price) * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return percent, amount
        
    return None, None
