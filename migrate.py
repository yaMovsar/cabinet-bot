import asyncio
import aiosqlite
import asyncpg
import os

# Настройки
SQLITE_PATH = "production.db"  # Путь к твоему SQLite файлу
POSTGRES_URL = "postgresql://postgres:gnNPxfJjALcDHAGANzfjvFOYiUhiNBvc@postgres.railway.internal:5432/railway"

# Для локального запуска используй внешний URL:
# POSTGRES_URL = "postgresql://postgres:gnNPxfJjALcDHAGANzfjvFOYiUhiNBvc@autorack.proxy.rlwy.net:PORT/railway"
# PORT узнай в Railway → PostgreSQL → Settings → TCP Proxy


async def migrate():
    print("🚀 Начинаю миграцию SQLite → PostgreSQL...")
    
    # Проверка SQLite файла
    if not os.path.exists(SQLITE_PATH):
        print(f"❌ Файл {SQLITE_PATH} не найден!")
        print("   Скачай бэкап из Railway Volume или укажи правильный путь")
        return
    
    # Подключение к базам
    print("📂 Подключаюсь к SQLite...")
    sqlite = await aiosqlite.connect(SQLITE_PATH)
    
    print("🐘 Подключаюсь к PostgreSQL...")
    pg = await asyncpg.connect(POSTGRES_URL)
    
    try:
        # ===== 1. СОЗДАНИЕ ТАБЛИЦ =====
        print("\n📋 Создаю таблицы в PostgreSQL...")
        
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                telegram_id BIGINT PRIMARY KEY,
                name TEXT NOT NULL,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                emoji TEXT DEFAULT '📦'
            )
        """)
        
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS price_list (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category_code TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS worker_categories (
                worker_id BIGINT NOT NULL,
                category_code TEXT NOT NULL,
                PRIMARY KEY (worker_id, category_code)
            )
        """)
        
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS work_log (
                id SERIAL PRIMARY KEY,
                worker_id BIGINT NOT NULL,
                work_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price_per_unit REAL NOT NULL,
                total REAL NOT NULL,
                work_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                id SERIAL PRIMARY KEY,
                worker_id BIGINT NOT NULL,
                amount REAL NOT NULL,
                comment TEXT DEFAULT '',
                advance_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS penalties (
                id SERIAL PRIMARY KEY,
                worker_id BIGINT NOT NULL,
                amount REAL NOT NULL,
                reason TEXT DEFAULT '',
                penalty_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await pg.execute("""
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
        
        print("✅ Таблицы созданы!")
        
        # ===== 2. МИГРАЦИЯ ДАННЫХ =====
        
        # --- workers ---
        print("\n👥 Переношу работников...")
        cursor = await sqlite.execute("SELECT telegram_id, name, registered_at FROM workers")
        workers = await cursor.fetchall()
        for row in workers:
            await pg.execute("""
                INSERT INTO workers (telegram_id, name, registered_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (telegram_id) DO UPDATE SET name = $2
            """, row[0], row[1], row[2])
        print(f"   ✅ Перенесено работников: {len(workers)}")
        
        # --- categories ---
        print("\n📂 Переношу категории...")
        cursor = await sqlite.execute("SELECT code, name, emoji FROM categories")
        categories = await cursor.fetchall()
        for row in categories:
            await pg.execute("""
                INSERT INTO categories (code, name, emoji)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET name = $2, emoji = $3
            """, row[0], row[1], row[2])
        print(f"   ✅ Перенесено категорий: {len(categories)}")
        
        # --- price_list ---
        print("\n💰 Переношу прайс-лист...")
        cursor = await sqlite.execute("SELECT code, name, price, category_code, is_active FROM price_list")
        prices = await cursor.fetchall()
        for row in prices:
            await pg.execute("""
                INSERT INTO price_list (code, name, price, category_code, is_active)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (code) DO UPDATE SET name = $2, price = $3, category_code = $4, is_active = $5
            """, row[0], row[1], row[2], row[3], bool(row[4]))
        print(f"   ✅ Перенесено позиций: {len(prices)}")
        
        # --- worker_categories ---
        print("\n🔗 Переношу связи работник-категория...")
        cursor = await sqlite.execute("SELECT worker_id, category_code FROM worker_categories")
        wc = await cursor.fetchall()
        for row in wc:
            await pg.execute("""
                INSERT INTO worker_categories (worker_id, category_code)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
            """, row[0], row[1])
        print(f"   ✅ Перенесено связей: {len(wc)}")
        
        # --- work_log ---
        print("\n📝 Переношу записи работ...")
        cursor = await sqlite.execute("""
            SELECT worker_id, work_code, quantity, price_per_unit, total, work_date, created_at
            FROM work_log ORDER BY id
        """)
        logs = await cursor.fetchall()
        for row in logs:
            await pg.execute("""
                INSERT INTO work_log (worker_id, work_code, quantity, price_per_unit, total, work_date, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, row[0], row[1], row[2], row[3], row[4], row[5], row[6])
        print(f"   ✅ Перенесено записей: {len(logs)}")
        
        # --- advances ---
        print("\n💳 Переношу авансы...")
        cursor = await sqlite.execute("""
            SELECT worker_id, amount, comment, advance_date, created_at
            FROM advances ORDER BY id
        """)
        advances = await cursor.fetchall()
        for row in advances:
            await pg.execute("""
                INSERT INTO advances (worker_id, amount, comment, advance_date, created_at)
                VALUES ($1, $2, $3, $4, $5)
            """, row[0], row[1], row[2] or '', row[3], row[4])
        print(f"   ✅ Перенесено авансов: {len(advances)}")
        
        # --- penalties ---
        print("\n⚠️ Переношу штрафы...")
        cursor = await sqlite.execute("""
            SELECT worker_id, amount, reason, penalty_date, created_at
            FROM penalties ORDER BY id
        """)
        penalties = await cursor.fetchall()
        for row in penalties:
            await pg.execute("""
                INSERT INTO penalties (worker_id, amount, reason, penalty_date, created_at)
                VALUES ($1, $2, $3, $4, $5)
            """, row[0], row[1], row[2] or '', row[3], row[4])
        print(f"   ✅ Перенесено штрафов: {len(penalties)}")
        
        # --- reminder_settings ---
        print("\n⏰ Переношу настройки напоминаний...")
        cursor = await sqlite.execute("SELECT * FROM reminder_settings WHERE id = 1")
        settings = await cursor.fetchone()
        if settings:
            await pg.execute("""
                INSERT INTO reminder_settings 
                (id, evening_hour, evening_minute, late_hour, late_minute,
                 report_hour, report_minute, evening_enabled, late_enabled, report_enabled)
                VALUES (1, $1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (id) DO UPDATE SET
                    evening_hour = $1, evening_minute = $2,
                    late_hour = $3, late_minute = $4,
                    report_hour = $5, report_minute = $6,
                    evening_enabled = $7, late_enabled = $8, report_enabled = $9
            """, settings[1], settings[2], settings[3], settings[4],
                settings[5], settings[6], bool(settings[7]), bool(settings[8]), bool(settings[9]))
            print("   ✅ Настройки перенесены!")
        
        # ===== 3. СОЗДАНИЕ ИНДЕКСОВ =====
        print("\n📇 Создаю индексы...")
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_worklog_worker_date ON work_log(worker_id, work_date)")
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_worklog_date ON work_log(work_date)")
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_advances_worker_date ON advances(worker_id, advance_date)")
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_penalties_worker_date ON penalties(worker_id, penalty_date)")
        print("   ✅ Индексы созданы!")
        
        # ===== ИТОГО =====
        print("\n" + "="*50)
        print("🎉 МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("="*50)
        print(f"""
📊 Перенесено:
   👥 Работников: {len(workers)}
   📂 Категорий: {len(categories)}
   💰 Позиций прайса: {len(prices)}
   🔗 Связей: {len(wc)}
   📝 Записей работ: {len(logs)}
   💳 Авансов: {len(advances)}
   ⚠️ Штрафов: {len(penalties)}
        """)
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        raise
    finally:
        await sqlite.close()
        await pg.close()


if __name__ == "__main__":
    asyncio.run(migrate())