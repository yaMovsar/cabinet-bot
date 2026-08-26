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

# ==================== ТИПЫ РАБОТ ====================

SIDE_JOB_TYPE = 'custom'   # подработка/шабашка — работник вводит сумму в рублях
SIDE_JOB_NAME = 'Подработка'


def unit_of(price_type: str) -> str:
    """Единица измерения по типу расценки"""
    if price_type == 'square':
        return 'м²'
    if price_type == SIDE_JOB_TYPE:
        return '₽'
    return 'шт'


def format_qty(qty, price_type: str) -> str:
    """Количество в виде строки по типу расценки"""
    if price_type == 'square':
        return f"{float(qty):.2f}"
    if price_type == SIDE_JOB_TYPE:
        return f"{int(qty):,}".replace(",", " ")
    return str(int(qty))


def format_qty_unit(qty, price_type: str) -> str:
    """«12.50 м²» / «3 шт» / «5 000 ₽»"""
    return f"{format_qty(qty, price_type)} {unit_of(price_type)}"


# ==================== ЗАКРЫТИЕ МЕСЯЦА ====================

def month_key(value) -> tuple:
    """(год, месяц) из date или строки YYYY-MM-DD"""
    if isinstance(value, str):
        value = date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    return (value.year, value.month)


def is_month_open(value) -> bool:
    """Дата относится к текущему (ещё не закрытому) месяцу?"""
    try:
        return month_key(value) == month_key(date.today())
    except Exception:
        return False


def days_left_in_month(today=None) -> int:
    """Сколько дней осталось до конца месяца (0 = сегодня последний день)"""
    import calendar
    today = today or date.today()
    return calendar.monthrange(today.year, today.month)[1] - today.day


MONTH_CLOSED_TEXT = (
    "🔒 Прошлый месяц закрыт!\n\n"
    "Записи можно вносить только за текущий месяц.\n"
    "Если нужно добавить что-то за прошлый месяц — обратитесь к руководителю."
)
