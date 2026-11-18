from aiogram import Router

from .common import router as common_router
from .worker import router as worker_router
from .admin import router as admin_router
from .admin_entries_add import router as admin_entries_add_router
from .money import router as money_router
from .expenses import router as expenses_router
from .roles import router as roles_router
from .report_handlers import router as reports_router
from .reminders import router as reminders_router
from .broadcast import router as broadcast_router
from .manager import router as manager_router
from .brigade import router as brigade_router


def setup_routers() -> Router:
    main_router = Router()

    main_router.include_router(common_router)
    main_router.include_router(worker_router)
    main_router.include_router(admin_router)
    main_router.include_router(admin_entries_add_router)
    main_router.include_router(money_router)
    main_router.include_router(expenses_router)
    main_router.include_router(roles_router)
    main_router.include_router(reports_router)
    main_router.include_router(reminders_router)
    main_router.include_router(broadcast_router)
    main_router.include_router(manager_router)
    main_router.include_router(brigade_router)

    return main_router