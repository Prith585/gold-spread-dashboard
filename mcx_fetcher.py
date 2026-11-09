import os
import json
import sqlite3
import datetime
import pandas as pd
from curl_cffi import requests as c_req
from bs4 import BeautifulSoup

DB_PATH = os.path.join(os.path.dirname(__file__), 'mcx_gold_data.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS gold_futures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT,
            symbol TEXT,
            expiry_date TEXT,
            instrument TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            prev_close REAL,
            volume INTEGER,
            volume_thousands TEXT,
            value_lacs REAL,
            open_interest INTEGER,
            UNIQUE(trade_date, symbol, expiry_date, instrument)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sync_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_mcx_session():
    s = c_req.Session(impersonate='chrome120')
    r = s.get('https://www.mcxindia.com/market-data/bhavcopy', timeout=15)
    soup = BeautifulSoup(r.text, 'lxml')
    sym_el = soup.select_one('#symbol-data')
    symbol_master = []
    if sym_el:
        try:
            symbol_master = json.loads(sym_el.get_text(strip=True))
        except Exception as e:
            print(f"Error parsing symbol master: {e}")
    return s, symbol_master

def fetch_gold_contracts(symbols=['GOLD', 'GOLDM'], months_back=14):
    init_db()
    s, master = get_mcx_session()
    
    headers = {
        'Referer': 'https://www.mcxindia.com/market-data/bhavcopy',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01'
    }
    
    today = datetime.date(2026, 11, 6)
    start_date = today - datetime.timedelta(days=months_back * 31)
    from_date_str = start_date.strftime('%d/%m/%Y')
    to_date_str = today.strftime('%d/%m/%Y')
    
    # Filter contracts
    target_contracts = []
    for item in master:
        if item.get('InstrumentName') == 'FUTCOM' and item.get('Symbol', '').strip() in symbols:
            exp_str = item.get('ExpiryDate', '')
            try:
                exp_dt = datetime.datetime.strptime(exp_str, '%d%b%Y').date()
                # Include expiries that expired after start_date or are future
                if exp_dt >= start_date - datetime.timedelta(days=45) and exp_dt <= today + datetime.timedelta(days=365):
                    target_contracts.append({
                        'symbol': item.get('Symbol', '').strip(),
                        'expiry': exp_str,
                        'expiry_date': exp_dt
                    })
            except Exception:
                continue

    target_contracts.sort(key=lambda x: (x['symbol'], x['expiry_date']))
    print(f"Found {len(target_contracts)} candidate contracts for {symbols} across the past {months_back} months.")
    
    conn = sqlite3.connect(DB_PATH)
    total_saved = 0
    
    for idx, c_info in enumerate(target_contracts, 1):
        sym = c_info['symbol']
        exp = c_info['expiry']
        print(f"[{idx}/{len(target_contracts)}] Fetching {sym} {exp} ({from_date_str} to {to_date_str})...", end=' ', flush=True)
        
        url = 'https://www.mcxindia.com/market-data/bhavcopy/GetCommoditywiseBhavCopy'
        params = {
            'InstrumentName': 'FUTCOM',
            'Symbol': sym,
            'Expiry': exp,
            'fromDate': from_date_str,
            'toDate': to_date_str
        }
        
        try:
            resp = s.get(url, params=params, headers=headers, timeout=15)
            res_json = resp.json()
            data = res_json.get('Data', [])
            if not data:
                print("No rows.")
                continue
            
            cur = conn.cursor()
            inserted = 0
            for row in data:
                # Format date to YYYY-MM-DD
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
                inserted += 1
            
            conn.commit()
            total_saved += inserted
            print(f"Saved {inserted} rows.")
        except Exception as e:
            print(f"Error: {e}")
            
    # Record metadata
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('last_sync', ?)", (datetime.datetime.now().isoformat(),))
    conn.commit()
    conn.close()
    print(f"\nDone! Total {total_saved} records stored in {DB_PATH}.")

if __name__ == '__main__':
    fetch_gold_contracts(['GOLD', 'GOLDM'], months_back=14)
