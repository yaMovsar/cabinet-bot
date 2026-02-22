from datetime import datetime, date

MONTHS_RU = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def format_date(iso_date: str) -> str:
    """2025-01-15 -> 15.01.2025"""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return iso_date


def format_date_short(iso_date: str) -> str:
    """2025-01-15 -> 15.01"""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m")
    except Exception:
        return iso_date


def parse_user_date(text: str):
    """15.01.2025 -> date(2025, 1, 15)"""
    try:
        parts = text.strip().split(".")
        if len(parts) != 3:
            return None
        return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        return None


def format_money(amount: float) -> str:
    """12345.67 -> 12 345 руб"""
    return f"{int(amount):,} руб".replace(",", " ")