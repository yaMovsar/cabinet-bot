import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID
from database import init_db, get_reminder_settings, DB_NAME
from handlers import setup_routers
from middlewares import RoleMiddleware

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()


# ==================== ERROR HANDLER ====================

@dp.error()
async def global_error_handler(event: types.ErrorEvent):
    if "message is not modified" in str(event.exception):
        return True
    logging.exception(f"Ошибка: {event.exception}")
    try:
        error_text = f"🚨 Ошибка бота:\n\n{type(event.exception).__name__}: {str(event.exception)[:500]}"
        await bot.send_message(ADMIN_ID, error_text)
    except Exception:
        pass


# ==================== НАПОМИНАНИЯ ====================

async def send_backup(chat_id=None):
    """Отправка бэкапа БД"""
    from aiogram.types import FSInputFile
    if chat_id is None:
        chat_id = ADMIN_ID
    
    if not os.path.exists(DB_NAME):
        await bot.send_message(chat_id, "❌ База данных не найдена!")
        return
    
    try:
        now = datetime.now()
        await bot.send_document(
            chat_id,
            FSInputFile(DB_NAME, filename=f"backup_{now.strftime('%Y%m%d_%H%M')}.db"),
            caption=f"💾 Бэкап БД\n📅 {now.strftime('%d.%m.%Y %H:%M')}"
        )
    except Exception as e:
        logging.error(f"Backup error: {e}")


async def reschedule_reminders():
    """Перенастройка напоминаний по БД"""
    # ... логика из старого bot.py


# ==================== ЗАПУСК ====================

async def main():
    # Инициализация БД
    await init_db()
    
    # Подключение middleware
    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())
    
    # Подключение роутеров
    main_router = setup_routers()
    dp.include_router(main_router)
    
    # Настройка планировщика
    settings = await get_reminder_settings()
    # ... настройка scheduler
    scheduler.add_job(send_backup, "cron", hour=23, minute=0, id='auto_backup')
    scheduler.start()
    
    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())