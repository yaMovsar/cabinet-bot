import logging
from aiogram import types


def format_salary_block(stats: dict, work_days: int = None) -> str:
    """Форматирует блок расчёта зарплаты: сдельно + оклад + премия → начислено → к выплате"""
    earned = int(stats['earned'])
    fixed = int(stats.get('fixed_salary', 0))
    bonus = int(stats.get('bonus', 0))
    advances = int(stats.get('advances', 0))
    penalties = int(stats.get('penalties', 0))
    total_accrued = earned + fixed + bonus
    to_pay = int(stats['balance'])

    days = work_days if work_days is not None else stats.get('work_days', 0)
    text = f"📅 Рабочих дней: {days}\n\n"
    text += f"💰 Сдельно: {earned:,} руб\n"
    if fixed > 0:
        text += f"🏢 Оклад: +{fixed:,} руб\n"
    if bonus > 0:
        text += f"🏆 Премия: +{bonus:,} руб\n"
    if fixed > 0 or bonus > 0:
        text += f"─────────────────\n"
        text += f"📋 Начислено: {total_accrued:,} руб\n"
    if advances > 0:
        text += f"💳 Авансы: -{advances:,} руб\n"
    if penalties > 0:
        text += f"⚠️ Штрафы: -{penalties:,} руб\n"
    text += f"─────────────────\n"
    text += f"✅ К выплате: {to_pay:,} руб"
    return text


async def send_long_message(target, text: str, parse_mode=None, max_len=4000):
    """Отправка длинного сообщения частями"""
    if len(text) <= max_len:
        try:
            await target.answer(text, parse_mode=parse_mode)
        except Exception:
            await target.answer(text, parse_mode=None)
        return

    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            parts.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        parts.append(current)

    for part in parts:
        if part.strip():
            try:
                await target.answer(part, parse_mode=parse_mode)
            except Exception:
                await target.answer(part, parse_mode=None)


async def safe_edit_text(message: types.Message, text: str, reply_markup=None):
    """Безопасное редактирование сообщения"""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" not in str(e):
            logging.error(f"Edit error: {e}")