import os
import sqlite3
import datetime
import json
import time
from bs4 import BeautifulSoup
from curl_cffi import requests as c_req
from pypdf import PdfReader
import io
import re

DB_PATH = os.path.join(os.path.dirname(__file__), 'mcx_gold_data.db')

def get_db():
    return sqlite3.connect(DB_PATH)

def get_latest_db_date():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT MAX(trade_date) FROM gold_futures WHERE symbol = 'GOLDM'")
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else '2025-08-01'

def fetch_mcx_session_and_symbols():
    s = c_req.Session(impersonate='chrome120')
    r = s.get('https://www.mcxindia.com/market-data/bhavcopy', timeout=15)
    soup = BeautifulSoup(r.text, 'lxml')
    sym_el = soup.select_one('#symbol-data')
    master = []
    if sym_el:
        try:
            master = json.loads(sym_el.get_text(strip=True))
        except Exception as e:
            print(f"Error parsing symbol master: {e}")
    return s, master

def update_mcx_closing_data(symbols=['GOLDM', 'GOLDPETAL', 'GOLDGUINEA', 'GOLD'], days_back=7):
    """
    Fetches the latest closing bhavcopy prices from MCX for all currently active contracts.
    """
    s, master = fetch_mcx_session_and_symbols()
    if not master:
        return 0, "Failed to connect to MCX master"

    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=days_back)
    from_date_str = start_date.strftime('%d/%m/%Y')
    to_date_str = today.strftime('%d/%m/%Y')

    # Identify currently active / upcoming contracts
    active_contracts = []
    for item in master:
        if item.get('InstrumentName') == 'FUTCOM' and item.get('Symbol', '').strip() in symbols:
            exp_str = item.get('ExpiryDate', '').strip()
            try:
                exp_dt = datetime.datetime.strptime(exp_str, '%d%b%Y').date()
                if exp_dt >= start_date - datetime.timedelta(days=10):
                    active_contracts.append({
                        'symbol': item.get('Symbol', '').strip(),
                        'expiry': exp_str,
                        'exp_dt': exp_dt
                    })
            except Exception:
                continue

    active_contracts.sort(key=lambda x: (x['symbol'], x['exp_dt']))
    print(f"Found {len(active_contracts)} active contracts across {symbols} to check.")

    headers = {
        'Referer': 'https://www.mcxindia.com/market-data/bhavcopy',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01'
    }
    url = 'https://www.mcxindia.com/market-data/bhavcopy/GetCommoditywiseBhavCopy'

    conn = get_db()
    cur = conn.cursor()
    total_saved = 0

    for c_info in active_contracts:
        sym = c_info['symbol']
        exp = c_info['expiry']
        params = {
            'InstrumentName': 'FUTCOM',
            'Symbol': sym,
            'Expiry': exp,
            'fromDate': from_date_str,
            'toDate': to_date_str
        }

        try:
            resp = s.get(url, params=params, headers=headers, timeout=12)
            if resp.status_code != 200:
                continue
            data = resp.json().get('Data', [])
            if not data:
                continue

            for row in data:
                raw_date = row.get('Date', '')
                try:
                    dt_obj = datetime.datetime.strptime(raw_date, '%m/%d/%Y').date()
                    clean_date = dt_obj.strftime('%Y-%m-%d')
                except:
                    clean_date = raw_date

                cur.execute('''
                    INSERT OR REPLACE INTO gold_futures 
                    (trade_date, symbol, expiry_date, instrument, open, high, low, close, prev_close, volume, volume_thousands, value_lacs, open_interest)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    clean_date,
                    row.get('Symbol', '').strip(),
                    row.get('ExpiryDate', '').strip(),
                    row.get('InstrumentName', 'FUTCOM').strip(),
                    float(row.get('Open', 0.0) or 0.0),
                    float(row.get('High', 0.0) or 0.0),
                    float(row.get('Low', 0.0) or 0.0),
                    float(row.get('Close', 0.0) or 0.0),
                    float(row.get('PreviousClose', 0.0) or 0.0),
                    int(row.get('Volume', 0) or 0),
                    str(row.get('VolumeInThousands', '')),
                    float(row.get('Value', 0.0) or 0.0),
                    int(row.get('OpenInterest', 0) or 0)
                ))
                total_saved += 1
            conn.commit()
        except Exception as e:
            print(f"Error fetching {sym} {exp}: {e}")

    conn.close()
    return total_saved, f"Saved {total_saved} daily contract rows"

def update_mcx_inventory_data():
    """
    Fetches the latest MCX deliverable stock position reports (warehouse inventory) for any recent dates.
    """
    from fetch_mcx_inventory import fetch_inventory_for_date

    conn = get_db()
    c = conn.cursor()
    # Find dates in gold_futures that do not have warehouse_inventory entry
    q = """
        SELECT DISTINCT trade_date FROM gold_futures
        WHERE trade_date NOT IN (SELECT trade_date FROM warehouse_inventory WHERE gold_kg IS NOT NULL)
        ORDER BY trade_date DESC LIMIT 10
    """
    missing_dates = [r[0] for r in c.execute(q).fetchall()]
    conn.close()

    if not missing_dates:
        return 0, "Inventory already up-to-date"

    print(f"Checking inventory for {len(missing_dates)} dates: {missing_dates}")
    saved = 0
    conn = get_db()
    c = conn.cursor()

    for d in missing_dates:
        d_str, data = fetch_inventory_for_date(d)
        if data:
            c.execute('''
                INSERT OR REPLACE INTO warehouse_inventory (trade_date, gold_kg, gold_mini_gm, gold_petal_gm, gold_guinea_gm, pdf_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                d,
                data.get('gold_kg'),
                data.get('gold_mini_gm'),
                data.get('gold_petal_gm'),
                data.get('gold_guinea_gm'),
                data.get('pdf_url')
            ))
            saved += 1
    conn.commit()

    # Forward fill if any missing
    c.execute('''
        SELECT gold_kg, gold_mini_gm, gold_petal_gm, gold_guinea_gm, pdf_url
        FROM warehouse_inventory
        ORDER BY trade_date DESC LIMIT 1
    ''')
    last_known = c.fetchone()
    if last_known:
        for d in missing_dates:
            c.execute("SELECT gold_kg FROM warehouse_inventory WHERE trade_date = ?", (d,))
            if not c.fetchone():
                c.execute('''
                    INSERT OR REPLACE INTO warehouse_inventory (trade_date, gold_kg, gold_mini_gm, gold_petal_gm, gold_guinea_gm, pdf_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (d, last_known[0], last_known[1], last_known[2], last_known[3], last_known[4]))
    conn.commit()
    conn.close()
    return saved, f"Updated inventory for {saved} dates"

def run_auto_daily_update():
    """
    Main entrypoint called by background scheduler and manual trigger.
    """
    t0 = time.time()
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[AUTO-UPDATE] Starting daily MCX closing update check at {now_str}...")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS auto_update_log (id INTEGER PRIMARY KEY AUTOINCREMENT, run_time TEXT, status TEXT, records_added INTEGER, message TEXT)")
    conn.commit()
    conn.close()

    try:
        # 1. Update closing Bhavcopy data
        bhav_count, bhav_msg = update_mcx_closing_data(symbols=['GOLDM', 'GOLDPETAL', 'GOLDGUINEA', 'GOLD'], days_back=5)
        
        # 2. Update deliverable stock inventory
        inv_count, inv_msg = update_mcx_inventory_data()

        # 3. Check and send Telegram alerts for spreads >= threshold (default 1.8%)
        tg_info = ""
        try:
            import telegram_notifier
            tg_res = telegram_notifier.check_and_send_spread_alerts(forced=False)
            if tg_res.get('alerts_count', 0) > 0:
                tg_info = f" | Telegram alert sent for {tg_res['alerts_count']} spreads >= {tg_res.get('threshold', 1.8)}%"
                print(f"[TELEGRAM ALERT] {tg_info}")
        except Exception as tg_err:
            print(f"[TELEGRAM ERROR] {tg_err}")

        latest_d = get_latest_db_date()
        duration = round(time.time() - t0, 1)
        res_msg = f"Completed in {duration}s. Bhavcopy rows: {bhav_count}. Inventory rows: {inv_count}. Latest DB Date: {latest_d}{tg_info}"
        print(f"[AUTO-UPDATE] {res_msg}")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO auto_update_log (run_time, status, records_added, message) VALUES (?, 'SUCCESS', ?, ?)", (now_str, bhav_count + inv_count, res_msg))
        cur.execute("INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('last_auto_check', ?)", (now_str,))
        cur.execute("INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('latest_trade_date', ?)", (latest_d,))
        conn.commit()
        conn.close()

        return {
            'success': True,
            'run_time': now_str,
            'duration_sec': duration,
            'bhavcopy_rows': bhav_count,
            'inventory_rows': inv_count,
            'latest_db_date': latest_d,
            'message': res_msg
        }

    except Exception as e:
        err_msg = str(e)
        print(f"[AUTO-UPDATE ERROR] {err_msg}")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO auto_update_log (run_time, status, records_added, message) VALUES (?, 'ERROR', 0, ?)", (now_str, err_msg))
        conn.commit()
        conn.close()
        return {'success': False, 'error': err_msg}

if __name__ == '__main__':
    res = run_auto_daily_update()
    print(res)
