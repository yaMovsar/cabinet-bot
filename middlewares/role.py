from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from utils.roles import is_admin, is_manager, is_staff, is_owner


class RoleMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user:
            uid = user.id
            data["is_admin"] = is_admin(uid)
            data["is_manager"] = is_manager(uid)
            data["is_staff"] = is_staff(uid)
            data["is_owner"] = is_owner(uid)
        else:
            data["is_admin"] = False
            data["is_manager"] = False
            data["is_staff"] = False
            data["is_owner"] = False
        return await handler(event, data)