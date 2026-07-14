import logging
from datetime import date

from aiogram import Router, Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import get_all_workers, get_categories, get_workers_in_category, get_worker_full_stats, get_ghost_worker_ids
from states import AdminBroadcast
from handlers.filters import AdminFilter

router = Router()


def _target_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Всем работникам", callback_data="bc_target:all")],
        [InlineKeyboardButton(text="📂 По категории", callback_data="bc_target:category")],
        [InlineKeyboardButton(text="💰 Баланс > 0 (текущий месяц)", callback_data="bc_target:balance")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_target:cancel")],
    ])


@router.message(F.text == "📢 Рассылка", AdminFilter())
async def broadcast_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📢 Рассылка\n\nКому отправить сообщение?", reply_markup=_target_kb())
    await state.set_state(AdminBroadcast.choosing_target)


@router.callback_query(F.data.startswith("bc_target:"), AdminBroadcast.choosing_target)
async def broadcast_target_chosen(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]

    if value == "cancel":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
        await callback.answer()
        return

    if value == "category":
        cats = await get_categories()
        if not cats:
            await callback.message.edit_text("⚠️ Нет категорий.")
            await state.clear()
            await callback.answer()
            return
        buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"bc_cat:{c}")]
                   for c, n, e in cats]
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bc_cat:cancel")])
        await callback.message.edit_text("📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(AdminBroadcast.choosing_category)
        await callback.answer()
        return

    await state.update_data(target=value)
    await callback.message.edit_text("✏️ Введите текст сообщения для рассылки:")
    await state.set_state(AdminBroadcast.entering_message)
    await callback.answer()


@router.callback_query(F.data.startswith("bc_cat:"), AdminBroadcast.choosing_category)
async def broadcast_category_chosen(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]
    if value == "cancel":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
        await callback.answer()
        return
    await state.update_data(target="category", category_code=value)
    await callback.message.edit_text("✏️ Введите текст сообщения для рассылки:")
    await state.set_state(AdminBroadcast.entering_message)
    await callback.answer()


@router.message(AdminBroadcast.entering_message)
async def broadcast_message_entered(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("❌ Сообщение не может быть пустым.")
        return

    data = await state.get_data()
    target = data["target"]
    today = date.today()

    # Собираем список получателей
    if target == "all":
        workers = await get_all_workers()
        target_label = "всем работникам"
    elif target == "category":
        code = data["category_code"]
        workers = await get_workers_in_category(code)
        target_label = f"категория «{code}»"
    else:  # balance
        all_workers = await get_all_workers()
        workers = []
        for tid, name in all_workers:
            stats = await get_worker_full_stats(tid, today.year, today.month)
            if stats["balance"] > 0:
                workers.append((tid, name))
        target_label = f"баланс > 0 ({len(workers)} чел.)"

    ghost_ids = await get_ghost_worker_ids()
    workers = [(t, n) for t, n in workers if t not in ghost_ids]

    count = len(workers)
    if count == 0:
        await message.answer("⚠️ Нет работников для рассылки.")
        await state.clear()
        return

    await state.update_data(broadcast_text=text, workers=[[t, n] for t, n in workers])

    preview = (
        f"📢 Готово к отправке\n"
        f"👥 Получатели: {target_label}\n"
        f"📨 Кол-во: {count} чел.\n\n"
        f"Текст сообщения:\n"
        f"─────────────────\n"
        f"{text}\n"
        f"─────────────────\n\n"
        f"Отправить?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="bc_confirm:yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_confirm:no")],
    ])
    await message.answer(preview, reply_markup=kb)
    await state.set_state(AdminBroadcast.confirming)


@router.callback_query(F.data.startswith("bc_confirm:"), AdminBroadcast.confirming)
async def broadcast_confirm(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split(":")[1]
    if action == "no":
        await callback.message.edit_text("❌ Рассылка отменена.")
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()
    text = data["broadcast_text"]
    workers = data["workers"]

    await callback.message.edit_text(f"⏳ Отправляю {len(workers)} сообщений...")

    sent = 0
    failed = 0
    for tid, name in workers:
        try:
            await bot.send_message(tid, text)
            sent += 1
        except Exception as e:
            logging.warning(f"Broadcast to {name} ({tid}) failed: {e}")
            failed += 1

    result = f"✅ Рассылка завершена!\n\n📨 Отправлено: {sent}"
    if failed:
        result += f"\n❌ Не доставлено: {failed} (заблокировали бота или не запускали)"
    await callback.message.answer(result)

    await state.clear()
    await callback.answer()
