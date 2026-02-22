from aiogram import Router

from .common import router as common_router
from .worker import router as worker_router
from .admin import router as admin_router
from .money import router as money_router
from .reports import router as reports_router
from .reminders import router as reminders_router


def setup_routers() -> Router:
    """Собрать все роутеры в один"""
    main_router = Router()
    
    main_router.include_router(common_router)
    main_router.include_router(worker_router)
    main_router.include_router(admin_router)
    main_router.include_router(money_router)
    main_router.include_router(reports_router)
    main_router.include_router(reminders_router)
    
    return main_router