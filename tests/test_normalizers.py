from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

from etl.normalizers.text import clean_text, strip_html, normalize_id
from etl.normalizers.datetime import parse_datetime, parse_date
from etl.normalizers.currency import parse_decimal, normalize_currency, calculate_discounts
from etl.normalizers.location import normalize_location_name, clean_destination_candidates

def test_normalize_id():
    assert normalize_id(3082.0) == "3082"
    assert normalize_id("3082.0") == "3082"
    assert normalize_id(3082) == "3082"
    assert normalize_id("afd604f4-489f-4e39") == "afd604f4-489f-4e39"
    assert normalize_id(None) is None

def test_strip_html():
    raw = "<p>Tour <b>Hạ Long</b> 3N2Đ<br>Giá rẻ &amp; hấp dẫn</p>"
    cleaned = strip_html(raw)
    assert "<b>" not in cleaned
    assert "&amp;" not in cleaned
    assert "Hạ Long" in cleaned
    assert "&" in cleaned

def test_clean_text_unicode_nfc():
    # Combining diacritics vs precomposed
    composed = "Hà Nội"
    decomposed = "Ha\u0300 N\u00f4\u0323i"
    assert clean_text(decomposed) == composed

def test_clean_text_preserve_newlines():
    text = "Ngày 1: Hà Nội\n\n\n\nNgày 2: Hạ Long"
    cleaned = clean_text(text, preserve_newlines=True)
    assert "Ngày 1: Hà Nội\n\nNgày 2: Hạ Long" in cleaned

def test_parse_datetime_iso():
    dt_str = "2026-09-19T12:55:07.272412+00:00"
    dt = parse_datetime(dt_str)
    assert dt is not None
    assert dt.year == 2026

def test_parse_datetime_date_only():
    dt_str = "23/09/2026"
    dt = parse_datetime(dt_str)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 9
    assert dt.day == 23
    assert dt.hour == 0
    assert dt.tzinfo is not None

def test_parse_decimal_clean():
    assert parse_decimal("19.990.000đ") == Decimal("19990000.00")
    assert parse_decimal("1234.50") == Decimal("1234.50")
    assert parse_decimal("1,234,567.89") == Decimal("1234567.89")
    assert parse_decimal(None) is None
    assert parse_decimal("") is None

def test_calculate_discounts():
    list_price = Decimal("10000000.00")
    sale_price = Decimal("8000000.00")
    pct, amt = calculate_discounts(list_price, sale_price)
    assert amt == Decimal("2000000.00")
    assert pct == Decimal("20.0000")

def test_normalize_location_name():
    std, loc_type, parent = normalize_location_name("Sài Gòn")
    assert std == "TP. Hồ Chí Minh"
    assert loc_type == "Province"

    std2, _, _ = normalize_location_name("Hà Nội")
    assert std2 == "Hà Nội"

    std3, _, _ = normalize_location_name("Tour Trong Nước")
    assert std3 is None

def test_clean_destination_candidates():
    raw = ["Phú Quốc, Kiên Giang, Tour Miền Tây, Tour Trong Nước", "Hà Nội"]
    cleaned = clean_destination_candidates(raw)
    assert "Phú Quốc" in cleaned
    assert "Kiên Giang" in cleaned
    assert "Hà Nội" in cleaned
    assert "Tour Trong Nước" not in cleaned
