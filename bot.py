import asyncio
import logging
import os
from datetime import datetime, date

from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID
from database import (
    init_db, get_reminder_settings,
    get_workers_without_records, get_all_workers_daily_summary,
    DB_NAME
)
from handlers import setup_routers
from handlers.reminders import set_scheduler
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

async def send_evening_reminder():
    settings = await get_reminder_settings()
    if not settings['evening_enabled']:
        return
    for tid, name in await get_workers_without_records():
        try:
            await bot.send_message(tid, "🔔 Запишите работу за сегодня!")
        except Exception as e:
            logging.error(f"Reminder {name}: {e}")


async def send_late_reminder():
    settings = await get_reminder_settings()
    if not settings['late_enabled']:
        return
    for tid, name in await get_workers_without_records():
        try:
            await bot.send_message(tid, "⚠️ Вы не записали работу! Нужно для зарплаты.")
        except Exception as e:
            logging.error(f"Late {name}: {e}")


async def send_admin_report():
    settings = await get_reminder_settings()
    if not settings['report_enabled']:
        return
    summary = await get_all_workers_daily_summary()
    text = f"📊 Итоги {date.today().strftime('%d.%m.%Y')}:\n\n"
    total = 0
    for tid, name, dt in summary:
        icon = '✅' if dt > 0 else '❌'
        text += f"{icon} {name}: {int(dt)} руб\n"
        total += dt
    text += f"\n💰 Итого: {int(total)} руб"
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logging.error(f"Admin report: {e}")


async def send_backup(chat_id=None):
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


# Safe wrappers
async def safe_evening_reminder():
    try:
        await send_evening_reminder()
    except Exception as e:
        logging.exception(f"Evening reminder failed: {e}")


async def safe_late_reminder():
    try:
        await send_late_reminder()
    except Exception as e:
        logging.exception(f"Late reminder failed: {e}")


async def safe_admin_report():
    try:
        await send_admin_report()
    except Exception as e:
        logging.exception(f"Admin report failed: {e}")


async def safe_backup():
    try:
        await send_backup(ADMIN_ID)
    except Exception as e:
        logging.exception(f"Backup failed: {e}")


async def reschedule_reminders():
    settings = await get_reminder_settings()
    for job_id in ['evening_reminder', 'late_reminder', 'admin_report', 'auto_backup']:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
    if settings['evening_enabled']:
        scheduler.add_job(safe_evening_reminder, "cron",
            hour=settings['evening_hour'], minute=settings['evening_minute'],
            id='evening_reminder', replace_existing=True)
    if settings['late_enabled']:
        scheduler.add_job(safe_late_reminder, "cron",
            hour=settings['late_hour'], minute=settings['late_minute'],
            id='late_reminder', replace_existing=True)
    if settings['report_enabled']:
        scheduler.add_job(safe_admin_report, "cron",
            hour=settings['report_hour'], minute=settings['report_minute'],
            id='admin_report', replace_existing=True)
    scheduler.add_job(safe_backup, "cron", hour=23, minute=0,
        id='auto_backup', replace_existing=True)


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
    
    # Передаём scheduler в reminders
    set_scheduler(scheduler)
    
    # Настройка планировщика
    settings = await get_reminder_settings()
    if settings['evening_enabled']:
        scheduler.add_job(safe_evening_reminder, "cron",
            hour=settings['evening_hour'], minute=settings['evening_minute'],
            id='evening_reminder')
    if settings['late_enabled']:
        scheduler.add_job(safe_late_reminder, "cron",
            hour=settings['late_hour'], minute=settings['late_minute'],
            id='late_reminder')
    if settings['report_enabled']:
        scheduler.add_job(safe_admin_report, "cron",
            hour=settings['report_hour'], minute=settings['report_minute'],
            id='admin_report')
    scheduler.add_job(safe_backup, "cron", hour=23, minute=0, id='auto_backup')
    scheduler.start()
    
    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())