import sqlite3
from datetime import date

DB_NAME = "production.db"


def _connect():
    """Возвращает подключение к базе данных."""
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = _connect()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT DEFAULT '📦'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS price_list (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            category_code TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (category_code) REFERENCES categories(code)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS worker_categories (
            worker_id INTEGER NOT NULL,
            category_code TEXT NOT NULL,
            PRIMARY KEY (worker_id, category_code),
            FOREIGN KEY (worker_id) REFERENCES workers(telegram_id),
            FOREIGN KEY (category_code) REFERENCES categories(code)
        )
    """)

    c.execute("""
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

    c.execute("""
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

    conn.commit()
    conn.close()


# ==================== КАТЕГОРИИ ====================

def add_category(code, name, emoji="📦"):
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO categories (code, name, emoji) VALUES (?, ?, ?)",
                 (code, name, emoji))
    conn.commit()
    conn.close()


def get_categories():
    conn = _connect()
    rows = conn.execute("SELECT code, name, emoji FROM categories ORDER BY name").fetchall()
    conn.close()
    return rows


def delete_category(code):
    conn = _connect()
    conn.execute("DELETE FROM worker_categories WHERE category_code = ?", (code,))
    conn.execute("UPDATE price_list SET is_active = 0 WHERE category_code = ?", (code,))
    conn.execute("DELETE FROM categories WHERE code = ?", (code,))
    conn.commit()
    conn.close()


# ==================== РАБОТНИКИ ====================

def add_worker(telegram_id, name):
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO workers (telegram_id, name) VALUES (?, ?)",
                 (telegram_id, name))
    conn.commit()
    conn.close()


def get_all_workers():
    conn = _connect()
    rows = conn.execute("SELECT telegram_id, name FROM workers ORDER BY name").fetchall()
    conn.close()
    return rows


def delete_worker(telegram_id):
    conn = _connect()
    conn.execute("DELETE FROM worker_categories WHERE worker_id = ?", (telegram_id,))
    conn.execute("DELETE FROM workers WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()


# ==================== СВЯЗЬ РАБОТНИК-КАТЕГОРИЯ ====================

def assign_category_to_worker(worker_id, category_code):
    conn = _connect()
    conn.execute("INSERT OR IGNORE INTO worker_categories (worker_id, category_code) VALUES (?, ?)",
                 (worker_id, category_code))
    conn.commit()
    conn.close()


def remove_category_from_worker(worker_id, category_code):
    conn = _connect()
    conn.execute("DELETE FROM worker_categories WHERE worker_id = ? AND category_code = ?",
                 (worker_id, category_code))
    conn.commit()
    conn.close()


def get_worker_categories(worker_id):
    conn = _connect()
    rows = conn.execute("""
        SELECT c.code, c.name, c.emoji
        FROM worker_categories wc
        JOIN categories c ON wc.category_code = c.code
        WHERE wc.worker_id = ?
        ORDER BY c.name
    """, (worker_id,)).fetchall()
    conn.close()
    return rows


def get_workers_in_category(category_code):
    conn = _connect()
    rows = conn.execute("""
        SELECT w.telegram_id, w.name
        FROM worker_categories wc
        JOIN workers w ON wc.worker_id = w.telegram_id
        WHERE wc.category_code = ?
        ORDER BY w.name
    """, (category_code,)).fetchall()
    conn.close()
    return rows


# ==================== ПРАЙС-ЛИСТ ====================

def add_price_item(code, name, price, category_code):
    conn = _connect()
    conn.execute("""
        INSERT OR REPLACE INTO price_list (code, name, price, category_code, is_active)
        VALUES (?, ?, ?, ?, 1)
    """, (code, name, price, category_code))
    conn.commit()
    conn.close()


def get_price_list():
    conn = _connect()
    rows = conn.execute("""
        SELECT pl.code, pl.name, pl.price, pl.category_code, c.name, c.emoji
        FROM price_list pl
        JOIN categories c ON pl.category_code = c.code
        WHERE pl.is_active = 1
        ORDER BY c.name, pl.name
    """).fetchall()
    conn.close()
    return rows


def get_price_list_for_worker(worker_id):
    conn = _connect()
    rows = conn.execute("""
        SELECT pl.code, pl.name, pl.price, pl.category_code
        FROM price_list pl
        JOIN worker_categories wc ON pl.category_code = wc.category_code
        WHERE wc.worker_id = ? AND pl.is_active = 1
        ORDER BY pl.category_code, pl.name
    """, (worker_id,)).fetchall()
    conn.close()
    return rows


def update_price(code, new_price):
    conn = _connect()
    conn.execute("UPDATE price_list SET price = ? WHERE code = ?", (new_price, code))
    conn.commit()
    conn.close()


def delete_price_item_permanently(code):
    conn = _connect()
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM work_log WHERE work_code = ?", (code,)).fetchone()[0]
    if count > 0:
        c.execute("UPDATE price_list SET is_active = 0 WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        return False
    else:
        c.execute("DELETE FROM price_list WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        return True


# ==================== ЗАПИСИ О РАБОТЕ ====================

def add_work(worker_id, work_code, quantity, price, work_date=None):
    if work_date is None:
        work_date = date.today()
    total = quantity * price
    conn = _connect()
    conn.execute("""
        INSERT INTO work_log (worker_id, work_code, quantity, price_per_unit, total, work_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (worker_id, work_code, quantity, price, total, work_date))
    conn.commit()
    conn.close()
    return total


def delete_last_entry(worker_id):
    conn = _connect()
    conn.execute("""
        DELETE FROM work_log WHERE id = (
            SELECT id FROM work_log WHERE worker_id = ?
            ORDER BY created_at DESC LIMIT 1
        )
    """, (worker_id,))
    conn.commit()
    conn.close()


# ==================== ОТЧЁТЫ ====================

def get_daily_total(worker_id, target_date=None):
    if target_date is None:
        target_date = date.today()
    conn = _connect()
    rows = conn.execute("""
        SELECT work_code, SUM(quantity), price_per_unit, SUM(total)
        FROM work_log
        WHERE worker_id = ? AND work_date = ?
        GROUP BY work_code
    """, (worker_id, target_date)).fetchall()
    conn.close()
    return rows


def get_monthly_total(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
        SELECT work_code, SUM(quantity), price_per_unit, SUM(total)
        FROM work_log
        WHERE worker_id = ?
          AND strftime('%Y', work_date) = ?
          AND strftime('%m', work_date) = ?
        GROUP BY work_code
    """, (worker_id, str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


def get_all_workers_daily_summary(target_date=None):
    if target_date is None:
        target_date = date.today()
    conn = _connect()
    rows = conn.execute("""
        SELECT w.telegram_id, w.name, COALESCE(SUM(wl.total), 0)
        FROM workers w
        LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id AND wl.work_date = ?
        GROUP BY w.telegram_id, w.name
        ORDER BY w.name
    """, (target_date,)).fetchall()
    conn.close()
    return rows


def get_all_workers_monthly_summary(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
        SELECT w.telegram_id, w.name, COALESCE(SUM(wl.total), 0)
        FROM workers w
        LEFT JOIN work_log wl ON w.telegram_id = wl.worker_id
            AND strftime('%Y', wl.work_date) = ?
            AND strftime('%m', wl.work_date) = ?
        GROUP BY w.telegram_id, w.name
        ORDER BY w.name
    """, (str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


def get_workers_without_records(target_date=None):
    if target_date is None:
        target_date = date.today()
    conn = _connect()
    all_workers = conn.execute("SELECT telegram_id, name FROM workers").fetchall()
    with_records = {r[0] for r in conn.execute(
        "SELECT DISTINCT worker_id FROM work_log WHERE work_date = ?",
        (target_date,)).fetchall()}
    conn.close()
    return [(tid, name) for tid, name in all_workers if tid not in with_records]


def get_monthly_by_days(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
        SELECT wl.work_date, pl.name, SUM(wl.quantity),
               wl.price_per_unit, SUM(wl.total)
        FROM work_log wl
        JOIN price_list pl ON wl.work_code = pl.code
        WHERE wl.worker_id = ?
          AND strftime('%Y', wl.work_date) = ?
          AND strftime('%m', wl.work_date) = ?
        GROUP BY wl.work_date, pl.name, wl.price_per_unit
        ORDER BY wl.work_date, pl.name
    """, (worker_id, str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


def get_today_entries(worker_id):
    conn = _connect()
    rows = conn.execute("""
        SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total, wl.created_at
        FROM work_log wl
        JOIN price_list pl ON wl.work_code = pl.code
        WHERE wl.worker_id = ? AND wl.work_date = ?
        ORDER BY wl.created_at
    """, (worker_id, date.today())).fetchall()
    conn.close()
    return rows


def get_worker_entries_by_date(worker_id, target_date):
    conn = _connect()
    rows = conn.execute("""
        SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
               wl.work_date, wl.created_at
        FROM work_log wl
        JOIN price_list pl ON wl.work_code = pl.code
        WHERE wl.worker_id = ? AND wl.work_date = ?
        ORDER BY wl.created_at
    """, (worker_id, target_date)).fetchall()
    conn.close()
    return rows


def get_worker_recent_entries(worker_id, limit=20):
    conn = _connect()
    rows = conn.execute("""
        SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
               wl.work_date, wl.created_at
        FROM work_log wl
        JOIN price_list pl ON wl.work_code = pl.code
        WHERE wl.worker_id = ?
        ORDER BY wl.work_date DESC, wl.created_at DESC
        LIMIT ?
    """, (worker_id, limit)).fetchall()
    conn.close()
    return rows


def delete_entry_by_id(entry_id):
    conn = _connect()
    entry = conn.execute("""
        SELECT wl.id, pl.name, wl.quantity, wl.total, wl.work_date, w.name
        FROM work_log wl
        JOIN price_list pl ON wl.work_code = pl.code
        JOIN workers w ON wl.worker_id = w.telegram_id
        WHERE wl.id = ?
    """, (entry_id,)).fetchone()
    if entry:
        conn.execute("DELETE FROM work_log WHERE id = ?", (entry_id,))
        conn.commit()
    conn.close()
    return entry


def update_entry_quantity(entry_id, new_quantity):
    conn = _connect()
    c = conn.cursor()
    entry = c.execute("SELECT price_per_unit FROM work_log WHERE id = ?", (entry_id,)).fetchone()
    if entry:
        new_total = new_quantity * entry[0]
        c.execute("UPDATE work_log SET quantity = ?, total = ? WHERE id = ?",
                  (new_quantity, new_total, entry_id))
        conn.commit()
    conn.close()
    return entry is not None


def get_entry_by_id(entry_id):
    conn = _connect()
    entry = conn.execute("""
        SELECT wl.id, pl.name, wl.quantity, wl.price_per_unit, wl.total,
               wl.work_date, wl.worker_id, w.name
        FROM work_log wl
        JOIN price_list pl ON wl.work_code = pl.code
        JOIN workers w ON wl.worker_id = w.telegram_id
        WHERE wl.id = ?
    """, (entry_id,)).fetchone()
    conn.close()
    return entry


def get_worker_monthly_details(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
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
    """, (worker_id, str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


def get_all_workers_monthly_details(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
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
    """, (str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


def get_admin_monthly_detailed_all(year=None, month=None):
    """Все записи всех работников за месяц — с категориями и видами работ"""
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
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
    """, (str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


# ==================== АВАНСЫ ====================

def init_advances_table():
    """Создаёт таблицу авансов если не существует"""
    conn = _connect()
    conn.execute("""
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
    conn.commit()
    conn.close()


def add_advance(worker_id, amount, comment="", advance_date=None):
    if advance_date is None:
        advance_date = date.today()
    conn = _connect()
    conn.execute("""
        INSERT INTO advances (worker_id, amount, comment, advance_date)
        VALUES (?, ?, ?, ?)
    """, (worker_id, amount, comment, advance_date))
    conn.commit()
    conn.close()


def get_worker_advances(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
        SELECT id, amount, comment, advance_date, created_at
        FROM advances
        WHERE worker_id = ?
          AND strftime('%Y', advance_date) = ?
          AND strftime('%m', advance_date) = ?
        ORDER BY advance_date
    """, (worker_id, str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


def get_worker_advances_total(worker_id, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    result = conn.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM advances
        WHERE worker_id = ?
          AND strftime('%Y', advance_date) = ?
          AND strftime('%m', advance_date) = ?
    """, (worker_id, str(year), f"{month:02d}")).fetchone()
    conn.close()
    return result[0]


def delete_advance(advance_id):
    conn = _connect()
    advance = conn.execute(
        "SELECT id, amount, comment, advance_date, worker_id FROM advances WHERE id = ?",
        (advance_id,)
    ).fetchone()
    if advance:
        conn.execute("DELETE FROM advances WHERE id = ?", (advance_id,))
        conn.commit()
    conn.close()
    return advance


def get_all_advances_monthly(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    conn = _connect()
    rows = conn.execute("""
        SELECT w.telegram_id, w.name, 
               COALESCE(SUM(a.amount), 0) as total_advance
        FROM workers w
        LEFT JOIN advances a ON w.telegram_id = a.worker_id
            AND strftime('%Y', a.advance_date) = ?
            AND strftime('%m', a.advance_date) = ?
        GROUP BY w.telegram_id, w.name
        ORDER BY w.name
    """, (str(year), f"{month:02d}")).fetchall()
    conn.close()
    return rows


def get_worker_entries_by_custom_date(worker_id, target_date):
    """Получить записи работника за конкретную дату с подробностями"""
    conn = _connect()
    rows = conn.execute("""
        SELECT wl.id, pl.name, c.name, c.emoji, wl.quantity, 
               wl.price_per_unit, wl.total, wl.created_at
        FROM work_log wl
        JOIN price_list pl ON wl.work_code = pl.code
        JOIN categories c ON pl.category_code = c.code
        WHERE wl.worker_id = ? AND wl.work_date = ?
        ORDER BY wl.created_at
    """, (worker_id, target_date)).fetchall()
    conn.close()
    return rows