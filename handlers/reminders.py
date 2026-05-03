from datetime import datetime

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import get_reminder_settings, update_reminder_settings
from states import AdminReminderSettings
from keyboards import get_admin_keyboard
from handlers.filters import AdminFilter

router = Router()

# Ссылка на scheduler — будет установлена из bot.py
scheduler = None


def set_scheduler(sched):
    global scheduler
    scheduler = sched


# ==================== НАСТРОЙКА НАПОМИНАНИЙ ====================

@router.message(F.text == "⏰ Напоминания", AdminFilter())
async def reminder_settings_menu(message: types.Message, state: FSMContext):
    await state.clear()
    settings = await get_reminder_settings()

    ev_status = "✅" if settings['evening_enabled'] else "❌"
    lt_status = "✅" if settings['late_enabled'] else "❌"
    rp_status = "✅" if settings['report_enabled'] else "❌"

    text = (
        "⏰ Настройка напоминаний\n\n"
        f"{ev_status} Вечернее: {settings['evening_hour']:02d}:{settings['evening_minute']:02d}\n"
        f"{lt_status} Позднее: {settings['late_hour']:02d}:{settings['late_minute']:02d}\n"
        f"{rp_status} Отчёт админу: {settings['report_hour']:02d}:{settings['report_minute']:02d}\n"
        f"\nОбновлено: {datetime.now().strftime('%H:%M:%S')}"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['evening_enabled'] else '🟢'} Вечернее {'выкл' if settings['evening_enabled'] else 'вкл'}",
            callback_data="rem:toggle_evening"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['late_enabled'] else '🟢'} Позднее {'выкл' if settings['late_enabled'] else 'вкл'}",
            callback_data="rem:toggle_late"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['report_enabled'] else '🟢'} Отчёт {'выкл' if settings['report_enabled'] else 'вкл'}",
            callback_data="rem:toggle_report"
        )],
        [InlineKeyboardButton(text="🕐 Время вечернего", callback_data="rem:time_evening")],
        [InlineKeyboardButton(text="🕐 Время позднего", callback_data="rem:time_late")],
        [InlineKeyboardButton(text="🕐 Время отчёта", callback_data="rem:time_report")],
        [InlineKeyboardButton(text="🔄 Применить", callback_data="rem:apply")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="rem:back")],
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminReminderSettings.main_menu)


@router.callback_query(F.data.startswith("rem:"), AdminReminderSettings.main_menu)
async def reminder_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    settings = await get_reminder_settings()

    if action == "toggle_evening":
        new_val = not settings['evening_enabled']
        await update_reminder_settings(evening_enabled=int(new_val))
        await callback.answer(f"Вечернее: {'ВКЛ' if new_val else 'ВЫКЛ'}")
    elif action == "toggle_late":
        new_val = not settings['late_enabled']
        await update_reminder_settings(late_enabled=int(new_val))
        await callback.answer(f"Позднее: {'ВКЛ' if new_val else 'ВЫКЛ'}")
    elif action == "toggle_report":
        new_val = not settings['report_enabled']
        await update_reminder_settings(report_enabled=int(new_val))
        await callback.answer(f"Отчёт: {'ВКЛ' if new_val else 'ВЫКЛ'}")
    elif action in ("time_evening", "time_late", "time_report"):
        await state.update_data(time_target=action.replace("time_", ""))
        await callback.message.edit_text("Введите время в формате ЧЧ:ММ\n\nНапример: 18:30")
        await state.set_state(AdminReminderSettings.entering_time)
        await callback.answer()
        return
    elif action == "apply":
        # Вызываем reschedule из bot.py через глобальную функцию
        if scheduler:
            from bot import reschedule_reminders
            await reschedule_reminders()
        await callback.answer("✅ Расписание обновлено!", show_alert=True)
    elif action == "back":
        await state.clear()
        await callback.message.edit_text("👌 Ок")
        await callback.answer()
        return

    # Обновляем меню
    settings = await get_reminder_settings()
    ev_status = "✅" if settings['evening_enabled'] else "❌"
    lt_status = "✅" if settings['late_enabled'] else "❌"
    rp_status = "✅" if settings['report_enabled'] else "❌"

    text = (
        f"⏰ Настройка напоминаний\n\n"
        f"{ev_status} Вечернее: {settings['evening_hour']:02d}:{settings['evening_minute']:02d}\n"
        f"{lt_status} Позднее: {settings['late_hour']:02d}:{settings['late_minute']:02d}\n"
        f"{rp_status} Отчёт админу: {settings['report_hour']:02d}:{settings['report_minute']:02d}\n"
        f"\nОбновлено: {datetime.now().strftime('%H:%M:%S')}"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['evening_enabled'] else '🟢'} Вечернее {'выкл' if settings['evening_enabled'] else 'вкл'}",
            callback_data="rem:toggle_evening"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['late_enabled'] else '🟢'} Позднее {'выкл' if settings['late_enabled'] else 'вкл'}",
            callback_data="rem:toggle_late"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['report_enabled'] else '🟢'} Отчёт {'выкл' if settings['report_enabled'] else 'вкл'}",
            callback_data="rem:toggle_report"
        )],
        [InlineKeyboardButton(text="🕐 Время вечернего", callback_data="rem:time_evening")],
        [InlineKeyboardButton(text="🕐 Время позднего", callback_data="rem:time_late")],
        [InlineKeyboardButton(text="🕐 Время отчёта", callback_data="rem:time_report")],
        [InlineKeyboardButton(text="🔄 Применить", callback_data="rem:apply")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="rem:back")],
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        pass


@router.message(AdminReminderSettings.entering_time)
async def reminder_time_entered(message: types.Message, state: FSMContext):
    try:
        parts = message.text.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("❌ Формат: ЧЧ:ММ (например 18:30)")
        return

    data = await state.get_data()
    target = data["time_target"]

    if target == "evening":
        await update_reminder_settings(evening_hour=hour, evening_minute=minute)
    elif target == "late":
        await update_reminder_settings(late_hour=hour, late_minute=minute)
    elif target == "report":
        await update_reminder_settings(report_hour=hour, report_minute=minute)

    await message.answer(
        f"✅ Время установлено: {hour:02d}:{minute:02d}\n\n"
        f"Нажмите 🔄 Применить чтобы обновить расписание.",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()