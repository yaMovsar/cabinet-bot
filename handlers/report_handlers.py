import os
import logging
from datetime import date

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile

from database import (
    get_all_workers, get_all_workers_daily_summary,
    get_admin_monthly_detailed_all, get_worker_categories
)
from states import ReportWorker
from utils import format_date, format_date_short, send_long_message, MONTHS_RU
from handlers.filters import StaffFilter
from reports import generate_monthly_report, generate_worker_report

router = Router()


@router.message(F.text == "📋 Сводка день", StaffFilter())
async def summary_day(message: types.Message, state: FSMContext):
    await state.clear()
    summary = await get_all_workers_daily_summary()
    text = f"📋 {date.today().strftime('%d.%m.%Y')}:\n\n"
    total = 0
    for tid, name, dt in summary:
        cats = await get_worker_categories(tid)
        ce = "".join([c[2] for c in cats]) if cats else ""
        icon = '✅' if dt > 0 else '❌'
        text += f"{icon} {ce}{name}: {int(dt)} руб\n"
        total += dt
    text += f"\n💰 Итого: {int(total)} руб"
    await message.answer(text)


@router.message(F.text == "📋 Сводка месяц", StaffFilter())
async def summary_month(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    details = await get_admin_monthly_detailed_all(today.year, today.month)
    if not details:
        await message.answer("📭 Нет данных за этот месяц.")
        return

    text = f"📊 {MONTHS_RU[today.month].upper()} {today.year} — ПОЛНЫЙ ОТЧЁТ\n\n"
    current_worker = None
    current_category = None
    current_date = None
    worker_total = 0
    cat_total = 0
    day_total = 0
    grand_total = 0
    worker_days = set()

    # ✅ ИСПРАВЛЕНО: добавлен price_type в распаковку
    for tid, wname, cname, cemoji, wdate, pname, qty, price, total, price_type in details:
        if wname != current_worker:
            if current_date is not None:
                text += f"            💰 День: {int(day_total)} руб\n"
            if current_category is not None:
                text += f"      📊 Категория: {int(cat_total)} руб\n"
            if current_worker is not None:
                text += f"   ━━━━━━━━━━━━━━\n"
                text += f"   📊 Дней: {len(worker_days)} | 💰 Итого: {int(worker_total)} руб\n\n"
                grand_total += worker_total
            current_worker = wname
            current_category = None
            current_date = None
            worker_total = 0
            cat_total = 0
            day_total = 0
            worker_days = set()
            cats = await get_worker_categories(tid)
            ce = "".join([c[2] for c in cats]) if cats else ""
            text += f"👤 {wname} {ce}\n"

        if cname != current_category:
            if current_date is not None:
                text += f"            💰 День: {int(day_total)} руб\n"
                day_total = 0
            if current_category is not None:
                text += f"      📊 Категория: {int(cat_total)} руб\n\n"
            current_category = cname
            current_date = None
            cat_total = 0
            text += f"   {cemoji} {cname}:\n"

        if wdate != current_date:
            if current_date is not None:
                text += f"            💰 День: {int(day_total)} руб\n"
            text += f"      📅 {format_date_short(wdate)}:\n"
            current_date = wdate
            day_total = 0
            worker_days.add(wdate)

        # ✅ УЛУЧШЕНО: добавлен вывод единиц измерения
        unit_label = "м²" if price_type == "square" else "шт"
        qty_display = f"{qty:.2f}" if price_type == "square" else str(int(qty))
        text += f"         ▫️ {pname}: {qty_display} {unit_label} x {int(price)} руб = {int(total)} руб\n"
        worker_total += total
        cat_total += total
        day_total += total

    if current_date is not None:
        text += f"            💰 День: {int(day_total)} руб\n"
    if current_category is not None:
        text += f"      📊 Категория: {int(cat_total)} руб\n"
    if current_worker is not None:
        text += f"   ━━━━━━━━━━━━━━\n"
        text += f"   📊 Дней: {len(worker_days)} | 💰 Итого: {int(worker_total)} руб\n\n"
        grand_total += worker_total

    text += f"━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 ОБЩИЙ ФОНД: {int(grand_total)} руб"
    await send_long_message(message, text)


@router.message(F.text == "📥 Отчёт месяц", StaffFilter())
async def report_month(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⏳ Формирую...")
    try:
        today = date.today()
        fn = await generate_monthly_report(today.year, today.month)
        await message.answer_document(FSInputFile(fn), caption="📊 Отчёт за месяц")
        os.remove(fn)
    except Exception as e:
        logging.exception(f"Report error: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message(F.text == "📥 Отчёт работник", StaffFilter())
async def report_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n}", callback_data=f"rw:{t}")] for t, n in workers]
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(ReportWorker.choosing_worker)


@router.callback_query(F.data.startswith("rw:"), ReportWorker.choosing_worker)
async def report_worker_gen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    name = next((n for t, n in workers if t == wid), "Работник")
    await callback.message.edit_text("⏳ Формирую...")
    try:
        today = date.today()
        fn = await generate_worker_report(wid, name, today.year, today.month)
        await callback.message.answer_document(FSInputFile(fn), caption=f"📊 {name}")
        os.remove(fn)
    except Exception as e:
        logging.exception(f"Report error: {e}")
        await callback.message.answer(f"❌ Ошибка: {e}")
    await state.clear()
    await callback.answer()