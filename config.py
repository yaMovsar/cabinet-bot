import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip('"')
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip().strip('"'))
MANAGER_ID = int(os.getenv("MANAGER_ID", "0").strip().strip('"'))