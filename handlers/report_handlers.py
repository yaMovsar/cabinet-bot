import os
import logging
from datetime import date, timedelta

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile

from database import (
    get_all_workers, get_all_workers_daily_summary,
    get_admin_monthly_detailed_all, get_worker_categories,
    get_worker_monthly_details, get_worker_full_stats
)
from states import ReportWorker, MonthlySummaryWorker, SalaryPayout
from utils import (
    format_date, format_date_short, send_long_message, MONTHS_RU,
    format_salary_block, format_work_summary
)
from handlers.filters import StaffFilter, AdminFilter
from reports import generate_monthly_report, generate_worker_report, generate_salary_report

router = Router()


@router.message(F.text == "📁 Сводка день", StaffFilter())
async def summary_day(message: types.Message, state: FSMContext):
    await state.clear()
    summary = await get_all_workers_daily_summary()
    text = f"📁 {date.today().strftime('%d.%m.%Y')}:\n\n"
    total = 0
    for tid, name, dt in summary:
        cats = await get_worker_categories(tid)
        ce = "".join([c[2] for c in cats]) if cats else ""
        icon = '✅' if dt > 0 else '❌'
        text += f"{icon} {ce}{name}: {int(dt)} руб\n"
        total += dt
    text += f"\n💰 Итого: {int(total)} руб"
    await message.answer(text)


# ✅ НОВОЕ: Сводка за месяц с выбором работника
@router.message(F.text == "📁 Сводка месяц", StaffFilter())
async def summary_month_choose_worker(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    
    if not workers:
        await message.answer("📭 Нет работников.")
        return
    
    today = date.today()
    buttons = []
    
    # Кнопка "Все работники" для Excel отчёта
    buttons.append([InlineKeyboardButton(
        text="📊 Все работники (краткая сводка)",
        callback_data="msw:all"
    )])
    
    # Кнопки для каждого работника
    for tid, name in workers:
        stats = await get_worker_full_stats(tid, today.year, today.month)
        earned = int(stats['earned'])
        cats = await get_worker_categories(tid)
        ce = "".join([c[2] for c in cats]) if cats else ""
        
        if earned > 0:
            buttons.append([InlineKeyboardButton(
                text=f"👤 {ce}{name} — {earned} руб",
                callback_data=f"msw:{tid}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=f"👤 {ce}{name} — нет записей",
                callback_data=f"msw:{tid}"
            )])
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="msw:cancel")])
    
    await message.answer(
        f"📊 Сводка за {MONTHS_RU[today.month]} {today.year}\n\n"
        f"Выберите работника:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(MonthlySummaryWorker.choosing_worker)


@router.callback_query(F.data.startswith("msw:"), MonthlySummaryWorker.choosing_worker)
async def monthly_summary_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    # Отвечаем сразу: сводка считается дольше, чем живёт callback query
    await callback.answer()

    value = callback.data.split(":")[1]
    today = date.today()

    if value == "cancel":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
        return
    
    if value == "all":
        # Краткая сводка по всем работникам
        await callback.message.edit_text("⏳ Формирую сводку...")
        
        workers = await get_all_workers()
        text = f"📊 {MONTHS_RU[today.month].upper()} {today.year} — КРАТКАЯ СВОДКА\n\n"
        grand_total = 0
        
        for tid, name in workers:
            stats = await get_worker_full_stats(tid, today.year, today.month)
            earned = stats['earned']
            cats = await get_worker_categories(tid)
            ce = "".join([c[2] for c in cats]) if cats else ""
            
            if earned > 0:
                text += f"✅ {ce}{name}\n"
                text += f"   💰 Заработано: {int(earned)} руб\n"
                text += f"   📅 Дней: {stats['work_days']}\n"
                if stats['advances'] > 0:
                    text += f"   💳 Авансы: {int(stats['advances'])} руб\n"
                if stats['penalties'] > 0:
                    text += f"   ⚠️ Штрафы: {int(stats['penalties'])} руб\n"
                text += f"   📊 Остаток: {int(stats['balance'])} руб\n\n"
                grand_total += earned
            else:
                text += f"❌ {ce}{name} — нет записей\n\n"
        
        text += f"━━━━━━━━━━━━━━━━━━━\n"
        text += f"💰 ОБЩИЙ ФОНД: {int(grand_total)} руб"
        
        await send_long_message(callback.message, text)
        await state.clear()
        return
    
    # Детальная сводка по конкретному работнику
    worker_id = int(value)
    workers = await get_all_workers()
    worker_name = next((n for t, n in workers if t == worker_id), "Работник")
    
    await callback.message.edit_text(f"⏳ Формирую сводку для {worker_name}...")
    
    # Получаем детальную статистику
    details = await get_worker_monthly_details(worker_id, today.year, today.month)
    stats = await get_worker_full_stats(worker_id, today.year, today.month)
    cats = await get_worker_categories(worker_id)
    ce = "".join([c[2] for c in cats]) if cats else ""
    
    if not details:
        text = f"📭 {ce}{worker_name} — нет записей за {MONTHS_RU[today.month]} {today.year}"
        await callback.message.edit_text(text)
        await state.clear()
        return
    
    text = f"📊 {ce}{worker_name}\n"
    text += f"📅 {MONTHS_RU[today.month]} {today.year}\n\n"
    
    current_cat = ""
    cat_total = 0
    
    for pl_name, c_emoji, c_name, qty, price, total, price_type in details:
        if c_name != current_cat:
            if current_cat != "":
                text += f"   📊 Итого: {int(cat_total)} руб\n\n"
            current_cat = c_name
            cat_total = 0
            text += f"{c_emoji} {c_name}:\n"
        
        unit_label = "м²" if price_type == "square" else "шт"
        qty_display = f"{qty:.2f}" if price_type == "square" else str(int(qty))
        text += f"   ▪️ {pl_name}: {qty_display} {unit_label} x {int(price)} руб = {int(total)} руб\n"
        cat_total += total
    
    if current_cat != "":
        text += f"   📊 Итого: {int(cat_total)} руб\n"
    
    text += f"\n━━━━━━━━━━━━━━━━━━━\n"
    text += format_salary_block(stats)

    if stats['work_days'] > 0:
        avg = stats['earned'] / stats['work_days']
        text += f"\n📈 Среднее в день: {int(avg):,} руб"

    await send_long_message(callback.message, text)
    await state.clear()


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
    # Отвечаем сразу: генерация Excel дольше, чем живёт callback query
    await callback.answer()

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


# ==================== ВЫДАЧА ЗАРПЛАТЫ ====================

def _salary_month_kb() -> InlineKeyboardMarkup:
    today = date.today()
    buttons = []
    for i in range(4):
        if today.month - i <= 0:
            m = today.month - i + 12
            y = today.year - 1
        else:
            m = today.month - i
            y = today.year
        label = f"📅 {MONTHS_RU[m]} {y}" + (" (текущий)" if i == 0 else "")
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"sal_month:{y}:{m}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="sal_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "💸 Выдать зарплату", AdminFilter())
async def salary_payout_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💸 Выдача зарплаты\n\nЗа какой месяц формируем ведомость?",
        reply_markup=_salary_month_kb()
    )
    await state.set_state(SalaryPayout.choosing_month)


@router.callback_query(F.data == "sal_cancel", SalaryPayout.choosing_month)
async def salary_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("sal_month:"), SalaryPayout.choosing_month)
async def salary_month_chosen(callback: types.CallbackQuery, state: FSMContext):
    # Отвечаем сразу: ведомость по всем работникам считается дольше,
    # чем живёт callback query — иначе финальный answer() падает с "query is too old"
    await callback.answer()

    _, year, month = callback.data.split(":")
    year, month = int(year), int(month)

    await callback.message.edit_text(f"⏳ Формирую ведомость за {MONTHS_RU[month]} {year}...")

    try:
        workers = await get_all_workers()
        workers_data = []

        for tid, name in workers:
            stats = await get_worker_full_stats(tid, year, month)

            # Пропускаем работников с нулевым балансом — в ведомость только тех, с кем есть расчёты
            if round(stats['balance'], 2) == 0:
                continue

            details = await get_worker_monthly_details(tid, year, month)

            # Формируем строку "Что сделал"
            work_summary = format_work_summary(details)

            workers_data.append({
                'name': name,
                'work_summary': work_summary,
                'earned': stats['earned'],
                'fixed_salary': stats['fixed_salary'],
                'bonus': stats['bonus'],
                'advances': stats['advances'],
                'penalties': stats['penalties'],
                'balance': stats['balance'],
            })

        if not workers_data:
            await callback.message.answer(
                f"📭 За {MONTHS_RU[month]} {year} нет работников с ненулевым балансом — выплачивать некому."
            )
            await state.clear()
            return

        # Сортируем по убыванию суммы к выплате (самые большие сверху)
        workers_data.sort(key=lambda x: x['balance'], reverse=True)

        fn = await generate_salary_report(year, month, workers_data)

        total_pay = sum(w['balance'] for w in workers_data)
        caption = (
            f"💸 Ведомость зарплаты\n"
            f"📅 {MONTHS_RU[month]} {year}\n\n"
            f"👥 Работников: {len(workers_data)}\n"
            f"💼 Итого к выплате: {int(total_pay):,} руб"
        )

        await callback.message.answer_document(
            FSInputFile(fn, filename=f"vedomost_{MONTHS_RU[month]}_{year}.xlsx"),
            caption=caption
        )
        os.remove(fn)

    except Exception as e:
        logging.exception(f"Salary report error: {e}")
        await callback.message.answer(f"❌ Ошибка: {e}")

    await state.clear()