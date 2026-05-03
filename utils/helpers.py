import logging
from aiogram import types


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