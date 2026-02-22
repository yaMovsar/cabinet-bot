import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip('"')
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip().strip('"'))

_managers = os.getenv("MANAGER_IDS", os.getenv("MANAGER_ID", "0")).strip().strip('"')
MANAGER_IDS = []
for m in _managers.split(","):
    m = m.strip()
    if m and m != "0":
        MANAGER_IDS.append(int(m))