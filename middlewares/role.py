from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from config import ADMIN_ID, MANAGER_IDS


class RoleMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user:
            uid = user.id
            data["is_admin"] = uid == ADMIN_ID
            data["is_manager"] = uid in MANAGER_IDS
            data["is_staff"] = uid == ADMIN_ID or uid in MANAGER_IDS
        else:
            data["is_admin"] = False
            data["is_manager"] = False
            data["is_staff"] = False
        return await handler(event, data)