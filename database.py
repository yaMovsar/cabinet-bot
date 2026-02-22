import aiosqlite
import os
from datetime import date

VOLUME_PATH = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", ".")
DB_NAME = os.path.join(VOLUME_PATH, "production.db")


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                emoji TEXT DEFAULT '📦'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS price_list (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category_code TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (category_code) REFERENCES categories(code)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS worker_categories (
                worker_id INTEGER NOT NULL,
                category_code TEXT NOT NULL,
                PRIMARY KEY (worker_id, category_code),
                FOREIGN KEY (worker_id) REFERENCES workers(telegram_id),
                FOREIGN KEY (category_code) REFERENCES categories(code)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS work_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                work_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price_per_unit REAL NOT NULL,
                total REAL NOT NULL,
                work_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(telegram_id),
                FOREIGN KEY (work_code) REFERENCES price_list(code)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                comment TEXT DEFAULT '',
                advance_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS penalties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                reason TEXT DEFAULT '',
                penalty_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminder_settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                evening_hour INTEGER DEFAULT 18,
                evening_minute INTEGER DEFAULT 0,
                late_hour INTEGER DEFAULT 20,
                late_minute INTEGER DEFAULT 0,
                report_hour INTEGER DEFAULT 21,
                report_minute INTEGER DEFAULT 0,
                evening_enabled BOOLEAN DEFAULT 1,
                late_enabled BOOLEAN DEFAULT 1,
                report_enabled BOOLEAN DEFAULT 1
            )
        """)
        existing = await db.execute("SELECT COUNT(*) FROM reminder_settings")
        count = (await existing.fetchone())[0]
        if count == 0:
            await db.execute("""
                INSERT INTO reminder_settings 
                (id, evening_hour, evening_minute, late_hour, late_minute, 
                 report_hour, report_minute, evening_enabled, late_enabled, report_enabled)
                VALUES (1, 18, 0, 20, 0, 21, 0, 1, 1, 1)
            """)
        
        # Индексы для ускорения запросов
        await db.execute("CREATE INDEX IF NOT EXISTS idx_worklog_worker_date ON work_log(worker_id, work_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_worklog_date ON work_log(work_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_advances_worker_date ON advances(worker_id, advance_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_penalties_worker_date ON penalties(worker_id, penalty_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_worker_categories ON worker_categories(worker_id, category_code)")
        
        await db.commit()

# ==================== КАТЕГОРИИ ====================

async def add_category(code, name, emoji="📦"):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO categories (code, name, emoji) VALUES (?, ?, ?)",
                         (code, name, emoji))
        await db.commit()


async def get_categories():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT code, name, emoji FROM categories ORDER BY name")
        return await cursor.fetchall()


async def delete_category(code):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM worker_categories WHERE category_code = ?", (code,))
        await db.execute("UPDATE price_list SET is_active = 0 WHERE category_code = ?", (code,))
        await db.execute("DELETE FROM categories WHERE code = ?", (code,))
        await db.commit()


# ==================== РАБОТНИКИ ====================

async def add_worker(telegram_id, name):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO workers (telegram_id, name) VALUES (?, ?)",
                         (telegram_id, name))
        await db.commit()


async def worker_exists(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT 1 FROM workers WHERE telegram_id = ?", (telegram_id,))
        return await cursor.fetchone() is not None


async def get_all_workers():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT telegram_id, name FROM workers ORDER BY name")
        return await cursor.fetchall()


async def delete_worker(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM worker_categories WHERE worker_id = ?", (telegram_id,))
        await db.execute("DELETE FROM workers WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def rename_worker(telegram_id, new_name):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE workers SET name = ? WHERE telegram_id = ?",
                         (new_name, telegram_id))
        await db.commit()


# ==================== СВЯЗЬ РАБОТНИК-КАТЕГОРИЯ ====================

async def assign_category_to_worker(worker_id, category_code):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO worker_categories (worker_id, category_code) VALUES (?, ?)",
                         (worker_id, category_code))
        await db.commit()


async def remove_category_from_worker(worker_id, category_code):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM worker_categories WHERE worker_id = ? AND category_code = ?",
                         (worker_id, category_code))
        await db.commit()


async def get_worker_categories(worker_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT c.code, c.name, c.emoji
            FROM worker_categories wc
            JOIN categories c ON wc.category_code = c.code
            WHERE wc.worker_id = ?
            ORDER BY c.name
        """, (worker_id,))
        return await cursor.fetchall()


async def get_workers_in_category(category_code):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT w.telegram_id, w.name
            FROM worker_categories wc
            JOIN workers w ON wc.worker_id = w.telegram_id
            WHERE wc.category_code = ?
            ORDER BY w.name
        """, (category_code,))
        return await cursor.fetchall()


# ==================== ПРАЙС-ЛИСТ ====================

async def add_price_item(code, name, price, category_code):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO price_list (code, name, price, category_code, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (code, name, price, category_code))
        await db.commit()


async def get_price_list():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT pl.code, pl.name, pl.price, pl.category_code, c.name, c.emoji
            FROM price_list pl
            JOIN categories c ON pl.category_code = c.code
            WHERE pl.is_active = 1
            ORDER BY c.name, pl.name
        """)
        return await cursor.fetchall()


async def get_price_list_for_worker(worker_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT pl.code, pl.name, pl.price, pl.category_code
            FROM price_list pl
            JOIN worker_categories wc ON pl.category_code = wc.category_code
            WHERE wc.worker_id = ? AND pl.is_active = 1
            ORDER BY pl.category_code, pl.name
        """, (worker_id,))
        return await cursor.fetchall()


async def update_price(code, new_price):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE price_list SET price = ? WHERE code = ?", (new_price, code))
        await db.commit()


async def delete_price_item_permanently(code):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM work_log WHERE work_code = ?", (code,))
        count = (await cursor.fetchone())[0]
        if count > 0:
            await db.execute("UPDATE price_list SET is_active = 0 WHERE code = ?", (code,))
            await db.commit()
            return False
        else:
            await db.execute("DELETE FROM price_list WHERE code = ?", (code,))
            await db.commit()
            return True


# ==================== ЗАПИСИ О РАБОТЕ ====================

async def add_work(worker_id, work_code, quantity, price, work_date=None):
    if work_date is None:
        work_date = date.today()
    total = quantity * price
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO work_log (worker_id, work_code, quantity, price_per_unit, total, work_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (worker_id, work_code, quantity, price, total, work_date))
        await db.commit()
    return total


async def delete_last_entry(worker_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            DELETE FROM work_log WHERE id = (
                SELECT id FROM work_log WHERE worker_id = ?
                ORDER BY created_at DESC LIMIT 1
            )
        """, (worker_id,))
        await db.commit()


# ==================== ОТЧЁТЫ ====================

async def get_daily_total(worker_id, target_date=None):
    if target_date is None:
        target_date = date.today()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT work_code, SUM(quantity), price_per_unit, SUM(total)
            FROM work_log
            WHERE worker_id = ? AND work_date = ?
            GROUP BY work_code
        """, (worker_id, target_date))
        return await cursor.fetchall()


async def get_monthly_total(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT work_code, SUM(quantity), price_per_unit, SUM(total)
            FROM work_log
            WHERE worker_id = ?
              AND strftime('%Y', work_date) = ?
              AND strftime('%m', work_date) = ?
            GROUP BY work_code
        """, (worker_id, str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_all_workers_daily_summary(target_date=None):
    if target_date is None:
        target_date = date.today()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT w.telegram_id, w.name, COALESCE(SUM(wl.total), 0)
            FROM workers w
            LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id AND wl.work_date = ?
            GROUP BY w.telegram_id, w.name
            ORDER BY w.name
        """, (target_date,))
        return await cursor.fetchall()


async def get_all_workers_monthly_summary(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT w.telegram_id, w.name, COALESCE(SUM(wl.total), 0)
            FROM workers w
            LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id
                AND strftime('%Y', wl.work_date) = ?
                AND strftime('%m', wl.work_date) = ?
            GROUP BY w.telegram_id, w.name
            ORDER BY w.name
        """, (str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_workers_without_records(target_date=None):
    if target_date is None:
        target_date = date.today()
    async with aiosqlite.connect(DB_NAME) as db:
        all_cursor = await db.execute("SELECT telegram_id, name FROM workers")
        all_workers = await all_cursor.fetchall()
        rec_cursor = await db.execute(
            "SELECT DISTINCT worker_id FROM work_log WHERE work_date = ?",
            (target_date,))
        with_records = {r[0] for r in await rec_cursor.fetchall()}
    return [(tid, name) for tid, name in all_workers if tid not in with_records]


async def get_monthly_by_days(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT wl.work_date, pl.name, SUM(wl.quantity),
                   wl.price_per_unit, SUM(wl.total)
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = ?
              AND strftime('%Y', wl.work_date) = ?
              AND strftime('%m', wl.work_date) = ?
            GROUP BY wl.work_date, pl.name, wl.price_per_unit
            ORDER BY wl.work_date, pl.name
        """, (worker_id, str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_today_entries(worker_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total, wl.created_at
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = ? AND wl.work_date = ?
            ORDER BY wl.created_at
        """, (worker_id, date.today()))
        return await cursor.fetchall()


async def get_worker_entries_by_date(worker_id, target_date):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
                   wl.work_date, wl.created_at
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = ? AND wl.work_date = ?
            ORDER BY wl.created_at
        """, (worker_id, target_date))
        return await cursor.fetchall()


async def get_worker_recent_entries(worker_id, limit=20):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
                   wl.work_date, wl.created_at
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = ?
            ORDER BY wl.work_date DESC, wl.created_at DESC
            LIMIT ?
        """, (worker_id, limit))
        return await cursor.fetchall()


async def delete_entry_by_id(entry_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT wl.id, pl.name, wl.quantity, wl.total, wl.work_date, w.name
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN workers w ON wl.worker_id = w.telegram_id
            WHERE wl.id = ?
        """, (entry_id,))
        entry = await cursor.fetchone()
        if entry:
            await db.execute("DELETE FROM work_log WHERE id = ?", (entry_id,))
            await db.commit()
        return entry


async def update_entry_quantity(entry_id, new_quantity):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price_per_unit FROM work_log WHERE id = ?", (entry_id,))
        entry = await cursor.fetchone()
        if entry:
            new_total = new_quantity * entry[0]
            await db.execute("UPDATE work_log SET quantity = ?, total = ? WHERE id = ?",
                             (new_quantity, new_total, entry_id))
            await db.commit()
        return entry is not None


async def get_entry_by_id(entry_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
                   wl.work_date, wl.worker_id, w.name
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN workers w ON wl.worker_id = w.telegram_id
            WHERE wl.id = ?
        """, (entry_id,))
        return await cursor.fetchone()


async def get_worker_monthly_details(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT pl.name, c.emoji, c.name, SUM(wl.quantity),
                   wl.price_per_unit, SUM(wl.total)
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE wl.worker_id = ?
              AND strftime('%Y', wl.work_date) = ?
              AND strftime('%m', wl.work_date) = ?
            GROUP BY pl.name, c.emoji, c.name, wl.price_per_unit
            ORDER BY c.name, pl.name
        """, (worker_id, str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_all_workers_monthly_details(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT w.telegram_id, w.name,
                   pl.name, c.emoji, c.name,
                   SUM(wl.quantity), wl.price_per_unit, SUM(wl.total),
                   COUNT(DISTINCT wl.work_date)
            FROM workers w
            LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id
                AND strftime('%Y', wl.work_date) = ?
                AND strftime('%m', wl.work_date) = ?
            LEFT JOIN price_list pl ON wl.work_code = pl.code
            LEFT JOIN categories c ON pl.category_code = c.code
            GROUP BY w.telegram_id, w.name, pl.name, c.emoji, c.name, wl.price_per_unit
            ORDER BY w.name, c.name, pl.name
        """, (str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_admin_monthly_detailed_all(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT
                w.telegram_id,
                w.name AS worker_name,
                c.name AS category_name,
                c.emoji AS category_emoji,
                wl.work_date,
                pl.name AS work_name,
                wl.quantity,
                wl.price_per_unit,
                wl.total
            FROM work_log wl
            JOIN workers w ON wl.worker_id = w.telegram_id
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE strftime('%Y', wl.work_date) = ?
              AND strftime('%m', wl.work_date) = ?
            ORDER BY w.name, c.name, wl.work_date, wl.id
        """, (str(year), f"{month:02d}"))
        return await cursor.fetchall()


# ==================== ОПТИМИЗИРОВАННЫЕ ЗАПРОСЫ ====================

async def get_all_workers_balance(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT 
                w.telegram_id, w.name,
                COALESCE(earn.total_earned, 0) as earned,
                COALESCE(adv.total_advance, 0) as advances,
                COALESCE(pen.total_penalty, 0) as penalties,
                COALESCE(earn.work_days, 0) as work_days
            FROM workers w
            LEFT JOIN (
                SELECT worker_id, 
                       SUM(total) as total_earned,
                       COUNT(DISTINCT work_date) as work_days
                FROM work_log
                WHERE strftime('%Y', work_date) = ? AND strftime('%m', work_date) = ?
                GROUP BY worker_id
            ) earn ON w.telegram_id = earn.worker_id
            LEFT JOIN (
                SELECT worker_id, SUM(amount) as total_advance
                FROM advances
                WHERE strftime('%Y', advance_date) = ? AND strftime('%m', advance_date) = ?
                GROUP BY worker_id
            ) adv ON w.telegram_id = adv.worker_id
            LEFT JOIN (
                SELECT worker_id, SUM(amount) as total_penalty
                FROM penalties
                WHERE strftime('%Y', penalty_date) = ? AND strftime('%m', penalty_date) = ?
                GROUP BY worker_id
            ) pen ON w.telegram_id = pen.worker_id
            ORDER BY w.name
        """, (str(year), f"{month:02d}", str(year), f"{month:02d}", str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_worker_full_stats(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT 
                COALESCE(SUM(wl.total), 0) as earned,
                COUNT(DISTINCT wl.work_date) as work_days
            FROM work_log wl
            WHERE wl.worker_id = ?
              AND strftime('%Y', wl.work_date) = ?
              AND strftime('%m', wl.work_date) = ?
        """, (worker_id, str(year), f"{month:02d}"))
        earn_row = await cursor.fetchone()

        cursor2 = await db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM advances
            WHERE worker_id = ?
              AND strftime('%Y', advance_date) = ?
              AND strftime('%m', advance_date) = ?
        """, (worker_id, str(year), f"{month:02d}"))
        adv_row = await cursor2.fetchone()

        cursor3 = await db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM penalties
            WHERE worker_id = ?
              AND strftime('%Y', penalty_date) = ?
              AND strftime('%m', penalty_date) = ?
        """, (worker_id, str(year), f"{month:02d}"))
        pen_row = await cursor3.fetchone()

    return {
        'earned': earn_row[0],
        'work_days': earn_row[1],
        'advances': adv_row[0],
        'penalties': pen_row[0],
        'balance': earn_row[0] - adv_row[0] - pen_row[0]
    }


# ==================== АВАНСЫ ====================

async def add_advance(worker_id, amount, comment="", advance_date=None):
    if advance_date is None:
        advance_date = date.today()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO advances (worker_id, amount, comment, advance_date)
            VALUES (?, ?, ?, ?)
        """, (worker_id, amount, comment, advance_date))
        await db.commit()


async def get_worker_advances(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT id, amount, comment, advance_date, created_at
            FROM advances
            WHERE worker_id = ?
              AND strftime('%Y', advance_date) = ?
              AND strftime('%m', advance_date) = ?
            ORDER BY advance_date
        """, (worker_id, str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_worker_advances_total(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM advances
            WHERE worker_id = ?
              AND strftime('%Y', advance_date) = ?
              AND strftime('%m', advance_date) = ?
        """, (worker_id, str(year), f"{month:02d}"))
        result = await cursor.fetchone()
        return result[0]


async def delete_advance(advance_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, amount, comment, advance_date, worker_id FROM advances WHERE id = ?",
            (advance_id,))
        advance = await cursor.fetchone()
        if advance:
            await db.execute("DELETE FROM advances WHERE id = ?", (advance_id,))
            await db.commit()
        return advance


async def get_all_advances_monthly(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT w.telegram_id, w.name,
                   COALESCE(SUM(a.amount), 0) as total_advance
            FROM workers w
            LEFT JOIN advances a ON w.telegram_id = a.worker_id
                AND strftime('%Y', a.advance_date) = ?
                AND strftime('%m', a.advance_date) = ?
            GROUP BY w.telegram_id, w.name
            ORDER BY w.name
        """, (str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_worker_entries_by_custom_date(worker_id, target_date):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT wl.id, pl.name, c.name, c.emoji, wl.quantity,
                   wl.price_per_unit, wl.total, wl.created_at
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE wl.worker_id = ? AND wl.work_date = ?
            ORDER BY wl.created_at
        """, (worker_id, target_date))
        return await cursor.fetchall()


# ==================== ШТРАФЫ ====================

async def add_penalty(worker_id, amount, reason="", penalty_date=None):
    if penalty_date is None:
        penalty_date = date.today()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO penalties (worker_id, amount, reason, penalty_date)
            VALUES (?, ?, ?, ?)
        """, (worker_id, amount, reason, penalty_date))
        await db.commit()


async def get_worker_penalties(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT id, amount, reason, penalty_date, created_at
            FROM penalties
            WHERE worker_id = ?
              AND strftime('%Y', penalty_date) = ?
              AND strftime('%m', penalty_date) = ?
            ORDER BY penalty_date
        """, (worker_id, str(year), f"{month:02d}"))
        return await cursor.fetchall()


async def get_worker_penalties_total(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM penalties
            WHERE worker_id = ?
              AND strftime('%Y', penalty_date) = ?
              AND strftime('%m', penalty_date) = ?
        """, (worker_id, str(year), f"{month:02d}"))
        result = await cursor.fetchone()
        return result[0]


async def delete_penalty(penalty_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, amount, reason, penalty_date, worker_id FROM penalties WHERE id = ?",
            (penalty_id,))
        penalty = await cursor.fetchone()
        if penalty:
            await db.execute("DELETE FROM penalties WHERE id = ?", (penalty_id,))
            await db.commit()
        return penalty


# ==================== НАСТРОЙКИ НАПОМИНАНИЙ ====================

async def get_reminder_settings():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM reminder_settings WHERE id = 1")
        row = await cursor.fetchone()
        if row:
            return {
                'evening_hour': row[1], 'evening_minute': row[2],
                'late_hour': row[3], 'late_minute': row[4],
                'report_hour': row[5], 'report_minute': row[6],
                'evening_enabled': bool(row[7]),
                'late_enabled': bool(row[8]),
                'report_enabled': bool(row[9]),
            }
        return {
            'evening_hour': 18, 'evening_minute': 0,
            'late_hour': 20, 'late_minute': 0,
            'report_hour': 21, 'report_minute': 0,
            'evening_enabled': True, 'late_enabled': True, 'report_enabled': True,
        }


async def update_reminder_settings(**kwargs):
    async with aiosqlite.connect(DB_NAME) as db:
        sets = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        vals = list(kwargs.values())
        vals.append(1)
        await db.execute(f"UPDATE reminder_settings SET {sets} WHERE id = ?", vals)
        await db.commit()