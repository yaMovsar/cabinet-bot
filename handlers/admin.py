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
    rename_category, update_category_emoji,
    rename_price_item, change_price_item_category, get_price_item_by_code,
    update_price_item_unit
)

from states.states import (
    AdminAddCategory, AdminAddWork, AdminAddWorker,
    AdminAssignCategory, AdminRemoveCategory,
    AdminEditPrice, AdminRenameWorker,
    AdminDeleteCategory, AdminDeleteWork, AdminDeleteWorker,
    AdminManageEntries,
    AdminEditCategory, AdminEditWork
)

from keyboards import get_add_keyboard, get_edit_keyboard, get_delete_keyboard
from utils import format_date, send_long_message
from handlers.filters import AdminFilter, StaffFilter

router = Router()

# Доступные единицы измерения
UNITS = ["шт", "кв.м", "п.м", "л", "кг", "час"]


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
        items = [i for i in all_items if i[3] == code]
        i_str = ", ".join([f"{i[1]} ({int(i[2])} руб/{i[6] if len(i)>6 else 'шт'})" for i in items]) if items else "—"
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
    await message.answer("Расценка (число):")
    await state.set_state(AdminAddWork.entering_price)


@router.message(AdminAddWork.entering_price)
async def add_work_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.'))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    await state.update_data(price=price)
    
    buttons = []
    row = []
    for unit in UNITS:
        row.append(InlineKeyboardButton(text=unit, callback_data=f"awu:{unit}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    
    await message.answer(
        f"💰 Цена: {int(price)} руб\n\nВыберите единицу измерения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminAddWork.choosing_unit)


@router.callback_query(F.data.startswith("awu:"), AdminAddWork.choosing_unit)
async def add_work_unit(callback: types.CallbackQuery, state: FSMContext):
    unit = callback.data.split(":")[1]
    data = await state.get_data()
    await add_price_item(data["code"], data["name"], data["price"], data["category_code"], unit)
    await callback.message.edit_text(
        f"✅ Работа добавлена!\n\n"
        f"📝 {data['name']}\n"
        f"💰 {int(data['price'])} руб/{unit}"
    )
    await state.clear()
    await callback.answer()


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
        text += f"▫️ {name} ({tid})\n   {c_str}\n\n"
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
    for row in items:
        code, name, price, cat_code, cat_name, cat_emoji, unit = (row + ["шт"])[:7]
        if cat_code != cur:
            cur = cat_code
            text += f"\n{cat_emoji} {cat_name}:\n"
        text += f"   ▫️ {code} — {name}: {int(price)} руб/{unit}\n"
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
    await callback.message.edit_text(f"✅ {w} -> {c}")
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
    
    buttons = []
    for row in items:
        code, name, price, _, _, emoji, unit = (row + ["шт"])[:7]
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {name} — {int(price)} руб/{unit}",
            callback_data=f"ep:{code}"
        )])
    
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
        p = float(message.text.replace(',', '.'))
        if p <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    await update_price(data["code"], p)
    await message.answer(f"✅ Расценка: {int(p)} руб", reply_markup=get_edit_keyboard())
    await state.clear()


# === РАСЦЕНКА ===
@router.message(F.text == "✏️ Расценка", AdminFilter())
async def edit_price_start(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("⚠️ Пусто.")
        return
    
    buttons = []
    for row in items:
        # row — кортеж, превращаем в список, добавляем "шт" если нужно
        r = list(row)
        if len(r) == 6:
            r.append("шт")
        code, name, price, _, _, emoji, unit = r
        
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {name} — {int(price)} руб/{unit}",
            callback_data=f"ep:{code}"
        )])
    
    await message.answer("Позиция:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditPrice.choosing_item)


# === УДАЛЕНИЕ РАБОТЫ ===
@router.message(F.text == "🗑 Уд. работу", AdminFilter())
async def del_work_start(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("📄 Пусто.")
        return
    
    buttons = []
    for row in items:
        r = list(row)
        if len(r) == 6:
            r.append("шт")
        code, name, price, _, _, emoji, unit = r
        
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {name} — {int(price)} руб/{unit}",
            callback_data=f"dw:{code}"
        )])
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWork.choosing)


# === РЕДАКТИРОВАНИЕ РАБОТЫ ===
@router.message(F.text == "📝 Ред. работу", AdminFilter())
async def edit_work_start(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("📄 Нет работ.")
        return
    
    buttons = []
    for row in items:
        r = list(row)
        if len(r) == 6:
            r.append("шт")
        code, name, price, _, _, emoji, unit = r
        
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {name} — {int(price)} руб/{unit}",
            callback_data=f"ework:{code}"
        )])
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("📝 Выберите работу для редактирования:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditWork.choosing_work)


@router.callback_query(F.data.startswith("ework:"), AdminEditWork.choosing_work)
async def edit_work_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    item = await get_price_item_by_code(code)
    if not item:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    
    await state.update_data(
        work_code=item[0], work_name=item[1], work_price=item[2],
        work_cat_code=item[3], work_cat_name=item[4], work_cat_emoji=item[5],
        work_unit=item[6] if len(item) > 6 else "шт"
    )
    unit = item[6] if len(item) > 6 else "шт"
    buttons = [
        [InlineKeyboardButton(text="📝 Переименовать", callback_data="ework_act:rename")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data="ework_act:price")],
        [InlineKeyboardButton(text="📂 Изменить категорию", callback_data="ework_act:category")],
        [InlineKeyboardButton(text="📏 Изменить ед.изм.", callback_data="ework_act:unit")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ework_act:back")]
    ]
    await callback.message.edit_text(
        f"📝 Работа: {item[1]}\n"
        f"💰 Цена: {int(item[2])} руб/{unit}\n"
        f"📂 Категория: {item[5]} {item[4]}\n"
        f"📏 Единица: {unit}\n"
        f"📋 Код: {code}\n\n"
        f"Что изменить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminEditWork.choosing_action)
    await callback.answer()


# Остальные функции (удаление, записи, редактирование категории и т.д.) оставь как были — они уже работают идеально

@router.callback_query(F.data.startswith("ework_act:"), AdminEditWork.choosing_action)
async def edit_work_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    data = await state.get_data()
    
    if action == "rename":
        await callback.message.edit_text(f"📝 Текущее название: {data['work_name']}\n\nВведите новое название:")
        await state.set_state(AdminEditWork.entering_new_name)
    elif action == "price":
        await callback.message.edit_text(f"💰 Текущая цена: {int(data['work_price'])} руб\n\nВведите новую цену:")
        await state.set_state(AdminEditPrice.entering_new_price)
        await state.update_data(code=data['work_code'])
    elif action == "category":
        cats = await get_categories()
        buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"ework_cat:{c}")]
                  for c, n, e in cats if c != data['work_cat_code']]
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ework_cat:back")])
        await callback.message.edit_text(
            f"📂 Текущая категория: {data['work_cat_emoji']} {data['work_cat_name']}\n\nВыберите новую:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(AdminEditWork.choosing_new_category)
    elif action == "unit":
        buttons = []
        row = []
        for unit in UNITS:
            row.append(InlineKeyboardButton(text=unit, callback_data=f"ework_unit:{unit}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ework_unit:back")])
        await callback.message.edit_text(
            f"📏 Текущая единица: {data.get('work_unit', 'шт')}\n\nВыберите новую:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(AdminEditWork.choosing_new_unit)
    elif action == "back":
        await state.clear()
        await callback.message.edit_text("👌 Ок")
    await callback.answer()


@router.callback_query(F.data.startswith("ework_unit:"), AdminEditWork.choosing_new_unit)
async def edit_work_new_unit(callback: types.CallbackQuery, state: FSMContext):
    unit = callback.data.split(":")[1]
    if unit == "back":
        await state.clear()
        await callback.message.edit_text("👌 Ок")
        await callback.answer()
        return
    data = await state.get_data()
    await update_price_item_unit(data['work_code'], unit)
    await callback.message.edit_text(
        f"✅ Единица измерения изменена!\n\n"
        f"📝 {data['work_name']}\n"
        f"Было: {data.get('work_unit', 'шт')}\n"
        f"Стало: {unit}"
    )
    await state.clear()
    await callback.answer()


@router.message(AdminEditWork.entering_new_name)
async def edit_work_new_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.answer("❌ Название не может быть пустым!")
        return
    data = await state.get_data()
    await rename_price_item(data['work_code'], new_name)
    await message.answer(
        f"✅ Работа переименована!\n\nБыло: {data['work_name']}\nСтало: {new_name}",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


@router.callback_query(F.data.startswith("ework_cat:"), AdminEditWork.choosing_new_category)
async def edit_work_new_category(callback: types.CallbackQuery, state: FSMContext):
    cat_code = callback.data.split(":")[1]
    if cat_code == "back":
        await state.clear()
        await callback.message.edit_text("👌 Ок")
        await callback.answer()
        return
    data = await state.get_data()
    cats = await get_categories()
    new_cat = next((e, n) for c, n, e in cats if c == cat_code)
    await change_price_item_category(data['work_code'], cat_code)
    await callback.message.edit_text(
        f"✅ Категория изменена!\n\n"
        f"📝 {data['work_name']}\n"
        f"Было: {data['work_cat_emoji']} {data['work_cat_name']}\n"
        f"Стало: {new_cat[0]} {new_cat[1]}"
    )
    await state.clear()
    await callback.answer()

# === Остальные функции (удаление работника, записи, редактирование категории и т.д.) оставь как у тебя были — они уже идеальны ===

@router.callback_query(F.data == "cdel")
async def cancel_del(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()