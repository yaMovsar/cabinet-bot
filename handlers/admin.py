import logging
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID
from database import (
    add_category, get_categories, delete_category,
    add_price_item, get_price_list, update_price, delete_price_item_permanently,
    add_worker, get_all_workers, delete_worker, rename_worker,
    assign_category_to_worker, remove_category_from_worker,
    get_worker_categories, get_workers_in_category,
    get_worker_recent_entries, get_entry_by_id,
    delete_entry_by_id, update_entry_quantity,
    update_category, update_work_item, get_work_by_code
)

from states import (
    AdminAddCategory, AdminAddWork, AdminAddWorker,
    AdminAssignCategory, AdminRemoveCategory,
    AdminEditPrice, AdminRenameWorker,
    AdminDeleteCategory, AdminDeleteWork, AdminDeleteWorker,
    AdminManageEntries,
    AdminEditCategory, AdminEditWork
)

from keyboards import get_add_keyboard, get_edit_keyboard, get_delete_keyboard, get_info_keyboard
from utils import format_date, send_long_message
from handlers.filters import AdminFilter, StaffFilter

router = Router()


# ==================== КАТЕГОРИИ ====================

@router.message(F.text == "➕ Категория", AdminFilter())
async def add_cat_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Код категории (латиницей):")
    await state.set_state(AdminAddCategory.entering_code)


@router.message(AdminAddCategory.entering_code)
async def add_cat_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip().lower())
    await message.answer("Название:")
    await state.set_state(AdminAddCategory.entering_name)


@router.message(AdminAddCategory.entering_name)
async def add_cat_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Эмодзи (или - для 📦):")
    await state.set_state(AdminAddCategory.entering_emoji)


@router.message(AdminAddCategory.entering_emoji)
async def add_cat_emoji(message: types.Message, state: FSMContext):
    emoji = message.text.strip()
    if emoji == "-":
        emoji = "📦"
    data = await state.get_data()
    await add_category(data["code"], data["name"], emoji)
    await message.answer(f"✅ {emoji} {data['name']} ({data['code']})", reply_markup=get_add_keyboard())
    await state.clear()


@router.message(F.text == "📂 Категории", StaffFilter())
async def show_cats(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("📂 Пусто.")
        return
    text = "📂 Категории:\n\n"
    for code, name, emoji in cats:
        workers = await get_workers_in_category(code)
        w_str = ", ".join([w[1] for w in workers]) if workers else "—"
        all_items = await get_price_list()
        items = [i for i in all_items if i[4] == code]
        i_str = ", ".join([f"{i[1]}({int(i[2])} руб)" for i in items]) if items else "—"
        text += f"{emoji} {name} ({code})\n👥 {w_str}\n📋 {i_str}\n\n"
    await send_long_message(message, text)


# ==================== ВИД РАБОТЫ ====================

@router.message(F.text == "➕ Вид работы", AdminFilter())
async def add_work_start(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("⚠️ Сначала создайте категорию!")
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"awc:{c}")] for c, n, e in cats]
    await message.answer("Категория:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAddWork.choosing_category)


@router.callback_query(F.data.startswith("awc:"), AdminAddWork.choosing_category)
async def add_work_cat(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(category_code=callback.data.split(":")[1])
    await callback.message.edit_text("Код работы (латиницей):")
    await state.set_state(AdminAddWork.entering_code)
    await callback.answer()


@router.message(AdminAddWork.entering_code)
async def add_work_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip().lower())
    await message.answer("Название:")
    await state.set_state(AdminAddWork.entering_name)


@router.message(AdminAddWork.entering_name)
async def add_work_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    buttons = [
        [InlineKeyboardButton(text="📦 За штуку", callback_data="pt:unit")],
        [InlineKeyboardButton(text="📐 За м²", callback_data="pt:square")]
    ]
    await message.answer("Тип оплаты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAddWork.choosing_price_type)


@router.callback_query(F.data.startswith("pt:"), AdminAddWork.choosing_price_type)
async def add_work_price_type(callback: types.CallbackQuery, state: FSMContext):
    price_type = callback.data.split(":")[1]
    await state.update_data(price_type=price_type)
    unit_label = "м²" if price_type == "square" else "шт"
    await callback.message.edit_text(f"Расценка за 1 {unit_label} (число):")
    await state.set_state(AdminAddWork.entering_price)
    await callback.answer()


@router.message(AdminAddWork.entering_price)
async def add_work_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    price_type = data.get("price_type", "unit")
    await add_price_item(data["code"], data["name"], price, data["category_code"], price_type)
    unit_label = "м²" if price_type == "square" else "шт"
    await message.answer(
        f"✅ {data['code']} — {data['name']}\n💰 {int(price)} руб/{unit_label}",
        reply_markup=get_add_keyboard()
    )
    await state.clear()


# ==================== РАБОТНИК ====================

@router.message(F.text == "👤 Добавить работника", AdminFilter())
async def add_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Telegram ID (@userinfobot):")
    await state.set_state(AdminAddWorker.entering_id)


@router.message(AdminAddWorker.entering_id)
async def add_worker_id(message: types.Message, state: FSMContext):
    try:
        tid = int(message.text)
    except ValueError:
        await message.answer("❌ Число!")
        return
    await state.update_data(worker_id=tid)
    await message.answer("Имя:")
    await state.set_state(AdminAddWorker.entering_name)


@router.message(AdminAddWorker.entering_name)
async def add_worker_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await add_worker(data["worker_id"], message.text.strip())
    await message.answer(
        f"✅ {message.text.strip()} ({data['worker_id']})\n"
        f"Назначьте категории: ✏️ Редактировать → 🔗",
        reply_markup=get_add_keyboard()
    )
    await state.clear()


# ==================== ПЕРЕИМЕНОВАТЬ РАБОТНИКА ====================

@router.message(F.text == "✏️ Переименовать", AdminFilter())
async def rename_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n} ({t})", callback_data=f"rnw:{t}")] for t, n in workers]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Кого переименовать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminRenameWorker.choosing_worker)


@router.callback_query(F.data.startswith("rnw:"), AdminRenameWorker.choosing_worker)
async def rename_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    old_name = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, old_name=old_name)
    await callback.message.edit_text(f"👤 Текущее имя: {old_name}\n\nВведите новое имя:")
    await state.set_state(AdminRenameWorker.entering_name)
    await callback.answer()


@router.message(AdminRenameWorker.entering_name)
async def rename_worker_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_name = message.text.strip()
    await rename_worker(data["worker_id"], new_name)
    await message.answer(
        f"✅ Переименовано!\n\nБыло: {data['old_name']}\nСтало: {new_name}",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


# ==================== СПИСКИ ====================

@router.message(F.text == "👥 Работники", StaffFilter())
async def show_workers(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("👥 Пусто.")
        return
    text = "👥 Работники:\n\n"
    for tid, name in workers:
        cats = await get_worker_categories(tid)
        c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats]) if cats else "нет кат."
        text += f"▪️ {name} ({tid})\n   {c_str}\n\n"
    await send_long_message(message, text)


@router.message(F.text == "📄 Прайс-лист", StaffFilter())
async def show_pricelist(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("📄 Пусто.")
        return
    text = "📄 Прайс-лист:\n\n"
    cur = ""
    for code, name, price, price_type, cat_code, cat_name, cat_emoji in items:
        if cat_code != cur:
            cur = cat_code
            text += f"\n{cat_emoji} {cat_name}:\n"
        unit_label = "м²" if price_type == "square" else "шт"
        text += f"   ▪️ {code} — {name}: {int(price)} руб/{unit_label}\n"
    await send_long_message(message, text)


# ==================== НАЗНАЧИТЬ / УБРАТЬ КАТЕГОРИЮ ====================

@router.message(F.text == "🔗 Назначить кат.", AdminFilter())
async def assign_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = []
    for tid, name in workers:
        cats = await get_worker_categories(tid)
        c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats]) if cats else "—"
        buttons.append([InlineKeyboardButton(text=f"{name} [{c_str}]", callback_data=f"asw:{tid}")])
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAssignCategory.choosing_worker)


@router.callback_query(F.data.startswith("asw:"), AdminAssignCategory.choosing_worker)
async def assign_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    await state.update_data(worker_id=wid)
    cats = await get_categories()
    current = {c[0] for c in await get_worker_categories(wid)}
    available = [(c, n, e) for c, n, e in cats if c not in current]
    if not available:
        await callback.message.edit_text("✅ Все назначены!")
        await state.clear()
        await callback.answer()
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"asc:{c}")] for c, n, e in available]
    await callback.message.edit_text("Категория:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAssignCategory.choosing_category)
    await callback.answer()


@router.callback_query(F.data.startswith("asc:"), AdminAssignCategory.choosing_category)
async def assign_done(callback: types.CallbackQuery, state: FSMContext):
    cat = callback.data.split(":")[1]
    data = await state.get_data()
    await assign_category_to_worker(data["worker_id"], cat)
    workers = await get_all_workers()
    w = next((n for t, n in workers if t == data["worker_id"]), "?")
    cats = await get_categories()
    c = next((f"{e}{n}" for co, n, e in cats if co == cat), "?")
    await callback.message.edit_text(f"✅ {w} → {c}")
    await state.clear()
    await callback.answer()


@router.message(F.text == "🔓 Убрать кат.", AdminFilter())
async def rmcat_start(message: types.Message, state: FSMContext):
    await state.clear()
    buttons = []
    for tid, name in await get_all_workers():
        cats = await get_worker_categories(tid)
        if cats:
            c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats])
            buttons.append([InlineKeyboardButton(text=f"{name} [{c_str}]", callback_data=f"rcw:{tid}")])
    if not buttons:
        await message.answer("⚠️ Ни у кого нет категорий.")
        return
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminRemoveCategory.choosing_worker)


@router.callback_query(F.data.startswith("rcw:"), AdminRemoveCategory.choosing_worker)
async def rmcat_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    await state.update_data(worker_id=wid)
    cats = await get_worker_categories(wid)
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"rcc:{c}")] for c, n, e in cats]
    await callback.message.edit_text("Убрать:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminRemoveCategory.choosing_category)
    await callback.answer()


@router.callback_query(F.data.startswith("rcc:"), AdminRemoveCategory.choosing_category)
async def rmcat_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await remove_category_from_worker(data["worker_id"], callback.data.split(":")[1])
    await callback.message.edit_text("✅ Убрана!")
    await state.clear()
    await callback.answer()


# ==================== РАСЦЕНКА ====================

@router.message(F.text == "✏️ Расценка", AdminFilter())
async def edit_price_start(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("⚠️ Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{ce} {n} — {int(p)} руб",
                callback_data=f"ep:{c}")] for c, n, p, pt, cc, cn, ce in items]
    await message.answer("Позиция:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditPrice.choosing_item)


@router.callback_query(F.data.startswith("ep:"), AdminEditPrice.choosing_item)
async def edit_price_chosen(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(code=callback.data.split(":")[1])
    await callback.message.edit_text("Новая расценка:")
    await state.set_state(AdminEditPrice.entering_new_price)
    await callback.answer()


@router.message(AdminEditPrice.entering_new_price)
async def edit_price_done(message: types.Message, state: FSMContext):
    try:
        p = float(message.text.replace(",", "."))
        if p <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    await update_price(data["code"], p)
    await message.answer(f"✅ Расценка: {int(p)} руб", reply_markup=get_edit_keyboard())
    await state.clear()


# ==================== УДАЛЕНИЕ ====================

@router.message(F.text == "🗑 Уд. категорию", AdminFilter())
async def del_cat_start(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("📂 Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"dc:{c}")] for c, n, e in cats]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteCategory.choosing)


@router.callback_query(F.data.startswith("dc:"), AdminDeleteCategory.choosing)
async def del_cat_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    cats = await get_categories()
    info = next(((c, n, e) for c, n, e in cats if c == code), None)
    if not info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(code=code, name=info[1], emoji=info[2])
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdc:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdc:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить {info[2]} {info[1]}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteCategory.confirming)
    await callback.answer()


@router.callback_query(F.data.startswith("cdc:"), AdminDeleteCategory.confirming)
async def del_cat_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        await delete_category(data["code"])
        await callback.message.edit_text(f"✅ {data['emoji']} {data['name']} удалена!")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


@router.message(F.text == "🗑 Уд. работу", AdminFilter())
async def del_work_start(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("📄 Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{ce} {n} — {int(p)} руб",
                callback_data=f"dw:{c}")] for c, n, p, pt, cc, cn, ce in items]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWork.choosing)


@router.callback_query(F.data.startswith("dw:"), AdminDeleteWork.choosing)
async def del_work_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    items = await get_price_list()
    info = next(((c, n, p) for c, n, p, pt, cc, cn, ce in items if c == code), None)
    if not info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(code=code, name=info[1])
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdw:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdw:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить {info[1]} ({int(info[2])} руб)?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWork.confirming)
    await callback.answer()


@router.callback_query(F.data.startswith("cdw:"), AdminDeleteWork.confirming)
async def del_work_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        full = await delete_price_item_permanently(data["code"])
        msg = f"✅ {data['name']} удалён!" if full else f"✅ {data['name']} скрыт."
        await callback.message.edit_text(msg)
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


@router.message(F.text == "🗑 Уд. работника", AdminFilter())
async def del_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
    buttons = []
    for tid, name in await get_all_workers():
        if tid == ADMIN_ID:
            continue
        buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"dwk:{tid}")])
    if not buttons:
        await message.answer("⚠️ Некого удалять.")
        return
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWorker.choosing)


@router.callback_query(F.data.startswith("dwk:"), AdminDeleteWorker.choosing)
async def del_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    name = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=name)
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdwk:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdwk:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить {name}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWorker.confirming)
    await callback.answer()


@router.callback_query(F.data.startswith("cdwk:"), AdminDeleteWorker.confirming)
async def del_worker_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        await delete_worker(data["worker_id"])
        await callback.message.edit_text(f"✅ {data['worker_name']} удалён!")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cdel")
async def cancel_del(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()


# ==================== ЗАПИСИ РАБОТНИКОВ ====================

@router.message(F.text == "🔧 Записи работников", AdminFilter())
async def admin_entries_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n}", callback_data=f"ae_w:{t}")] for t, n in workers]
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminManageEntries.choosing_worker)


@router.callback_query(F.data.startswith("ae_w:"), AdminManageEntries.choosing_worker)
async def admin_entries_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    wname = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=wname)
    entries = await get_worker_recent_entries(wid, limit=20)
    if not entries:
        await callback.message.edit_text(f"📭 У {wname} нет записей.")
        await state.clear()
        await callback.answer()
        return
    text = f"📁 {wname}:\n\n"
    buttons = []
    current_date = ""
    for eid, name, qty, price, total, wdate, created, *_ in entries:
        if wdate != current_date:
            text += f"\n📅 {format_date(wdate)}:\n"
            current_date = wdate
        text += f"   📋 {name} x {int(qty)} = {int(total)} руб\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {name} x{int(qty)}={int(total)}руб ({wdate})",
            callback_data=f"ae_e:{eid}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ae_back")])
    await callback.message.edit_text(text + "\n\nВыберите запись:",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminManageEntries.viewing_entries)
    await callback.answer()


@router.callback_query(F.data.startswith("ae_e:"), AdminManageEntries.viewing_entries)
async def admin_entry_chosen(callback: types.CallbackQuery, state: FSMContext):
    eid = int(callback.data.split(":")[1])
    entry = await get_entry_by_id(eid)
    if not entry:
        await callback.answer("Не найдена", show_alert=True)
        return
    await state.update_data(entry_id=eid)
    price_type = entry[8] if len(entry) > 8 else "unit"
    unit_label = "м²" if price_type == "square" else "шт"
    qty_display = f"{entry[2]:.2f}" if price_type == "square" else str(int(entry[2]))
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить кол-во", callback_data="ae_act:edit")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="ae_act:delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ae_act:back")]
    ]
    await callback.message.edit_text(
        f"📦 {entry[1]}\n\n"
        f"👤 {entry[7]}\n"
        f"📅 {format_date(entry[5])}\n"
        f"🔢 Кол-во: {qty_display} {unit_label}\n"
        f"💵 Расценка: {int(entry[3])} руб/{unit_label}\n"
        f"💰 Сумма: {int(entry[4])} руб",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminManageEntries.choosing_action)
    await callback.answer()


@router.callback_query(F.data.startswith("ae_act:"), AdminManageEntries.choosing_action)
async def admin_entry_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    if action == "edit":
        await callback.message.edit_text("Введите новое количество:")
        await state.set_state(AdminManageEntries.entering_new_quantity)
    elif action == "delete":
        data = await state.get_data()
        entry = await get_entry_by_id(data["entry_id"])
        buttons = [
            [InlineKeyboardButton(text="✅ Да!", callback_data="ae_del:yes")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="ae_del:no")]
        ]
        await callback.message.edit_text(
            f"⚠️ Удалить?\n📦 {entry[1]} x {int(entry[2])} = {int(entry[4])} руб",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(AdminManageEntries.confirming_delete)
    elif action == "back":
        data = await state.get_data()
        entries = await get_worker_recent_entries(data["worker_id"], limit=20)
        text = f"📁 {data['worker_name']}:\n\n"
        buttons = []
        current_date = ""
        for eid, name, qty, price, total, wdate, created, *_ in entries:
            if wdate != current_date:
                text += f"\n📅 {format_date(wdate)}:\n"
                current_date = wdate
            text += f"   📋 {name} x {int(qty)} = {int(total)} руб\n"
            buttons.append([InlineKeyboardButton(
                text=f"📦 {name} x{int(qty)}={int(total)}руб",
                callback_data=f"ae_e:{eid}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ae_back")])
        await callback.message.edit_text(text + "\n\nВыберите:",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(AdminManageEntries.viewing_entries)
    await callback.answer()


@router.message(AdminManageEntries.entering_new_quantity)
async def admin_entry_new_qty(message: types.Message, state: FSMContext):
    try:
        new_qty = float(message.text.replace(",", "."))
        if new_qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    entry = await get_entry_by_id(data["entry_id"])
    if not entry:
        await message.answer("❌ Не найдена.")
        await state.clear()
        return
    old_qty = entry[2]
    old_total = entry[4]
    new_total = new_qty * entry[3]
    await update_entry_quantity(data["entry_id"], new_qty)
    price_type = entry[8] if len(entry) > 8 else "unit"
    unit_label = "м²" if price_type == "square" else "шт"
    await message.answer(
        f"✅ Изменено!\n\n📦 {entry[1]} ({entry[7]})\n"
        f"Было: {int(old_qty)} {unit_label} = {int(old_total)} руб\n"
        f"Стало: {int(new_qty)} {unit_label} = {int(new_total)} руб",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


@router.callback_query(F.data.startswith("ae_del:"), AdminManageEntries.confirming_delete)
async def admin_entry_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        deleted = await delete_entry_by_id(data["entry_id"])
        if deleted:
            await callback.message.edit_text(
                f"✅ Удалено: {deleted[1]} x {int(deleted[2])} = {int(deleted[3])} руб")
        else:
            await callback.message.edit_text("❌ Не найдена.")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "ae_back")
async def admin_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Ок")
    await callback.answer()


# ==================== РЕДАКТИРОВАНИЕ КАТЕГОРИИ ====================

@router.message(F.text == "✏️ Редактировать категорию", AdminFilter())
async def edit_category_start(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("📂 Нет категорий.")
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"ec:{c}")] for c, n, e in cats]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditCategory.choosing_category)


@router.callback_query(F.data.startswith("ec:"), AdminEditCategory.choosing_category)
async def edit_category_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    cats = await get_categories()
    cat_info = next(((c, n, e) for c, n, e in cats if c == code), None)
    if not cat_info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(cat_code=code, cat_name=cat_info[1], cat_emoji=cat_info[2])
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="ec_act:name")],
        [InlineKeyboardButton(text="🎨 Изменить эмодзи", callback_data="ec_act:emoji")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ec_act:back")]
    ]
    await callback.message.edit_text(
        f"Категория: {cat_info[2]} {cat_info[1]}\nКод: {code}\n\nЧто изменить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminEditCategory.choosing_action)
    await callback.answer()


@router.callback_query(F.data.startswith("ec_act:"), AdminEditCategory.choosing_action)
async def edit_category_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    if action == "name":
        data = await state.get_data()
        await callback.message.edit_text(f"Текущее: {data['cat_name']}\n\nВведите новое название:")
        await state.set_state(AdminEditCategory.entering_new_name)
    elif action == "emoji":
        data = await state.get_data()
        await callback.message.edit_text(f"Текущий: {data['cat_emoji']}\n\nВведите новый эмодзи:")
        await state.set_state(AdminEditCategory.entering_new_emoji)
    elif action == "back":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
    await callback.answer()


@router.message(AdminEditCategory.entering_new_name)
async def edit_category_new_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    data = await state.get_data()
    await update_category(data["cat_code"], new_name=new_name)
    await message.answer(
        f"✅ Название изменено!\nБыло: {data['cat_name']}\nСтало: {new_name}",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


@router.message(AdminEditCategory.entering_new_emoji)
async def edit_category_new_emoji(message: types.Message, state: FSMContext):
    new_emoji = message.text.strip()
    data = await state.get_data()
    await update_category(data["cat_code"], new_emoji=new_emoji)
    await message.answer(
        f"✅ Эмодзи изменён!\nБыло: {data['cat_emoji']}\nСтало: {new_emoji}",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


# ==================== РЕДАКТИРОВАНИЕ РАБОТЫ ====================

@router.message(F.text == "✏️ Редактировать работу", AdminFilter())
async def edit_work_start(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("📂 Нет категорий.")
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"ew_cat:{c}")] for c, n, e in cats]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditWork.choosing_category)


@router.callback_query(F.data.startswith("ew_cat:"), AdminEditWork.choosing_category)
async def edit_work_category_chosen(callback: types.CallbackQuery, state: FSMContext):
    cat_code = callback.data.split(":")[1]
    await state.update_data(category_code=cat_code)
    items = await get_price_list()
    cat_items = [i for i in items if i[4] == cat_code]
    if not cat_items:
        await callback.message.edit_text("📭 В этой категории нет работ.")
        await state.clear()
        await callback.answer()
        return
    buttons = []
    for code, name, price, price_type, *_ in cat_items:
        unit_label = "м²" if price_type == "square" else "шт"
        buttons.append([InlineKeyboardButton(
            text=f"{name} ({int(price)} руб/{unit_label})",
            callback_data=f"ew_work:{code}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ew_back")])
    await callback.message.edit_text("Выберите работу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditWork.choosing_work)
    await callback.answer()


@router.callback_query(F.data.startswith("ew_work:"), AdminEditWork.choosing_work)
async def edit_work_chosen(callback: types.CallbackQuery, state: FSMContext):
    work_code = callback.data.split(":")[1]
    work_info = await get_work_by_code(work_code)
    if not work_info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    code, name, price, price_type, cat_code, cat_name, cat_emoji = work_info
    await state.update_data(work_code=code, work_name=name, work_price=price, work_price_type=price_type)
    unit_label = "м²" if price_type == "square" else "шт"
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="ew_act:name")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data="ew_act:price")],
        [InlineKeyboardButton(text="📐 Изменить тип оплаты", callback_data="ew_act:type")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ew_act:back")]
    ]
    await callback.message.edit_text(
        f"Работа: {name}\nКатегория: {cat_emoji} {cat_name}\n"
        f"Цена: {int(price)} руб/{unit_label}\n"
        f"Тип: {'За м²' if price_type == 'square' else 'За штуку'}\n\nЧто изменить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminEditWork.choosing_action)
    await callback.answer()


@router.callback_query(F.data.startswith("ew_act:"), AdminEditWork.choosing_action)
async def edit_work_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    data = await state.get_data()
    if action == "name":
        await callback.message.edit_text(f"Текущее: {data['work_name']}\n\nВведите новое название:")
        await state.set_state(AdminEditWork.entering_new_name)
    elif action == "price":
        unit_label = "м²" if data["work_price_type"] == "square" else "шт"
        await callback.message.edit_text(f"Текущая: {int(data['work_price'])} руб/{unit_label}\n\nВведите новую цену:")
        await state.set_state(AdminEditWork.entering_new_price)
    elif action == "type":
        current_type = "За м²" if data["work_price_type"] == "square" else "За штуку"
        buttons = [
            [InlineKeyboardButton(text="📦 За штуку", callback_data="ew_type:unit")],
            [InlineKeyboardButton(text="📐 За м²", callback_data="ew_type:square")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="ew_type:cancel")]
        ]
        await callback.message.edit_text(
            f"Текущий тип: {current_type}\n\nВыберите новый тип:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(AdminEditWork.choosing_new_price_type)
    elif action == "back":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
    await callback.answer()


@router.message(AdminEditWork.entering_new_name)
async def edit_work_new_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    data = await state.get_data()
    await update_work_item(data["work_code"], new_name=new_name)
    await message.answer(
        f"✅ Название изменено!\nБыло: {data['work_name']}\nСтало: {new_name}",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


@router.message(AdminEditWork.entering_new_price)
async def edit_work_new_price(message: types.Message, state: FSMContext):
    try:
        new_price = float(message.text.replace(",", "."))
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    unit_label = "м²" if data["work_price_type"] == "square" else "шт"
    await update_work_item(data["work_code"], new_price=new_price)
    await message.answer(
        f"✅ Цена изменена!\nБыло: {int(data['work_price'])} руб/{unit_label}\nСтало: {int(new_price)} руб/{unit_label}",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


@router.callback_query(F.data.startswith("ew_type:"), AdminEditWork.choosing_new_price_type)
async def edit_work_new_type(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    if choice == "cancel":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
        await callback.answer()
        return
    data = await state.get_data()
    if choice == data["work_price_type"]:
        await callback.message.edit_text("ℹ️ Тип оплаты не изменился.")
        await state.clear()
        await callback.answer()
        return
    old_type = "За м²" if data["work_price_type"] == "square" else "За штуку"
    new_type = "За м²" if choice == "square" else "За штуку"
    await update_work_item(data["work_code"], new_price_type=choice)
    await callback.message.edit_text(f"✅ Тип изменён!\nБыло: {old_type}\nСтало: {new_type}")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "ew_back")
async def edit_work_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"ew_cat:{c}")] for c, n, e in cats]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await callback.message.edit_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditWork.choosing_category)
    await callback.answer()
