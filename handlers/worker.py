from datetime import date, timedelta
import logging

from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID, MANAGER_IDS
from database import (
    get_price_list_for_worker, get_worker_categories,
    add_work, get_daily_total
)
from states import WorkEntry
from keyboards import make_date_picker, make_work_buttons
from utils import format_date, parse_user_date

router = Router()


@router.message(F.text == "📝 Записать работу")
async def start_work_entry(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list_for_worker(message.from_user.id)
    if not items:
        await message.answer("⚠️ Вам не назначены категории.")
        return
    await message.answer(
        "📅 За какой день записать работу?",
        reply_markup=make_date_picker("wdate", "cancel")
    )
    await state.set_state(WorkEntry.choosing_date)


@router.callback_query(F.data.startswith("wdate:"), WorkEntry.choosing_date)
async def work_date_chosen(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await callback.message.edit_text(
            "📅 Введите дату в формате ДД.ММ.ГГГГ\n\nНапример: 25.05.2025"
        )
        await state.set_state(WorkEntry.entering_custom_date)
        await callback.answer()
        return
    await state.update_data(work_date=value)
    await show_category_or_work(callback, state, value)
    await callback.answer()


@router.message(WorkEntry.entering_custom_date)
async def custom_date_entered(message: types.Message, state: FSMContext):
    chosen = parse_user_date(message.text)
    if not chosen:
        await message.answer("❌ Неверный формат!\nВведите дату как ДД.ММ.ГГГГ")
        return
    if chosen > date.today():
        await message.answer("❌ Нельзя записать на будущую дату!")
        return
    if chosen < date.today() - timedelta(days=90):
        await message.answer("❌ Нельзя записать дату старше 90 дней!")
        return

    chosen_date = chosen.isoformat()
    await state.update_data(work_date=chosen_date)
    # ... продолжение логики


async def show_category_or_work(callback, state, chosen_date):
    """Показать категории или сразу работы"""
    items = await get_price_list_for_worker(callback.from_user.id)
    worker_cats = await get_worker_categories(callback.from_user.id)

    if len(worker_cats) == 1:
        cat_code = worker_cats[0][0]
        cat_items = [i for i in items if i[3] == cat_code]
        buttons = make_work_buttons(cat_items)
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await callback.message.edit_text(
            f"📅 Дата: {format_date(chosen_date)}\n"
            f"📋 {worker_cats[0][2]} {worker_cats[0][1]}\n\nВыберите работу:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_work)
    else:
        buttons = []
        for cat_code, cat_name, cat_emoji in worker_cats:
            count = len([i for i in items if i[3] == cat_code])
            buttons.append([InlineKeyboardButton(
                text=f"{cat_emoji} {cat_name} ({count})",
                callback_data=f"wcat:{cat_code}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await callback.message.edit_text(
            f"📅 Дата: {format_date(chosen_date)}\n\n📂 Выберите категорию работ:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_category)


# ... остальные хендлеры для записи работы