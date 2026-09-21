import re
import unicodedata
from typing import Optional, List, Tuple

# Explicit alias dictionary: key -> (standard_name, location_type, parent_standard_name)
LOCATION_ALIASES = {
    # Ho Chi Minh City
    "tp.hồ chí minh": ("TP. Hồ Chí Minh", "Province", None),
    "tp. hồ chí minh": ("TP. Hồ Chí Minh", "Province", None),
    "tphcm": ("TP. Hồ Chí Minh", "Province", None),
    "tp hcm": ("TP. Hồ Chí Minh", "Province", None),
    "hồ chí minh": ("TP. Hồ Chí Minh", "Province", None),
    "sài gòn": ("TP. Hồ Chí Minh", "Province", None),
    "sai gon": ("TP. Hồ Chí Minh", "Province", None),
    "hcm": ("TP. Hồ Chí Minh", "Province", None),

    # Ha Noi
    "hà nội": ("Hà Nội", "Province", None),
    "ha noi": ("Hà Nội", "Province", None),
    "thủ đô hà nội": ("Hà Nội", "Province", None),

    # Da Nang
    "đà nẵng": ("Đà Nẵng", "Province", None),
    "da nang": ("Đà Nẵng", "Province", None),

    # Can Tho
    "cần thơ": ("Cần Thơ", "Province", None),
    "can tho": ("Cần Thơ", "Province", None),

    # Hai Phong
    "hải phòng": ("Hải Phòng", "Province", None),
    "hai phong": ("Hải Phòng", "Province", None),

    # Other common provinces / destinations
    "nha trang": ("Nha Trang", "City", "Khánh Hòa"),
    "khánh hòa": ("Khánh Hòa", "Province", None),
    "đà lạt": ("Đà Lạt", "City", "Lâm Đồng"),
    "lâm đồng": ("Lâm Đồng", "Province", None),
    "phú quốc": ("Phú Quốc", "City", "Kiên Giang"),
    "kiên giang": ("Kiên Giang", "Province", None),
    "rạch giá": ("Rạch Giá", "City", "Kiên Giang"),
    "long xuyên": ("Long Xuyên", "City", "An Giang"),
    "an giang": ("An Giang", "Province", None),
    "huế": ("Huế", "City", "Thừa Thiên Huế"),
    "thừa thiên huế": ("Thừa Thiên Huế", "Province", None),
    "hạ long": ("Hạ Long", "City", "Quảng Ninh"),
    "quảng ninh": ("Quảng Ninh", "Province", None),
    "sapa": ("Sa Pa", "City", "Lào Cai"),
    "sa pa": ("Sa Pa", "City", "Lào Cai"),
    "lào cai": ("Lào Cai", "Province", None),
    "hà giang": ("Hà Giang", "Province", None),
    "cao bằng": ("Cao Bằng", "Province", None),
    "bắc kạn": ("Bắc Kạn", "Province", None),
    "lạng sơn": ("Lạng Sơn", "Province", None),
    "ninh bình": ("Ninh Bình", "Province", None),
    "quảng bình": ("Quảng Bình", "Province", None),
    "quy nhơn": ("Quy Nhơn", "City", "Bình Định"),
    "bình định": ("Bình Định", "Province", None),
    "vũng tàu": ("Vũng Tàu", "City", "Bà Rịa - Vũng Tàu"),
    "bà rịa vũng tàu": ("Bà Rịa - Vũng Tàu", "Province", None),
    "bà rịa - vũng tàu": ("Bà Rịa - Vũng Tàu", "Province", None),
    "côn đảo": ("Côn Đảo", "District", "Bà Rịa - Vũng Tàu"),
    "mũi né": ("Mũi Né", "Ward", "Bình Thuận"),
    "phan thiết": ("Phan Thiết", "City", "Bình Thuận"),
    "bình thuận": ("Bình Thuận", "Province", None),
    "hội an": ("Hội An", "City", "Quảng Nam"),
    "quảng nam": ("Quảng Nam", "Province", None),

    # International destinations
    "thái lan": ("Thái Lan", "Country", None),
    "bangkok": ("Bangkok", "City", "Thái Lan"),
    "singapore": ("Singapore", "Country", None),
    "malaysia": ("Malaysia", "Country", None),
    "kuala lumpur": ("Kuala Lumpur", "City", "Malaysia"),
    "trung quốc": ("Trung Quốc", "Country", None),
    "bắc kinh": ("Bắc Kinh", "City", "Trung Quốc"),
    "thượng hải": ("Thượng Hải", "City", "Trung Quốc"),
    "tây an": ("Tây An", "City", "Trung Quốc"),
    "hồng kông": ("Hồng Kông", "Region", "Trung Quốc"),
    "nhật bản": ("Nhật Bản", "Country", None),
    "tokyo": ("Tokyo", "City", "Nhật Bản"),
    "osaka": ("Osaka", "City", "Nhật Bản"),
    "hàn quốc": ("Hàn Quốc", "Country", None),
    "seoul": ("Seoul", "City", "Hàn Quốc"),
    "đài loan": ("Đài Loan", "Region", None),
    "đài bắc": ("Đài Bắc", "City", "Đài Loan"),
    "châu âu": ("Châu Âu", "Continent", None),
    "châu á": ("Châu Á", "Continent", None),
    "châu mỹ": ("Châu Mỹ", "Continent", None),
    "châu phi": ("Châu Phi", "Continent", None),
    "châu úc": ("Châu Úc", "Continent", None),
    "mỹ": ("Hoa Kỳ", "Country", None),
    "hoa kỳ": ("Hoa Kỳ", "Country", None),
    "pháp": ("Pháp", "Country", None),
    "paris": ("Paris", "City", "Pháp"),
}

# Labels to ignore / strip
EXCLUDE_LOCATION_LABELS = {
    "tour trong nước",
    "tour nước ngoài",
    "tour miền bắc",
    "tour miền trung",
    "tour miền nam",
    "tour miền tây",
    "tour đông bắc",
    "tour tây bắc",
    "vòng cung đông bắc",
    "đông tây bắc",
    "tết nguyên đán",
    "tết âm lịch",
    "tour tết",
    "trong nước",
    "nước ngoài",
    "khởi hành hàng tuần",
}

def normalize_location_name(raw_name: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns (standard_name, location_type, parent_name).
    If no alias match is found, returns clean title-cased name with type 'Destination'.
    """
    if not raw_name:
        return None, None, None
        
    cleaned = unicodedata.normalize('NFC', str(raw_name)).strip()
    # Remove surrounding quotes, dashes
    cleaned = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', cleaned).strip()
    if not cleaned:
        return None, None, None
        
    lower = cleaned.lower()
    if lower in EXCLUDE_LOCATION_LABELS:
        return None, None, None
        
    for excl in EXCLUDE_LOCATION_LABELS:
        if excl in lower:
            # Check if whole string is an exclusion pattern
            cleaned_sub = re.sub(r'(?i)\b' + re.escape(excl) + r'\b', '', cleaned).strip(' ,-–')
            if not cleaned_sub:
                return None, None, None
            cleaned = cleaned_sub
            lower = cleaned.lower()

    if lower in LOCATION_ALIASES:
        return LOCATION_ALIASES[lower]

    return cleaned, "Destination", None

def clean_destination_candidates(raw_str_or_list) -> List[str]:
    """
    Given a list or comma/hyphen separated string of destination names,
    split, clean, filter out exclusions, and return deduplicated standard names.
    """
    if not raw_str_or_list:
        return []
        
    raw_tokens = []
    if isinstance(raw_str_or_list, list):
        for item in raw_str_or_list:
            if isinstance(item, str):
                raw_tokens.extend(re.split(r'[,–\-\|]', item))
            elif isinstance(item, dict) and "name" in item:
                raw_tokens.append(item["name"])
    elif isinstance(raw_str_or_list, str):
        raw_tokens = re.split(r'[,–\-\|]', raw_str_or_list)
        
    results = []
    seen = set()
    for tok in raw_tokens:
        tok = tok.strip()
        if not tok:
            continue
        std_name, _, _ = normalize_location_name(tok)
        if std_name and std_name.lower() not in seen:
            seen.add(std_name.lower())
            results.append(std_name)
            
    return results
