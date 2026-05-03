import asyncpg
import os
from datetime import date, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

DATABASE_URL = os.getenv("DATABASE_URL", "")

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def _styles():
    return {
        "header": Font(bold=True, size=14),
        "th_font": Font(bold=True, size=10, color="FFFFFF"),
        "th_fill": PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid"),
        "total_font": Font(bold=True, size=11),
        "total_fill": PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid"),
        "worker_fill": PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid"),
        "day_fill": PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid"),
        "border": Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        ),
    }


def _cell(ws, row, col, value, s, font=None, fill=None, fmt=None, center=False):
    cell = ws.cell(row=row, column=col, value=value)
    cell.border = s["border"]
    if font:
        cell.font = font
    if fill:
        cell.fill = fill
    if fmt:
        cell.number_format = fmt
    if center:
        cell.alignment = Alignment(horizontal='center')
    return cell


async def generate_monthly_report(year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    s = _styles()
    wb = Workbook()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # ===== ЛИСТ 1: СВОДКА =====
        ws = wb.active
        ws.title = "Сводка"

        ws.merge_cells('A1:F1')
        ws['A1'] = f"Отчёт за {MONTHS_RU[month]} {year}"
        ws['A1'].font = s["header"]
        ws['A1'].alignment = Alignment(horizontal='center')

        ws.merge_cells('A2:F2')
        ws['A2'] = f"Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        ws['A2'].alignment = Alignment(horizontal='center')

        row = 4
        for col, h in enumerate(["№", "Работник", "Категории", "Записей", "Дней", "Итого (₽)"], 1):
            _cell(ws, row, col, h, s, font=s["th_font"], fill=s["th_fill"], center=True)

        workers = await conn.fetch("SELECT telegram_id, name FROM workers ORDER BY name")
        row = 5
        grand = 0

        for idx, worker in enumerate(workers, 1):
            tid, name = worker['telegram_id'], worker['name']
            
            cats = await conn.fetch("""
                SELECT c.emoji, c.name FROM worker_categories wc
                JOIN categories c ON wc.category_code = c.code WHERE wc.worker_id = $1
            """, tid)
            cats_str = ", ".join([f"{c['emoji']}{c['name']}" for c in cats]) if cats else "—"

            stat = await conn.fetchrow("""
                SELECT COUNT(*), COUNT(DISTINCT work_date), COALESCE(SUM(total), 0)
                FROM work_log WHERE worker_id = $1
                AND EXTRACT(YEAR FROM work_date) = $2 AND EXTRACT(MONTH FROM work_date) = $3
            """, tid, year, month)
            cnt, days, total = stat[0], stat[1], stat[2]

            _cell(ws, row, 1, idx, s, center=True)
            _cell(ws, row, 2, name, s)
            _cell(ws, row, 3, cats_str, s)
            _cell(ws, row, 4, cnt, s, center=True)
            _cell(ws, row, 5, days, s, center=True)
            _cell(ws, row, 6, round(total, 2), s, fmt='#,##0.00 ₽')
            grand += total
            row += 1

        _cell(ws, row, 1, "", s, fill=s["total_fill"])
        _cell(ws, row, 2, "ИТОГО", s, font=s["total_font"], fill=s["total_fill"])
        for col in range(3, 6):
            _cell(ws, row, col, "", s, fill=s["total_fill"])
        _cell(ws, row, 6, round(grand, 2), s, font=s["total_font"],
              fill=s["total_fill"], fmt='#,##0.00 ₽')

        for col, w in zip('ABCDEF', [5, 25, 30, 12, 12, 18]):
            ws.column_dimensions[col].width = w

        # ===== ЛИСТ 2: ДЕТАЛИЗАЦИЯ =====
        ws2 = wb.create_sheet("Детализация")
        ws2.merge_cells('A1:G1')
        ws2['A1'] = f"Детализация за {MONTHS_RU[month]} {year}"
        ws2['A1'].font = s["header"]
        ws2['A1'].alignment = Alignment(horizontal='center')

        row = 3
        for worker in workers:
            tid, name = worker['telegram_id'], worker['name']
            
            ws2.merge_cells(f'A{row}:G{row}')
            cell = ws2.cell(row=row, column=1, value=f"👤 {name}")
            cell.font = Font(bold=True, size=12)
            cell.fill = s["worker_fill"]
            row += 1

            for col, h in enumerate(["Дата", "Работа", "Категория", "Кол-во",
                                       "Расценка", "Сумма", "Время"], 1):
                _cell(ws2, row, col, h, s, font=s["th_font"], fill=s["th_fill"], center=True)
            row += 1

            records = await conn.fetch("""
                SELECT wl.work_date::TEXT, pl.name, c.name, wl.quantity,
                       wl.price_per_unit, wl.total, wl.created_at::TEXT
                FROM work_log wl
                JOIN price_list pl ON wl.work_code = pl.code
                JOIN categories c ON pl.category_code = c.code
                WHERE wl.worker_id = $1
                  AND EXTRACT(YEAR FROM wl.work_date) = $2
                  AND EXTRACT(MONTH FROM wl.work_date) = $3
                ORDER BY wl.work_date, wl.created_at
            """, tid, year, month)

            wtotal = 0
            cur_date = ""
            day_total = 0

            for rec in records:
                if rec[0] != cur_date and cur_date != "":
                    for c2 in range(1, 6):
                        _cell(ws2, row, c2, "", s, fill=s["day_fill"])
                    _cell(ws2, row, 5, f"День {cur_date}:", s,
                          font=Font(bold=True, italic=True, size=9), fill=s["day_fill"])
                    _cell(ws2, row, 6, round(day_total, 2), s,
                          font=Font(bold=True, italic=True, size=9),
                          fill=s["day_fill"], fmt='#,##0.00')
                    _cell(ws2, row, 7, "", s, fill=s["day_fill"])
                    row += 1
                    day_total = 0
                cur_date = rec[0]

                _cell(ws2, row, 1, rec[0], s)
                _cell(ws2, row, 2, rec[1], s)
                _cell(ws2, row, 3, rec[2], s)
                _cell(ws2, row, 4, rec[3], s, center=True)
                _cell(ws2, row, 5, round(rec[4], 2), s, fmt='#,##0.00')
                _cell(ws2, row, 6, round(rec[5], 2), s, fmt='#,##0.00')
                _cell(ws2, row, 7, rec[6], s)
                wtotal += rec[5]
                day_total += rec[5]
                row += 1

            if cur_date != "":
                for c2 in range(1, 6):
                    _cell(ws2, row, c2, "", s, fill=s["day_fill"])
                _cell(ws2, row, 5, f"День {cur_date}:", s,
                      font=Font(bold=True, italic=True, size=9), fill=s["day_fill"])
                _cell(ws2, row, 6, round(day_total, 2), s,
                      font=Font(bold=True, italic=True, size=9),
                      fill=s["day_fill"], fmt='#,##0.00')
                _cell(ws2, row, 7, "", s, fill=s["day_fill"])
                row += 1

            if records:
                for col in range(1, 6):
                    _cell(ws2, row, col, "", s, fill=s["total_fill"])
                _cell(ws2, row, 2, f"ИТОГО {name}:", s, font=s["total_font"], fill=s["total_fill"])
                _cell(ws2, row, 6, round(wtotal, 2), s, font=s["total_font"],
                      fill=s["total_fill"], fmt='#,##0.00 ₽')
                _cell(ws2, row, 7, "", s, fill=s["total_fill"])
                row += 1
            else:
                ws2.cell(row=row, column=1, value="Нет записей")
                row += 1
            row += 1

        for col, w in zip('ABCDEFG', [14, 25, 20, 10, 14, 14, 20]):
            ws2.column_dimensions[col].width = w

        # ===== ЛИСТ 3: ПО ДНЯМ =====
        ws3 = wb.create_sheet("По дням")
        ws3.merge_cells('A1:D1')
        ws3['A1'] = f"По дням за {MONTHS_RU[month]} {year}"
        ws3['A1'].font = s["header"]
        ws3['A1'].alignment = Alignment(horizontal='center')

        row = 3
        for col, h in enumerate(["Дата", "Работник", "Работа", "Сумма (₽)"], 1):
            _cell(ws3, row, col, h, s, font=s["th_font"], fill=s["th_fill"], center=True)
        row += 1

        daily = await conn.fetch("""
            SELECT wl.work_date::TEXT, w.name, pl.name, SUM(wl.total)
            FROM work_log wl
            JOIN workers w ON wl.worker_id = w.telegram_id
            JOIN price_list pl ON wl.work_code = pl.code
            WHERE EXTRACT(YEAR FROM wl.work_date) = $1 AND EXTRACT(MONTH FROM wl.work_date) = $2
            GROUP BY wl.work_date, w.name, pl.name
            ORDER BY wl.work_date, w.name
        """, year, month)

        cur_date = ""
        day_sum = 0
        for rec in daily:
            wd, wn, wname, total = rec[0], rec[1], rec[2], rec[3]
            if wd != cur_date and cur_date != "":
                _cell(ws3, row, 1, "", s)
                _cell(ws3, row, 2, f"Итого за {cur_date}:", s,
                      font=Font(bold=True, italic=True, size=9))
                _cell(ws3, row, 3, "", s)
                _cell(ws3, row, 4, round(day_sum, 2), s,
                      font=Font(bold=True, size=9), fmt='#,##0.00')
                row += 1
                day_sum = 0
            cur_date = wd
            _cell(ws3, row, 1, wd, s)
            _cell(ws3, row, 2, wn, s)
            _cell(ws3, row, 3, wname, s)
            _cell(ws3, row, 4, round(total, 2), s, fmt='#,##0.00')
            day_sum += total
            row += 1

        if cur_date:
            _cell(ws3, row, 1, "", s)
            _cell(ws3, row, 2, f"Итого за {cur_date}:", s,
                  font=Font(bold=True, italic=True, size=9))
            _cell(ws3, row, 3, "", s)
            _cell(ws3, row, 4, round(day_sum, 2), s,
                  font=Font(bold=True, size=9), fmt='#,##0.00')

        for col, w in zip('ABCD', [14, 25, 25, 15]):
            ws3.column_dimensions[col].width = w

        # ===== ЛИСТ 4: ПО КАТЕГОРИЯМ =====
        ws4 = wb.create_sheet("По категориям")
        ws4.merge_cells('A1:E1')
        ws4['A1'] = f"По категориям за {MONTHS_RU[month]} {year}"
        ws4['A1'].font = s["header"]
        ws4['A1'].alignment = Alignment(horizontal='center')

        row = 3
        for col, h in enumerate(["Категория", "Работа", "Кол-во", "Расценка", "Итого (₽)"], 1):
            _cell(ws4, row, col, h, s, font=s["th_font"], fill=s["th_fill"], center=True)
        row += 1

        cat_data = await conn.fetch("""
            SELECT c.name, pl.name, SUM(wl.quantity), wl.price_per_unit, SUM(wl.total)
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE EXTRACT(YEAR FROM wl.work_date) = $1 AND EXTRACT(MONTH FROM wl.work_date) = $2
            GROUP BY c.name, pl.name, wl.price_per_unit
            ORDER BY c.name, pl.name
        """, year, month)

        cat_grand = 0
        for rec in cat_data:
            cn, pn, qty, price, total = rec[0], rec[1], rec[2], rec[3], rec[4]
            _cell(ws4, row, 1, cn, s)
            _cell(ws4, row, 2, pn, s)
            _cell(ws4, row, 3, qty, s, center=True)
            _cell(ws4, row, 4, round(price, 2), s, fmt='#,##0.00')
            _cell(ws4, row, 5, round(total, 2), s, fmt='#,##0.00')
            cat_grand += total
            row += 1

        for col in range(1, 5):
            _cell(ws4, row, col, "", s, fill=s["total_fill"])
        _cell(ws4, row, 2, "ОБЩИЙ ИТОГО", s, font=s["total_font"], fill=s["total_fill"])
        _cell(ws4, row, 5, round(cat_grand, 2), s, font=s["total_font"],
              fill=s["total_fill"], fmt='#,##0.00 ₽')

        for col, w in zip('ABCDE', [20, 25, 12, 14, 15]):
            ws4.column_dimensions[col].width = w

    finally:
        await conn.close()

    filename = f"report_{year}_{month:02d}.xlsx"
    wb.save(filename)
    return filename


async def generate_worker_report(worker_id, worker_name, year=None, month=None):
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    s = _styles()
    wb = Workbook()
    ws = wb.active
    ws.title = f"Отчёт {worker_name}"

    ws.merge_cells('A1:F1')
    ws['A1'] = f"Отчёт: {worker_name}"
    ws['A1'].font = s["header"]
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:F2')
    ws['A2'] = f"Период: {MONTHS_RU[month]} {year}"
    ws['A2'].alignment = Alignment(horizontal='center')

    row = 4
    for col, h in enumerate(["Дата", "Категория", "Работа", "Кол-во", "Расценка", "Сумма"], 1):
        _cell(ws, row, col, h, s, font=s["th_font"], fill=s["th_fill"], center=True)
    row += 1

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        records = await conn.fetch("""
            SELECT wl.work_date::TEXT, c.name, pl.name, wl.quantity, wl.price_per_unit, wl.total
            FROM work_log wl
            JOIN price_list pl ON wl.work_code = pl.code
            JOIN categories c ON pl.category_code = c.code
            WHERE wl.worker_id = $1
              AND EXTRACT(YEAR FROM wl.work_date) = $2
              AND EXTRACT(MONTH FROM wl.work_date) = $3
            ORDER BY wl.work_date, wl.created_at
        """, worker_id, year, month)
    finally:
        await conn.close()

    grand = 0
    cur_date = ""
    day_total = 0

    for rec in records:
        wd, cn, pn, qty, price, total = rec[0], rec[1], rec[2], rec[3], rec[4], rec[5]
        if wd != cur_date and cur_date != "":
            for c2 in range(1, 5):
                _cell(ws, row, c2, "", s, fill=s["day_fill"])
            _cell(ws, row, 4, f"День {cur_date}:", s,
                  font=Font(bold=True, italic=True, size=9), fill=s["day_fill"])
            _cell(ws, row, 5, "", s, fill=s["day_fill"])
            _cell(ws, row, 6, round(day_total, 2), s,
                  font=Font(bold=True, italic=True, size=9),
                  fill=s["day_fill"], fmt='#,##0.00')
            row += 1
            day_total = 0
        cur_date = wd

        _cell(ws, row, 1, wd, s)
        _cell(ws, row, 2, cn, s)
        _cell(ws, row, 3, pn, s)
        _cell(ws, row, 4, qty, s, center=True)
        _cell(ws, row, 5, round(price, 2), s, fmt='#,##0.00')
        _cell(ws, row, 6, round(total, 2), s, fmt='#,##0.00')
        grand += total
        day_total += total
        row += 1

    if cur_date != "":
        for c2 in range(1, 5):
            _cell(ws, row, c2, "", s, fill=s["day_fill"])
        _cell(ws, row, 4, f"День {cur_date}:", s,
              font=Font(bold=True, italic=True, size=9), fill=s["day_fill"])
        _cell(ws, row, 5, "", s, fill=s["day_fill"])
        _cell(ws, row, 6, round(day_total, 2), s,
              font=Font(bold=True, italic=True, size=9),
              fill=s["day_fill"], fmt='#,##0.00')
        row += 1

    for col in range(1, 6):
        _cell(ws, row, col, "", s, fill=s["total_fill"])
    _cell(ws, row, 3, "ИТОГО:", s, font=s["total_font"], fill=s["total_fill"])
    _cell(ws, row, 6, round(grand, 2), s, font=s["total_font"],
          fill=s["total_fill"], fmt='#,##0.00 ₽')

    for col, w in zip('ABCDEF', [14, 20, 25, 10, 14, 14]):
        ws.column_dimensions[col].width = w

    filename = f"report_{worker_name}_{year}_{month:02d}.xlsx"
    wb.save(filename)
    return filename


async def generate_salary_report(year: int, month: int, workers_data: list) -> str:
    """
    Ведомость выплаты зарплаты.
    workers_data: список dict с ключами name, work_summary, fixed_salary,
                  bonus, penalties, advances, balance
    """
    s = _styles()
    wb = Workbook()
    ws = wb.active
    ws.title = f"Ведомость {MONTHS_RU[month]} {year}"

    # ---- Заголовок ----
    ws.merge_cells('A1:G1')
    ws['A1'] = f"Ведомость зарплаты — {MONTHS_RU[month]} {year}"
    ws['A1'].font = s["header"]
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:G2')
    ws['A2'] = f"Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    ws['A2'].alignment = Alignment(horizontal='center')

    # ---- Шапка таблицы ----
    headers = ["Работник", "Что сделал", "Фикс. ставка", "Премия",
               "Штрафы", "Авансы", "К выдаче"]
    row = 4
    for col, h in enumerate(headers, 1):
        _cell(ws, row, col, h, s, font=s["th_font"], fill=s["th_fill"], center=True)
    row += 1

    # ---- Данные ----
    money_fmt = '#,##0.00 ₽'
    grand_fixed = grand_bonus = grand_penalties = grand_advances = grand_balance = 0

    for w in workers_data:
        _cell(ws, row, 1, w['name'], s)
        # "Что сделал" — многострочный текст
        cell = ws.cell(row=row, column=2, value=w['work_summary'])
        cell.border = s["border"]
        cell.alignment = Alignment(wrap_text=True, vertical='top')

        _cell(ws, row, 3, w['fixed_salary'] or None, s, fmt=money_fmt, center=True)
        _cell(ws, row, 4, w['bonus'] or None, s, fmt=money_fmt, center=True)
        _cell(ws, row, 5, w['penalties'] or None, s, fmt=money_fmt, center=True)
        _cell(ws, row, 6, w['advances'] or None, s, fmt=money_fmt, center=True)

        to_pay = round(w['balance'], 2)
        pay_cell = _cell(ws, row, 7, to_pay, s,
                         font=Font(bold=True),
                         fill=PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid"),
                         fmt=money_fmt, center=True)

        grand_fixed += w['fixed_salary'] or 0
        grand_bonus += w['bonus'] or 0
        grand_penalties += w['penalties'] or 0
        grand_advances += w['advances'] or 0
        grand_balance += w['balance']
        row += 1

    # ---- Итоговая строка ----
    tf = s["total_fill"]
    tf_font = s["total_font"]
    _cell(ws, row, 1, "ИТОГО", s, font=tf_font, fill=tf)
    _cell(ws, row, 2, "", s, fill=tf)
    _cell(ws, row, 3, round(grand_fixed, 2) or None, s, font=tf_font, fill=tf, fmt=money_fmt, center=True)
    _cell(ws, row, 4, round(grand_bonus, 2) or None, s, font=tf_font, fill=tf, fmt=money_fmt, center=True)
    _cell(ws, row, 5, round(grand_penalties, 2) or None, s, font=tf_font, fill=tf, fmt=money_fmt, center=True)
    _cell(ws, row, 6, round(grand_advances, 2) or None, s, font=tf_font, fill=tf, fmt=money_fmt, center=True)
    _cell(ws, row, 7, round(grand_balance, 2), s, font=tf_font, fill=tf, fmt=money_fmt, center=True)

    # ---- Ширина столбцов ----
    for col, w in zip('ABCDEFG', [22, 45, 16, 14, 14, 14, 16]):
        ws.column_dimensions[col].width = w

    filename = f"vedomost_{year}_{month:02d}.xlsx"
    wb.save(filename)
    return filename