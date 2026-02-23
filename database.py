import asyncpg
import os
from datetime import date, datetime
from typing import Optional, List, Any

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Пул соединений (глобальный)
pool: Optional[asyncpg.Pool] = None


def parse_date(value):
    """Преобразует строку в date"""
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value[:10], '%Y-%m-%d').date()
    return date.today()


async def init_db():
    """Инициализация пула соединений и создание таблиц"""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                telegram_id BIGINT PRIMARY KEY,
                name TEXT NOT NULL,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                emoji TEXT DEFAULT '📦'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS price_list (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category_code TEXT NOT NULL REFERENCES categories(code),
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS worker_categories (
                worker_id BIGINT NOT NULL REFERENCES workers(telegram_id),
                category_code TEXT NOT NULL REFERENCES categories(code),
                PRIMARY KEY (worker_id, category_code)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS work_log (
                id SERIAL PRIMARY KEY,
                worker_id BIGINT NOT NULL REFERENCES workers(telegram_id),
                work_code TEXT NOT NULL REFERENCES price_list(code),
                quantity INTEGER NOT NULL,
                price_per_unit REAL NOT NULL,
                total REAL NOT NULL,
                work_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                id SERIAL PRIMARY KEY,
                worker_id BIGINT NOT NULL REFERENCES workers(telegram_id),
                amount REAL NOT NULL,
                comment TEXT DEFAULT '',
                advance_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS penalties (
                id SERIAL PRIMARY KEY,
                worker_id BIGINT NOT NULL REFERENCES workers(telegram_id),
                amount REAL NOT NULL,
                reason TEXT DEFAULT '',
                penalty_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                evening_hour INTEGER DEFAULT 18,
                evening_minute INTEGER DEFAULT 0,
                late_hour INTEGER DEFAULT 20,
                late_minute INTEGER DEFAULT 0,
                report_hour INTEGER DEFAULT 21,
                report_minute INTEGER DEFAULT 0,
                evening_enabled BOOLEAN DEFAULT TRUE,
                late_enabled BOOLEAN DEFAULT TRUE,
                report_enabled BOOLEAN DEFAULT TRUE
            )
        """)
        
        count = await conn.fetchval("SELECT COUNT(*) FROM reminder_settings")
        if count == 0:
            await conn.execute("""
                INSERT INTO reminder_settings 
                (id, evening_hour, evening_minute, late_hour, late_minute, 
                 report_hour, report_minute, evening_enabled, late_enabled, report_enabled)
                VALUES (1, 18, 0, 20, 0, 21, 0, TRUE, TRUE, TRUE)
            """)
        
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_worklog_worker_date ON work_log(worker_id, work_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_worklog_date ON work_log(work_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_advances_worker_date ON advances(worker_id, advance_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_penalties_worker_date ON penalties(worker_id, penalty_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_worker_categories ON worker_categories(worker_id, category_code)")


async def close_db():
    """Закрытие пула соединений"""
    global pool
    if pool:
        await pool.close()


# ==================== КАТЕГОРИИ ====================

async def add_category(code: str, name: str, emoji: str = "📦"):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO categories (code, name, emoji) VALUES ($1, $2, $3)
            ON CONFLICT (code) DO UPDATE SET name = $2, emoji = $3
        """, code, name, emoji)


async def get_categories():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT code, name, emoji FROM categories ORDER BY name")
        return [tuple(row) for row in rows]


async def delete_category(code: str):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM worker_categories WHERE category_code = $1", code)
        await conn.execute("UPDATE price_list SET is_active = FALSE WHERE category_code = $1", code)
        await conn.execute("DELETE FROM categories WHERE code = $1", code)


# ==================== РАБОТНИКИ ====================

async def add_worker(telegram_id: int, name: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO workers (telegram_id, name) VALUES ($1, $2)
            ON CONFLICT (telegram_id) DO UPDATE SET name = $2
        """, telegram_id, name)


async def worker_exists(telegram_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT 1 FROM workers WHERE telegram_id = $1", telegram_id)
        return result is not None


async def get_all_workers():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id, name FROM workers ORDER BY name")
        return [tuple(row) for row in rows]


async def delete_worker(telegram_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM worker_categories WHERE worker_id = $1", telegram_id)
        await conn.execute("DELETE FROM workers WHERE telegram_id = $1", telegram_id)


async def rename_worker(telegram_id: int, new_name: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE workers SET name = $1 WHERE telegram_id = $2", new_name, telegram_id)


# ==================== СВЯЗЬ РАБОТНИК-КАТЕГОРИЯ ====================

async def assign_category_to_worker(worker_id: int, category_code: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO worker_categories (worker_id, category_code) VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """, worker_id, category_code)


async def remove_category_from_worker(worker_id: int, category_code: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM worker_categories WHERE worker_id = $1 AND category_code = $2",
            worker_id, category_code)


async def get_worker_categories(worker_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.code, c.name, c.emoji
            FROM worker_categories wc
            JOIN categories c ON wc.category_code = c.code
            WHERE wc.worker_id = $1
            ORDER BY c.name
        """, worker_id)
        return [tuple(row) for row in rows]


async def get_workers_in_category(category_code: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.telegram_id, w.name
            FROM worker_categories wc
            JOIN workers w ON wc.worker_id = w.telegram_id
            WHERE wc.category_code = $1
            ORDER BY w.name
        """, category_code)
        return [tuple(row) for row in rows]


# ==================== ПРАЙС-ЛИСТ ====================

async def add_price_item(code: str, name: str, price: float, category_code: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO price_list (code, name, price, category_code, is_active)
            VALUES ($1, $2, $3, $4, TRUE)
            ON CONFLICT (code) DO UPDATE SET name = $2, price = $3, category_code = $4, is_active = TRUE
        """, code, name, price, category_code)


async def get_price_list():
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT pl.code, pl.name, pl.price, pl.category_code, c.name, c.emoji
            FROM price_list pl
            JOIN categories c ON pl.category_code = c.code
            WHERE pl.is_active = TRUE
            ORDER BY c.name, pl.name
        """)
        return [tuple(row) for row in rows]


async def get_price_list_for_worker(worker_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT pl.code, pl.name, pl.price, pl.category_code
            FROM price_list pl
            JOIN worker_categories wc ON pl.category_code = wc.category_code
            WHERE wc.worker_id = $1 AND pl.is_active = TRUE
            ORDER BY pl.category_code, pl.name
        """, worker_id)
        return [tuple(row) for row in rows]


async def update_price(code: str, new_price: float):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE price_list SET price = $1 WHERE code = $2", new_price, code)


async def delete_price_item_permanently(code: str) -> bool:
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM work_log WHERE work_code = $1", code)
        if count > 0:
            await conn.execute("UPDATE price_list SET is_active = FALSE WHERE code = $1", code)
            return False
        else:
            await conn.execute("DELETE FROM price_list WHERE code = $1", code)
            return True


# ==================== ЗАПИСИ О РАБОТЕ ====================

async def add_work(worker_id: int, work_code: str, quantity: int, price: float, work_date=None) -> float:
    work_date = parse_date(work_date)
    total = quantity * price
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO work_log (worker_id, work_code, quantity, price_per_unit, total, work_date)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, worker_id, work_code, quantity, price, total, work_date)
    return total


async def delete_last_entry(worker_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM work_log WHERE id = (
                SELECT id FROM work_log WHERE worker_id = $1
                ORDER BY created_at DESC LIMIT 1
            )
        """, worker_id)


# ==================== ОТЧЁТЫ ====================

async def get_daily_total(worker_id: int, target_date=None):
    target_date = parse_date(target_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT work_code, SUM(quantity), price_per_unit, SUM(total)
            FROM work_log
            WHERE worker_id = $1 AND work_date = $2
            GROUP BY work_code, price_per_unit
        """, worker_id, target_date)
        return [tuple(row) for row in rows]


async def get_monthly_total(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT work_code, SUM(quantity), price_per_unit, SUM(total)
            FROM work_log
            WHERE worker_id = $1
              AND EXTRACT(YEAR FROM work_date) = $2
              AND EXTRACT(MONTH FROM work_date) = $3
            GROUP BY work_code, price_per_unit
        """, worker_id, year, month)
        return [tuple(row) for row in rows]


async def get_all_workers_daily_summary(target_date=None):
    target_date = parse_date(target_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.telegram_id, w.name, COALESCE(SUM(wl.total), 0)
            FROM workers w
            LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id AND wl.work_date = $1
            GROUP BY w.telegram_id, w.name
            ORDER BY w.name
        """, target_date)
        return [tuple(row) for row in rows]


async def get_all_workers_monthly_summary(year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.telegram_id, w.name, COALESCE(SUM(wl.total), 0)
            FROM workers w
            LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id
                AND EXTRACT(YEAR FROM wl.work_date) = $2
                AND EXTRACT(MONTH FROM wl.work_date) = $3
            GROUP BY w.telegram_id, w.name
            ORDER BY w.name
        """, year, month)
        return [tuple(row) for row in rows]


async def get_workers_without_records(target_date=None):
    target_date = parse_date(target_date)
    async with pool.acquire() as conn:
        all_workers = await conn.fetch("SELECT telegram_id, name FROM workers")
        with_records = await conn.fetch(
            "SELECT DISTINCT worker_id FROM work_log WHERE work_date = $1", target_date)
        with_records_set = {r['worker_id'] for r in with_records}
        return [(r['telegram_id'], r['name']) for r in all_workers 
                if r['telegram_id'] not in with_records_set]


async def get_monthly_by_days(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT wl.work_date::TEXT, pl.name, SUM(wl.quantity),
                   wl.price_per_unit, SUM(wl.total)
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = $1
              AND EXTRACT(YEAR FROM wl.work_date) = $2
              AND EXTRACT(MONTH FROM wl.work_date) = $3
            GROUP BY wl.work_date, pl.name, wl.price_per_unit
            ORDER BY wl.work_date, pl.name
        """, worker_id, year, month)
        return [tuple(row) for row in rows]


async def get_today_entries(worker_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total, 
                   wl.created_at::TEXT
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = $1 AND wl.work_date = $2
            ORDER BY wl.created_at
        """, worker_id, date.today())
        return [tuple(row) for row in rows]


async def get_worker_entries_by_date(worker_id: int, target_date):
    target_date = parse_date(target_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
                   wl.work_date::TEXT, wl.created_at::TEXT
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = $1 AND wl.work_date = $2
            ORDER BY wl.created_at
        """, worker_id, target_date)
        return [tuple(row) for row in rows]


async def get_worker_recent_entries(worker_id: int, limit: int = 20):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
                   wl.work_date::TEXT, wl.created_at::TEXT
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE wl.worker_id = $1
            ORDER BY wl.work_date DESC, wl.created_at DESC
            LIMIT $2
        """, worker_id, limit)
        return [tuple(row) for row in rows]


async def delete_entry_by_id(entry_id: int):
    async with pool.acquire() as conn:
        entry = await conn.fetchrow("""
            SELECT wl.id, pl.name, wl.quantity, wl.total, wl.work_date::TEXT, w.name
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN workers w ON wl.worker_id = w.telegram_id
            WHERE wl.id = $1
        """, entry_id)
        if entry:
            await conn.execute("DELETE FROM work_log WHERE id = $1", entry_id)
            return tuple(entry)
        return None


async def update_entry_quantity(entry_id: int, new_quantity: int) -> bool:
    async with pool.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT price_per_unit FROM work_log WHERE id = $1", entry_id)
        if entry:
            new_total = new_quantity * entry['price_per_unit']
            await conn.execute(
                "UPDATE work_log SET quantity = $1, total = $2 WHERE id = $3",
                new_quantity, new_total, entry_id)
            return True
        return False


async def get_entry_by_id(entry_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
                   wl.work_date::TEXT, wl.worker_id, w.name
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN workers w ON wl.worker_id = w.telegram_id
            WHERE wl.id = $1
        """, entry_id)
        return tuple(row) if row else None


async def get_worker_monthly_details(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT pl.name, c.emoji, c.name, SUM(wl.quantity),
                   wl.price_per_unit, SUM(wl.total)
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE wl.worker_id = $1
              AND EXTRACT(YEAR FROM wl.work_date) = $2
              AND EXTRACT(MONTH FROM wl.work_date) = $3
            GROUP BY pl.name, c.emoji, c.name, wl.price_per_unit
            ORDER BY c.name, pl.name
        """, worker_id, year, month)
        return [tuple(row) for row in rows]


async def get_all_workers_monthly_details(year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.telegram_id, w.name,
                   pl.name, c.emoji, c.name,
                   SUM(wl.quantity), wl.price_per_unit, SUM(wl.total),
                   COUNT(DISTINCT wl.work_date)
            FROM workers w
            LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id
                AND EXTRACT(YEAR FROM wl.work_date) = $1
                AND EXTRACT(MONTH FROM wl.work_date) = $2
            LEFT JOIN price_list pl ON wl.work_code = pl.code
            LEFT JOIN categories c ON pl.category_code = c.code
            GROUP BY w.telegram_id, w.name, pl.name, c.emoji, c.name, wl.price_per_unit
            ORDER BY w.name, c.name, pl.name
        """, year, month)
        return [tuple(row) for row in rows]


async def get_admin_monthly_detailed_all(year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                w.telegram_id,
                w.name AS worker_name,
                c.name AS category_name,
                c.emoji AS category_emoji,
                wl.work_date::TEXT,
                pl.name AS work_name,
                wl.quantity,
                wl.price_per_unit,
                wl.total
            FROM work_log wl
            JOIN workers w ON wl.worker_id = w.telegram_id
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE EXTRACT(YEAR FROM wl.work_date) = $1
              AND EXTRACT(MONTH FROM wl.work_date) = $2
            ORDER BY w.name, c.name, wl.work_date, wl.id
        """, year, month)
        return [tuple(row) for row in rows]


# ==================== ОПТИМИЗИРОВАННЫЕ ЗАПРОСЫ ====================

async def get_all_workers_balance(year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
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
                WHERE EXTRACT(YEAR FROM work_date) = $1 AND EXTRACT(MONTH FROM work_date) = $2
                GROUP BY worker_id
            ) earn ON w.telegram_id = earn.worker_id
            LEFT JOIN (
                SELECT worker_id, SUM(amount) as total_advance
                FROM advances
                WHERE EXTRACT(YEAR FROM advance_date) = $1 AND EXTRACT(MONTH FROM advance_date) = $2
                GROUP BY worker_id
            ) adv ON w.telegram_id = adv.worker_id
            LEFT JOIN (
                SELECT worker_id, SUM(amount) as total_penalty
                FROM penalties
                WHERE EXTRACT(YEAR FROM penalty_date) = $1 AND EXTRACT(MONTH FROM penalty_date) = $2
                GROUP BY worker_id
            ) pen ON w.telegram_id = pen.worker_id
            ORDER BY w.name
        """, year, month)
        return [tuple(row) for row in rows]


async def get_worker_full_stats(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        earn_row = await conn.fetchrow("""
            SELECT 
                COALESCE(SUM(wl.total), 0) as earned,
                COUNT(DISTINCT wl.work_date) as work_days
            FROM work_log wl
            WHERE wl.worker_id = $1
              AND EXTRACT(YEAR FROM wl.work_date) = $2
              AND EXTRACT(MONTH FROM wl.work_date) = $3
        """, worker_id, year, month)

        adv_row = await conn.fetchrow("""
            SELECT COALESCE(SUM(amount), 0)
            FROM advances
            WHERE worker_id = $1
              AND EXTRACT(YEAR FROM advance_date) = $2
              AND EXTRACT(MONTH FROM advance_date) = $3
        """, worker_id, year, month)

        pen_row = await conn.fetchrow("""
            SELECT COALESCE(SUM(amount), 0)
            FROM penalties
            WHERE worker_id = $1
              AND EXTRACT(YEAR FROM penalty_date) = $2
              AND EXTRACT(MONTH FROM penalty_date) = $3
        """, worker_id, year, month)

    return {
        'earned': earn_row['earned'],
        'work_days': earn_row['work_days'],
        'advances': adv_row[0],
        'penalties': pen_row[0],
        'balance': earn_row['earned'] - adv_row[0] - pen_row[0]
    }


# ==================== АВАНСЫ ====================

async def add_advance(worker_id: int, amount: float, comment: str = "", advance_date=None):
    advance_date = parse_date(advance_date)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO advances (worker_id, amount, comment, advance_date)
            VALUES ($1, $2, $3, $4)
        """, worker_id, amount, comment, advance_date)


async def get_worker_advances(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, amount, comment, advance_date::TEXT, created_at::TEXT
            FROM advances
            WHERE worker_id = $1
              AND EXTRACT(YEAR FROM advance_date) = $2
              AND EXTRACT(MONTH FROM advance_date) = $3
            ORDER BY advance_date
        """, worker_id, year, month)
        return [tuple(row) for row in rows]


async def get_worker_advances_total(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        result = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0)
            FROM advances
            WHERE worker_id = $1
              AND EXTRACT(YEAR FROM advance_date) = $2
              AND EXTRACT(MONTH FROM advance_date) = $3
        """, worker_id, year, month)
        return result


async def delete_advance(advance_id: int):
    async with pool.acquire() as conn:
        advance = await conn.fetchrow(
            "SELECT id, amount, comment, advance_date::TEXT, worker_id FROM advances WHERE id = $1",
            advance_id)
        if advance:
            await conn.execute("DELETE FROM advances WHERE id = $1", advance_id)
            return tuple(advance)
        return None


async def get_all_advances_monthly(year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.telegram_id, w.name,
                   COALESCE(SUM(a.amount), 0) as total_advance
            FROM workers w
            LEFT JOIN advances a ON w.telegram_id = a.worker_id
                AND EXTRACT(YEAR FROM a.advance_date) = $1
                AND EXTRACT(MONTH FROM a.advance_date) = $2
            GROUP BY w.telegram_id, w.name
            ORDER BY w.name
        """, year, month)
        return [tuple(row) for row in rows]


async def get_worker_entries_by_custom_date(worker_id: int, target_date):
    target_date = parse_date(target_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT wl.id, pl.name, c.name, c.emoji, wl.quantity,
                   wl.price_per_unit, wl.total, wl.created_at::TEXT
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE wl.worker_id = $1 AND wl.work_date = $2
            ORDER BY wl.created_at
        """, worker_id, target_date)
        return [tuple(row) for row in rows]


# ==================== ШТРАФЫ ====================

async def add_penalty(worker_id: int, amount: float, reason: str = "", penalty_date=None):
    penalty_date = parse_date(penalty_date)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO penalties (worker_id, amount, reason, penalty_date)
            VALUES ($1, $2, $3, $4)
        """, worker_id, amount, reason, penalty_date)


async def get_worker_penalties(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, amount, reason, penalty_date::TEXT, created_at::TEXT
            FROM penalties
            WHERE worker_id = $1
              AND EXTRACT(YEAR FROM penalty_date) = $2
              AND EXTRACT(MONTH FROM penalty_date) = $3
            ORDER BY penalty_date
        """, worker_id, year, month)
        return [tuple(row) for row in rows]


async def get_worker_penalties_total(worker_id: int, year: int = None, month: int = None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    async with pool.acquire() as conn:
        result = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0)
            FROM penalties
            WHERE worker_id = $1
              AND EXTRACT(YEAR FROM penalty_date) = $2
              AND EXTRACT(MONTH FROM penalty_date) = $3
        """, worker_id, year, month)
        return result


async def delete_penalty(penalty_id: int):
    async with pool.acquire() as conn:
        penalty = await conn.fetchrow(
            "SELECT id, amount, reason, penalty_date::TEXT, worker_id FROM penalties WHERE id = $1",
            penalty_id)
        if penalty:
            await conn.execute("DELETE FROM penalties WHERE id = $1", penalty_id)
            return tuple(penalty)
        return None


# ==================== НАСТРОЙКИ НАПОМИНАНИЙ ====================

async def get_reminder_settings():
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM reminder_settings WHERE id = 1")
        if row:
            return {
                'evening_hour': row['evening_hour'],
                'evening_minute': row['evening_minute'],
                'late_hour': row['late_hour'],
                'late_minute': row['late_minute'],
                'report_hour': row['report_hour'],
                'report_minute': row['report_minute'],
                'evening_enabled': row['evening_enabled'],
                'late_enabled': row['late_enabled'],
                'report_enabled': row['report_enabled'],
            }
        return {
            'evening_hour': 18, 'evening_minute': 0,
            'late_hour': 20, 'late_minute': 0,
            'report_hour': 21, 'report_minute': 0,
            'evening_enabled': True, 'late_enabled': True, 'report_enabled': True,
        }


async def update_reminder_settings(**kwargs):
    async with pool.acquire() as conn:
        sets = ", ".join([f"{k} = ${i+1}" for i, k in enumerate(kwargs.keys())])
        vals = list(kwargs.values())
        vals.append(1)
        await conn.execute(
            f"UPDATE reminder_settings SET {sets} WHERE id = ${len(vals)}", *vals)