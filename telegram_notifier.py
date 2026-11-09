import os
import sqlite3
import datetime
import requests
import json
import spread_engine
import mcx_live_fetcher

DB_PATH = os.path.join(os.path.dirname(__file__), 'mcx_gold_data.db')

def get_db():
    return sqlite3.connect(DB_PATH)

def init_telegram_table():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_settings (
            id INTEGER PRIMARY KEY,
            bot_token TEXT,
            chat_id TEXT,
            threshold_pct REAL DEFAULT 1.8,
            is_enabled INTEGER DEFAULT 1,
            last_checked TEXT,
            last_alert_sent TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_alerts_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_time TEXT,
            symbol TEXT,
            pair_label TEXT,
            spread_points REAL,
            spread_pct REAL,
            threshold_pct REAL,
            message_text TEXT,
            status TEXT
        )
    ''')
    # Insert default row if not exists
    c.execute("SELECT COUNT(*) FROM telegram_settings WHERE id = 1")
    if c.fetchone()[0] == 0:
        c.execute('''
            INSERT INTO telegram_settings (id, bot_token, chat_id, threshold_pct, is_enabled)
            VALUES (1, '', '', 1.8, 1)
        ''')
    conn.commit()
    conn.close()

init_telegram_table()

def get_telegram_config():
    init_telegram_table()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT bot_token, chat_id, threshold_pct, is_enabled, last_checked, last_alert_sent FROM telegram_settings WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'bot_token': row[0] or '',
            'chat_id': row[1] or '',
            'threshold_pct': float(row[2] or 1.8),
            'is_enabled': bool(row[3]),
            'last_checked': row[4] or '—',
            'last_alert_sent': row[5] or '—'
        }
    return {
        'bot_token': '',
        'chat_id': '',
        'threshold_pct': 1.8,
        'is_enabled': True,
        'last_checked': '—',
        'last_alert_sent': '—'
    }

def save_telegram_config(bot_token, chat_id, threshold_pct=1.8, is_enabled=True):
    init_telegram_table()
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE telegram_settings 
        SET bot_token = ?, chat_id = ?, threshold_pct = ?, is_enabled = ?
        WHERE id = 1
    ''', (bot_token.strip(), chat_id.strip(), float(threshold_pct), 1 if is_enabled else 0))
    conn.commit()
    conn.close()
    return True

def send_telegram_message(text, bot_token=None, chat_id=None):
    """
    Sends a message to Telegram using bot_token and chat_id.
    """
    cfg = get_telegram_config()
    token = bot_token or cfg.get('bot_token')
    cid = chat_id or cfg.get('chat_id')

    if not token or not cid:
        return False, "Bot token or Chat ID is missing. Please configure your Telegram settings."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': cid,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }

    try:
        r = requests.post(url, json=payload, timeout=12)
        resp_data = r.json()
        if resp_data.get('ok'):
            return True, "Message sent successfully"
        else:
            err = resp_data.get('description', 'Unknown Telegram API error')
            return False, f"Telegram API error: {err}"
    except Exception as e:
        return False, f"Network error sending Telegram message: {str(e)}"

def is_duplicate_alert(symbol, pair_label, spread_pct, cooldown_minutes=45):
    try:
        conn = get_db()
        c = conn.cursor()
        time_limit = (datetime.datetime.now() - datetime.timedelta(minutes=cooldown_minutes)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute('''
            SELECT spread_pct FROM telegram_alerts_log 
            WHERE symbol = ? AND pair_label = ? AND alert_time >= ? AND status = 'SENT'
            ORDER BY id DESC LIMIT 1
        ''', (symbol, pair_label, time_limit))
        row = c.fetchone()
        conn.close()
        if row and row[0] is not None:
            last_pct = row[0]
            if abs(spread_pct - last_pct) < 0.20:
                return True
        return False
    except:
        return False

def parse_expiry_month(exp_str):
    try:
        dt = datetime.datetime.strptime(exp_str.strip(), '%d%b%Y')
        return dt.strftime('%b').upper()
    except:
        return exp_str.strip()

def format_trade_alert(alert):
    """
    Formats the spread alert in the exact template requested from the photo:
    ✅ LIVE EXECUTED
    ADANIENSOL | NSE Fut-Fut

    BUY NOV @1305.70
    SELL DEC @1325.50

    SP 19.80 | ACT 1.39% | AAR 14.09%
    QTY 675
    """
    title = "✅ LIVE EXECUTED" if alert.get('is_live') else "✅ SPREAD ALERT"
    cat = alert.get('category', 'Calendar Spread')
    sym = alert['symbol']

    if cat == 'Calendar Spread':
        header = f"{sym} | MCX Fut-Fut"
        near_tag = alert.get('near_month', 'NEAR')
        next_tag = alert.get('next_month', 'NEXT')
        qty_str = alert.get('qty', '1 Lot')
    else:
        header = f"{sym} | MCX Cross"
        near_tag = alert.get('leg1_tag', f"{alert.get('leg1_symbol')} ({alert.get('near_month')})")
        next_tag = alert.get('leg2_tag', f"{alert.get('leg2_symbol')} ({alert.get('next_month')})")
        qty_str = "Per 10g Basis"

    p1 = alert.get('near_price', 0.0)
    p2 = alert.get('next_price', 0.0)
    sp = alert.get('spread_points', 0.0)
    act = alert.get('spread_pct', 0.0)
    aar = alert.get('aar_pct', 0.0)

    msg = (
        f"{title}\n"
        f"{header}\n\n"
        f"BUY {near_tag} @{p1:,.2f}\n"
        f"SELL {next_tag} @{p2:,.2f}\n\n"
        f"SP {sp:,.2f} | ACT {act:.2f}% | AAR {aar:.2f}%\n"
        f"QTY {qty_str}"
    )
    return msg

def check_and_send_spread_alerts(forced=False):
    """
    Scans active spreads (Live Quotes first, or latest active closing pairs).
    Whenever any spread goes above +1.8% (or user threshold),
    dispatches a Telegram alert formatted in the exact photo style.
    """
    cfg = get_telegram_config()
    if not cfg['is_enabled'] and not forced:
        return {'success': False, 'message': 'Telegram alerts are disabled in settings'}

    token = cfg.get('bot_token')
    chat_id = cfg.get('chat_id')
    if not token or not chat_id:
        return {'success': False, 'message': 'Telegram bot token or chat ID is not set'}

    threshold = cfg.get('threshold_pct', 1.8)
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    qty_map = {
        'GOLD': '1 (1 kg)',
        'GOLDM': '1 (100g)',
        'GOLDPETAL': '1 (1g)',
        'GOLDGUINEA': '1 (8g)'
    }

    triggered_alerts = []

    # 1. Try Live Quotes First (Real-time Intraday Feeds)
    try:
        quotes = mcx_live_fetcher.fetch_live_mcx_quotes()
        if quotes and len(quotes) > 0:
            for sym in ['GOLD', 'GOLDM', 'GOLDPETAL', 'GOLDGUINEA']:
                cal_spreads = mcx_live_fetcher.get_live_calendar_spreads(symbol=sym)
                for c in cal_spreads:
                    # Check if positive spread exceeds threshold
                    if c.get('spread_pct', 0.0) >= threshold:
                        near_m = parse_expiry_month(c['near_expiry'])
                        next_m = parse_expiry_month(c['next_expiry'])
                        dt1 = mcx_live_fetcher.parse_expiry(c['near_expiry'])
                        dt2 = mcx_live_fetcher.parse_expiry(c['next_expiry'])
                        days = max(1, (dt2 - dt1).days)
                        aar = (c['spread_pct'] * 365.0) / days

                        triggered_alerts.append({
                            'category': 'Calendar Spread',
                            'is_live': c.get('is_live', True),
                            'symbol': sym,
                            'pair_label': f"{c['label']} ({sym})",
                            'near_month': near_m,
                            'next_month': next_m,
                            'near_price': c['near_effective'],
                            'next_price': c['next_effective'],
                            'spread_points': c['spread'],
                            'spread_pct': c['spread_pct'],
                            'aar_pct': aar,
                            'qty': qty_map.get(sym, '1 Lot')
                        })

            # Check Live Cross Spreads (Per 10g Basis)
            cross_checks = [
                ('GOLDPETAL', 'GOLDM'),
                ('GOLDGUINEA', 'GOLDM'),
                ('GOLDPETAL', 'GOLDGUINEA')
            ]
            for s1, s2 in cross_checks:
                cr_spreads = mcx_live_fetcher.get_live_cross_spreads(s1, s2, basis='10g')
                for c in cr_spreads:
                    if c.get('spread_pct', 0.0) >= threshold:
                        dt = mcx_live_fetcher.parse_expiry(c['leg1_expiry'])
                        m_str = dt.strftime('%b').upper()
                        # Cross spread annualization (~30 days)
                        aar = c['spread_pct'] * 12.0

                        triggered_alerts.append({
                            'category': 'Cross Spread',
                            'is_live': c.get('is_live', True),
                            'symbol': f"{s1} vs {s2}",
                            'pair_label': f"{s1} vs {s2} ({c['month']})",
                            'near_month': m_str,
                            'next_month': m_str,
                            'leg1_symbol': s1,
                            'leg2_symbol': s2,
                            'leg1_tag': f"{s2} ({m_str})",
                            'leg2_tag': f"{s1} ({m_str})",
                            'near_price': c['leg2_norm'],
                            'next_price': c['leg1_norm'],
                            'spread_points': c['spread'],
                            'spread_pct': c['spread_pct'],
                            'aar_pct': aar,
                            'qty': '10g Basis'
                        })
    except Exception as e:
        print(f"[Live Alert Scanner Notice] {e}")

    # 2. Fallback to Closing Bhavcopy Data if no live alerts were found
    if not triggered_alerts:
        today_date = datetime.date.today()
        for sym in ['GOLDM', 'GOLDPETAL', 'GOLDGUINEA', 'GOLD']:
            pairs = spread_engine.get_consecutive_monthly_pairs(symbol=sym, formula='leg2_minus_leg1')
            for p in pairs:
                # Check only current and upcoming active pairs
                exp_dt = mcx_live_fetcher.parse_expiry(p.get('next_expiry', ''))
                if exp_dt < today_date:
                    continue  # Skip historical already-expired contracts

                sp_pct = p.get('spread_pct', 0.0)
                if sp_pct >= threshold:
                    near_m = parse_expiry_month(p['near_expiry'])
                    next_m = parse_expiry_month(p['next_expiry'])
                    dt1 = mcx_live_fetcher.parse_expiry(p['near_expiry'])
                    dt2 = mcx_live_fetcher.parse_expiry(p['next_expiry'])
                    days = max(1, (dt2 - dt1).days)
                    aar = (sp_pct * 365.0) / days

                    triggered_alerts.append({
                        'category': 'Calendar Spread',
                        'is_live': False,
                        'symbol': sym,
                        'pair_label': f"{p['label']} ({sym})",
                        'near_month': near_m,
                        'next_month': next_m,
                        'near_price': p['near_close'],
                        'next_price': p['next_close'],
                        'spread_points': p['spread'],
                        'spread_pct': sp_pct,
                        'aar_pct': aar,
                        'qty': qty_map.get(sym, '1 Lot')
                    })

    # Update last checked timestamp
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE telegram_settings SET last_checked = ? WHERE id = 1", (now_str,))
    conn.commit()
    conn.close()

    if not triggered_alerts:
        return {
            'success': True,
            'alerts_count': 0,
            'message': f"No active spreads currently exceed +{threshold}% threshold."
        }

    # Dispatch alerts in photo format
    sent_count = 0
    errors = []
    conn = get_db()
    c = conn.cursor()

    for a in triggered_alerts:
        if not forced and is_duplicate_alert(a['symbol'], a['pair_label'], a['spread_pct']):
            continue  # Avoid repeated spam for same spread level within cooldown
        msg_text = format_trade_alert(a)
        ok, res_text = send_telegram_message(msg_text, token, chat_id)
        if ok:
            sent_count += 1
        else:
            errors.append(res_text)

        c.execute('''
            INSERT INTO telegram_alerts_log (alert_time, symbol, pair_label, spread_points, spread_pct, threshold_pct, message_text, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            now_str,
            a['symbol'],
            a['pair_label'],
            a['spread_points'],
            a['spread_pct'],
            threshold,
            msg_text,
            'SENT' if ok else 'FAILED'
        ))

    if sent_count > 0:
        c.execute("UPDATE telegram_settings SET last_alert_sent = ? WHERE id = 1", (now_str,))
    conn.commit()
    conn.close()

    return {
        'success': sent_count > 0,
        'alerts_count': sent_count,
        'message': f"Delivered {sent_count} spread alerts (> {threshold}%) in photo format to Telegram." if sent_count > 0 else (errors[0] if errors else "Failed to send alerts")
    }
