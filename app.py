import os
import io
import csv
import json
import sqlite3
import datetime
import threading
import time
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify, Response, send_file

import spread_engine
import mcx_fetcher
import daily_updater
import telegram_notifier
import mcx_live_fetcher

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mcx-gold-spread-2026'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.context_processor
def inject_cache_id():
    return {'cache_id': int(time.time())}

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

sync_status = {
    'is_syncing': False,
    'progress': '',
    'error': None,
    'last_sync': None
}

def safe_float(val, default=0.0):
    if val is None or val == '':
        return default
    try:
        return float(val)
    except:
        return default

def safe_int(val, default=0):
    if val is None or val == '':
        return default
    try:
        return int(val)
    except:
        return default

@app.route('/')
def index():
    return render_template('index.html', cache_id=int(time.time()))

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'time': datetime.datetime.now().isoformat()}), 200

@app.route('/api/contracts', methods=['GET'])
def get_contracts():
    try:
        df = spread_engine.get_available_contracts()
        records = df.to_dict(orient='records')
        
        grouped = {}
        for r in records:
            sym = r['symbol']
            if sym not in grouped:
                grouped[sym] = []
            grouped[sym].append({
                'expiry': r['expiry_date'],
                'start_date': r['start_date'],
                'end_date': r['end_date'],
                'trading_days': r['trading_days'],
                'avg_volume': r['avg_volume'],
                'max_oi': r['max_oi']
            })
            
        conn = sqlite3.connect(mcx_fetcher.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM sync_meta WHERE key = 'last_sync'")
        row = c.fetchone()
        last_sync = row[0] if row else "Never"
        
        c.execute("SELECT COUNT(*) FROM gold_futures")
        total_rows = c.fetchone()[0]
        conn.close()

        return jsonify({
            'success': True,
            'symbols': list(grouped.keys()),
            'contracts': grouped,
            'last_sync': last_sync,
            'total_rows': total_rows
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/monthly_pairs', methods=['GET', 'POST'])
def get_monthly_pairs():
    try:
        if request.method == 'POST':
            req = request.get_json() or {}
            symbol = req.get('symbol') or 'GOLDM'
            formula = req.get('formula') or 'leg2_minus_leg1'
        else:
            symbol = request.args.get('symbol') or 'GOLDM'
            formula = request.args.get('formula') or 'leg2_minus_leg1'
            
        pairs = spread_engine.get_consecutive_monthly_pairs(symbol=symbol, formula=formula)
        try:
            live_quotes = { (q['symbol'], q['expiry']): q for q in mcx_live_fetcher.fetch_live_mcx_quotes() }
            for p in pairs:
                q1 = live_quotes.get((symbol, p['near_expiry']))
                q2 = live_quotes.get((symbol, p['next_expiry']))
                if q1 and q2 and (q1['ltp'] > 0 or q2['ltp'] > 0):
                    p1 = q1['effective_price']
                    p2 = q2['effective_price']
                    if formula == 'leg2_minus_leg1':
                        sp = p2 - p1
                    else:
                        sp = p1 - p2
                    sp_pct = (sp / p1) * 100.0 if p1 > 0 else 0.0
                    p['is_live'] = True
                    p['live_near_ltp'] = q1['ltp'] or q1['effective_price']
                    p['live_next_ltp'] = q2['ltp'] or q2['effective_price']
                    p['live_spread'] = round(sp, 2)
                    p['live_spread_pct'] = round(sp_pct, 3)
                    p['live_change'] = round(sp - p['spread'], 2)
        except Exception as e:
            print(f"[Live pairs enrich notice] {e}")

        return jsonify({
            'success': True,
            'symbol': symbol,
            'formula': formula,
            'pairs': pairs
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cross_commodity_monthly', methods=['GET', 'POST'])
def get_cross_commodity_monthly():
    try:
        if request.method == 'POST':
            req = request.get_json() or {}
            sym1 = req.get('leg1_symbol') or 'GOLDM'
            sym2 = req.get('leg2_symbol') or 'GOLDPETAL'
            basis = req.get('basis') or '10g'
            formula = req.get('formula') or 'leg1_minus_leg2'
        else:
            sym1 = request.args.get('leg1_symbol') or 'GOLDM'
            sym2 = request.args.get('leg2_symbol') or 'GOLDPETAL'
            basis = request.args.get('basis') or '10g'
            formula = request.args.get('formula') or 'leg1_minus_leg2'
            
        summary = spread_engine.get_cross_commodity_monthly_summary(
            symbol1=sym1, symbol2=sym2, basis=basis, spread_formula=formula
        )
        try:
            live_quotes = { (q['symbol'], q['expiry']): q for q in mcx_live_fetcher.fetch_live_mcx_quotes() }
            for m in summary:
                q1 = live_quotes.get((sym1, m['leg1_expiry']))
                q2 = live_quotes.get((sym2, m['leg2_expiry']))
                if q1 and q2 and (q1['ltp'] > 0 or q2['ltp'] > 0):
                    p1 = mcx_live_fetcher.normalize_live_price(sym1, q1['effective_price'], basis)
                    p2 = mcx_live_fetcher.normalize_live_price(sym2, q2['effective_price'], basis)
                    if formula == 'leg1_minus_leg2':
                        sp = p1 - p2
                        sp_pct = (sp / p2) * 100.0 if p2 > 0 else 0.0
                    else:
                        sp = p2 - p1
                        sp_pct = (sp / p1) * 100.0 if p1 > 0 else 0.0
                    m['is_live'] = True
                    m['live_p1'] = round(p1, 2)
                    m['live_p2'] = round(p2, 2)
                    m['live_spread'] = round(sp, 2)
                    m['live_spread_pct'] = round(sp_pct, 3)
        except Exception as e:
            print(f"[Live cross enrich notice] {e}")

        return jsonify({
            'success': True,
            'symbol1': sym1,
            'symbol2': sym2,
            'basis': basis,
            'formula': formula,
            'months': summary
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/live_spreads', methods=['GET', 'POST'])
def get_live_spreads():
    try:
        if request.method == 'POST':
            req = request.get_json() or {}
            mode = req.get('mode', 'calendar')
            symbol = req.get('symbol', 'GOLDM')
            formula = req.get('formula', 'leg2_minus_leg1')
            sym1 = req.get('leg1_symbol', 'GOLDM')
            sym2 = req.get('leg2_symbol', 'GOLDPETAL')
            basis = req.get('basis', '10g')
        else:
            mode = request.args.get('mode', 'calendar')
            symbol = request.args.get('symbol', 'GOLDM')
            formula = request.args.get('formula', 'leg2_minus_leg1')
            sym1 = request.args.get('leg1_symbol', 'GOLDM')
            sym2 = request.args.get('leg2_symbol', 'GOLDPETAL')
            basis = request.args.get('basis', '10g')

        is_open = mcx_live_fetcher.is_market_open()
        now_str = datetime.datetime.now().strftime('%H:%M:%S IST')

        if mode == 'cross':
            spreads = mcx_live_fetcher.get_live_cross_spreads(
                sym1=sym1, sym2=sym2, basis=basis, formula=formula
            )
        else:
            spreads = mcx_live_fetcher.get_live_calendar_spreads(
                symbol=symbol, formula=formula
            )

        quotes = mcx_live_fetcher.fetch_live_mcx_quotes()
        matrix = mcx_live_fetcher.get_live_cross_matrix(basis=basis)
        all_cal = mcx_live_fetcher.get_live_all_calendar_spreads(limit_per_sym=2, formula=formula)

        return jsonify({
            'success': True,
            'is_market_open': is_open,
            'market_status': 'OPEN' if is_open else 'CLOSED',
            'timestamp': now_str,
            'mode': mode,
            'symbol': symbol,
            'formula': formula,
            'basis': basis,
            'spreads': spreads,
            'front2_spreads': spreads[:2],
            'cross_matrix': matrix,
            'all_calendar': all_cal,
            'quotes_count': len(quotes)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/spread_data', methods=['POST'])
def get_spread_data():
    try:
        req = request.get_json() or {}
        mode = req.get('mode', 'rolling') # 'rolling', 'pair', or 'cross'
        symbol = req.get('symbol') or 'GOLDM'
        formula = req.get('formula') or 'leg2_minus_leg1'
        
        if mode == 'cross':
            sym1 = req.get('leg1_symbol') or 'GOLDM'
            sym2 = req.get('leg2_symbol') or 'GOLDPETAL'
            basis = req.get('basis') or '10g'
            formula = req.get('formula') or 'leg1_minus_leg2'
            df, meta = spread_engine.build_cross_commodity_spread(
                symbol1=sym1, symbol2=sym2, basis=basis, spread_formula=formula
            )
        elif mode == 'rolling':
            roll_days = safe_int(req.get('roll_days'), 5)
            df, meta = spread_engine.build_rolling_calendar_spread(
                symbol=symbol,
                roll_days_before_expiry=roll_days,
                spread_formula=formula
            )
        else:
            sym1 = req.get('leg1_symbol') or symbol
            exp1 = req.get('leg1_expiry')
            sym2 = req.get('leg2_symbol') or symbol
            exp2 = req.get('leg2_expiry')
            
            if not exp1 or not exp2:
                return jsonify({'success': False, 'error': 'Both Active Month and Next Month contracts must be selected'}), 400
                
            df, meta = spread_engine.build_pair_spread(
                symbol1=sym1, expiry1=exp1,
                symbol2=sym2, expiry2=exp2,
                spread_formula=formula
            )
            
        if df.empty:
            return jsonify({'success': False, 'error': 'No common trading dates found for the selected contracts'}), 404
            
        dates = [d.strftime('%Y-%m-%d') for d in df.index]
        
        def clean_series(s):
            return [None if (pd.isna(x) or np.isinf(x)) else round(float(x), 2) for x in s]

        # Table rows in numbers
        table_rows = []
        for d, row in df.iterrows():
            leg1_exp = str(row.get('expiry_date_leg1', row.get('leg1_expiry', '')))
            leg2_exp = str(row.get('expiry_date_leg2', row.get('leg2_expiry', '')))
            c1_disp = round(float(row.get('norm_price_leg1', row.get('close_leg1', 0.0))), 2)
            c2_disp = round(float(row.get('norm_price_leg2', row.get('close_leg2', 0.0))), 2)
            c1_raw = round(float(row.get('close_leg1', 0.0)), 2)
            c2_raw = round(float(row.get('close_leg2', 0.0)), 2)

            table_rows.append({
                'date': d.strftime('%Y-%m-%d'),
                'pair_label': str(row.get('pair_label', f"{leg1_exp} - {leg2_exp}")),
                'leg1_symbol': str(row.get('symbol_leg1', row.get('leg1_symbol', symbol))),
                'leg1_expiry': leg1_exp,
                'close_leg1': c1_disp,
                'close_leg1_raw': c1_raw,
                'leg2_symbol': str(row.get('symbol_leg2', row.get('leg2_symbol', symbol))),
                'leg2_expiry': leg2_exp,
                'close_leg2': c2_disp,
                'close_leg2_raw': c2_raw,
                'spread': round(float(row['spread_close']), 2),
                'spread_pct': round(float(row['spread_pct']), 3),
                'annualized_pct': round(float(row.get('annualized_basis_pct', 0.0)), 2),
                'spread_change': round(float(row.get('spread_change', 0.0)), 2),
                'spread_pct_change': round(float(row.get('spread_pct_change', 0.0)), 3),
                'inventory': str(row.get('inventory_display', '—')),
                'inventory_qty': round(float(row.get('inventory_qty', 0.0)), 2)
            })

        close1_series = df['norm_price_leg1'] if 'norm_price_leg1' in df.columns else df['close_leg1']
        close2_series = df['norm_price_leg2'] if 'norm_price_leg2' in df.columns else df['close_leg2']

        response_payload = {
            'success': True,
            'meta': meta,
            'dates': dates,
            'close_leg1': clean_series(close1_series),
            'close_leg2': clean_series(close2_series),
            'leg1_expiry': [str(x) for x in (df['expiry_date_leg1'] if 'expiry_date_leg1' in df.columns else df['leg1_expiry'])],
            'leg2_expiry': [str(x) for x in (df['expiry_date_leg2'] if 'expiry_date_leg2' in df.columns else df['leg2_expiry'])],
            'spread': clean_series(df['spread_close']),
            'spread_pct': clean_series(df['spread_pct']),
            'annualized_pct': clean_series(df.get('annualized_basis_pct', pd.Series([0]*len(df)))),
            'inventory_qty': clean_series(df.get('inventory_qty', pd.Series([0.0]*len(df)))),
            'inventory_display': [str(x) for x in df.get('inventory_display', pd.Series(['—']*len(df)))],
            'inventory_unit': str(df['inventory_unit'].iloc[-1]) if ('inventory_unit' in df and not df.empty) else 'KG',
            'table_rows': table_rows
        }

        # Append today's LIVE point to chart & table if active trading exists
        today_date_str = datetime.date.today().strftime('%Y-%m-%d')
        if today_date_str not in dates and not df.empty:
            try:
                live_quotes = { (q['symbol'], q['expiry']): q for q in mcx_live_fetcher.fetch_live_mcx_quotes() }
                last_row = df.iloc[-1]
                last_exp1 = str(last_row.get('expiry_date_leg1', last_row.get('leg1_expiry', '')))
                last_exp2 = str(last_row.get('expiry_date_leg2', last_row.get('leg2_expiry', '')))
                last_sym1 = str(last_row.get('symbol_leg1', last_row.get('leg1_symbol', symbol if mode != 'cross' else sym1)))
                last_sym2 = str(last_row.get('symbol_leg2', last_row.get('leg2_symbol', symbol if mode != 'cross' else sym2)))
                
                q1 = live_quotes.get((last_sym1, last_exp1))
                q2 = live_quotes.get((last_sym2, last_exp2))
                
                if q1 and q2 and (q1['ltp'] > 0 or q2['ltp'] > 0):
                    raw_p1 = q1['effective_price']
                    raw_p2 = q2['effective_price']
                    if mode == 'cross':
                        norm_p1 = mcx_live_fetcher.normalize_live_price(last_sym1, raw_p1, basis)
                        norm_p2 = mcx_live_fetcher.normalize_live_price(last_sym2, raw_p2, basis)
                        if formula == 'leg1_minus_leg2':
                            sp = norm_p1 - norm_p2
                            sp_pct = (sp / norm_p2) * 100.0 if norm_p2 > 0 else 0.0
                        else:
                            sp = norm_p2 - norm_p1
                            sp_pct = (sp / norm_p1) * 100.0 if norm_p1 > 0 else 0.0
                    else:
                        norm_p1 = raw_p1
                        norm_p2 = raw_p2
                        if formula == 'leg2_minus_leg1':
                            sp = raw_p2 - raw_p1
                        else:
                            sp = raw_p1 - raw_p2
                        sp_pct = (sp / raw_p1) * 100.0 if raw_p1 > 0 else 0.0
                    
                    prev_sp = float(last_row.get('spread_close', sp))
                    sp_change = sp - prev_sp
                    
                    response_payload['dates'].append(f"{today_date_str} (Live)")
                    response_payload['close_leg1'].append(round(norm_p1, 2))
                    response_payload['close_leg2'].append(round(norm_p2, 2))
                    response_payload['leg1_expiry'].append(last_exp1)
                    response_payload['leg2_expiry'].append(last_exp2)
                    response_payload['spread'].append(round(sp, 2))
                    response_payload['spread_pct'].append(round(sp_pct, 3))
                    response_payload['inventory_qty'].append(round(float(last_row.get('inventory_qty', 0.0)), 2))
                    response_payload['inventory_display'].append(str(last_row.get('inventory_display', '—')))
                    
                    live_tbl_row = {
                        'date': f"{today_date_str} (LIVE)",
                        'pair_label': str(last_row.get('pair_label', f"{last_exp1} - {last_exp2}")),
                        'leg1_symbol': last_sym1,
                        'leg1_expiry': last_exp1,
                        'close_leg1': round(norm_p1, 2),
                        'close_leg1_raw': round(raw_p1, 2),
                        'leg2_symbol': last_sym2,
                        'leg2_expiry': last_exp2,
                        'close_leg2': round(norm_p2, 2),
                        'close_leg2_raw': round(raw_p2, 2),
                        'spread': round(sp, 2),
                        'spread_pct': round(sp_pct, 3),
                        'annualized_pct': 0.0,
                        'spread_change': round(sp_change, 2),
                        'spread_pct_change': round(sp_pct - float(last_row.get('spread_pct', 0.0)), 3),
                        'inventory': str(last_row.get('inventory_display', '—')),
                        'inventory_qty': round(float(last_row.get('inventory_qty', 0.0)), 2),
                        'is_live': True
                    }
                    table_rows.append(live_tbl_row)
            except Exception as e:
                print(f"[Spread data live append notice] {e}")

        return jsonify(response_payload)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export_spread_csv', methods=['POST'])
def export_spread_csv():
    try:
        rows = request.get_json().get('rows', [])
        if not rows:
            return Response("No spread data to export", mimetype="text/plain")

        output = io.StringIO()
        fieldnames = [
            'date', 'leg1_expiry', 'close_leg1', 'leg2_expiry', 'close_leg2',
            'spread', 'spread_pct', 'inventory', 'annualized_pct', 'spread_change', 'spread_pct_change'
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, '') for k in fieldnames})

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=mcx_gold_future_spread_data.csv"}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

import daily_updater
import telegram_notifier

@app.route('/api/telegram_settings', methods=['GET', 'POST'])
def handle_telegram_settings():
    if request.method == 'POST':
        req = request.get_json() or {}
        bot_token = req.get('bot_token', '')
        chat_id = req.get('chat_id', '')
        threshold_pct = safe_float(req.get('threshold_pct', 1.8), 1.8)
        is_enabled = bool(req.get('is_enabled', True))
        
        telegram_notifier.save_telegram_config(
            bot_token=bot_token,
            chat_id=chat_id,
            threshold_pct=threshold_pct,
            is_enabled=is_enabled
        )
        return jsonify({'success': True, 'message': 'Telegram alert settings saved successfully!'})
    else:
        cfg = telegram_notifier.get_telegram_config()
        token = cfg.get('bot_token', '')
        masked_token = (token[:6] + '...' + token[-4:]) if len(token) > 10 else token
        return jsonify({
            'success': True,
            'bot_token': token,
            'masked_token': masked_token,
            'chat_id': cfg.get('chat_id', ''),
            'threshold_pct': cfg.get('threshold_pct', 1.8),
            'is_enabled': cfg.get('is_enabled', True),
            'last_checked': cfg.get('last_checked', '—'),
            'last_alert_sent': cfg.get('last_alert_sent', '—')
        })

@app.route('/api/telegram_test', methods=['POST'])
def test_telegram_message():
    req = request.get_json() or {}
    token = req.get('bot_token')
    chat_id = req.get('chat_id')
    
    test_msg = (
        "🤖 <b>MCX Gold Spread Alert System — Test Message</b>\n\n"
        "✅ Your Telegram bot is connected successfully!\n"
        "🎯 <b>Active Alert Threshold:</b> <code>1.8% a month</code>\n"
        "📡 <i>You will receive automatic alerts whenever any gold future spread exceeds 1.8% at market close.</i>"
    )
    
    ok, msg = telegram_notifier.send_telegram_message(test_msg, bot_token=token, chat_id=chat_id)
    return jsonify({'success': ok, 'message': msg})

@app.route('/api/telegram_check_alerts', methods=['POST'])
def trigger_telegram_check_alerts():
    res = telegram_notifier.check_and_send_spread_alerts(forced=True)
    return jsonify(res)

auto_update_state = {
    'enabled': True,
    'is_updating': False,
    'last_run_time': None,
    'latest_db_date': None,
    'last_message': None,
    'next_scheduled_run': 'Daily at 23:45 IST (Market Close)'
}

def start_auto_update_scheduler():
    def scheduler_loop():
        time.sleep(5)
        while True:
            try:
                now = datetime.datetime.now()
                latest_d = daily_updater.get_latest_db_date()
                auto_update_state['latest_db_date'] = latest_d
                
                should_run = False
                hour = now.hour
                minute = now.minute
                
                # MCX market close window: 23:40 - 23:59 or 00:00 - 01:30 IST
                is_close_window = (hour == 23 and minute >= 40) or (hour == 0) or (hour == 1 and minute <= 30)
                
                last_run = auto_update_state.get('last_run_time')
                if not last_run:
                    should_run = True
                elif is_close_window:
                    last_dt = datetime.datetime.strptime(last_run, '%Y-%m-%d %H:%M:%S')
                    if (now - last_dt).total_seconds() > 3600:
                        should_run = True
                else:
                    last_dt = datetime.datetime.strptime(last_run, '%Y-%m-%d %H:%M:%S')
                    if (now - last_dt).total_seconds() > 14400:
                        should_run = True

                if should_run and not auto_update_state['is_updating']:
                    auto_update_state['is_updating'] = True
                    res = daily_updater.run_auto_daily_update()
                    auto_update_state['last_run_time'] = res.get('run_time')
                    auto_update_state['latest_db_date'] = res.get('latest_db_date')
                    auto_update_state['last_message'] = res.get('message')
                    auto_update_state['is_updating'] = False

                # Real-time intraday live spread alert check during market hours (09:00 - 23:30 IST)
                try:
                    if mcx_live_fetcher.is_market_open():
                        telegram_notifier.check_and_send_spread_alerts(forced=False)
                except Exception as tg_e:
                    print(f"[Intraday Alert Check Notice] {tg_e}")

            except Exception as e:
                print(f"[SCHEDULER ERROR] {e}")
                auto_update_state['is_updating'] = False
            
            time.sleep(300)

    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

@app.route('/api/auto_update_status', methods=['GET'])
def get_auto_update_status():
    global auto_update_state
    if not auto_update_state['latest_db_date']:
        auto_update_state['latest_db_date'] = daily_updater.get_latest_db_date()
    return jsonify({
        'success': True,
        **auto_update_state
    })

@app.route('/api/trigger_auto_update', methods=['POST'])
def trigger_auto_update_now():
    global auto_update_state
    if auto_update_state['is_updating']:
        return jsonify({'success': False, 'message': 'Auto-update is currently in progress'}), 400

    def worker():
        global auto_update_state
        auto_update_state['is_updating'] = True
        try:
            res = daily_updater.run_auto_daily_update()
            auto_update_state['last_run_time'] = res.get('run_time')
            auto_update_state['latest_db_date'] = res.get('latest_db_date')
            auto_update_state['last_message'] = res.get('message')
        finally:
            auto_update_state['is_updating'] = False

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Daily MCX closing update triggered in background'})

@app.route('/api/sync_data', methods=['POST'])
def trigger_sync():
    global sync_status
    if sync_status['is_syncing']:
        return jsonify({'success': False, 'message': 'Sync already in progress'}), 400

    def sync_worker():
        global sync_status
        sync_status['is_syncing'] = True
        sync_status['progress'] = 'Connecting to MCX India...'
        sync_status['error'] = None
        try:
            mcx_fetcher.fetch_gold_contracts(['GOLD', 'GOLDM'], months_back=14)
            sync_status['progress'] = 'Sync completed successfully!'
            sync_status['last_sync'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            sync_status['error'] = str(e)
            sync_status['progress'] = f'Sync failed: {e}'
        finally:
            sync_status['is_syncing'] = False

    t = threading.Thread(target=sync_worker, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'MCX Data Sync started in background'})

@app.route('/api/sync_status', methods=['GET'])
def get_sync_status():
    global sync_status
    return jsonify(sync_status)

@app.route('/api/download_backup', methods=['GET'])
def download_backup():
    try:
        backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
        zips = []
        if os.path.exists(backup_dir):
            zips = [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith('.zip')]
        if not zips:
            doc_dir = os.path.expanduser('~/Documents')
            if os.path.exists(doc_dir):
                zips = [os.path.join(doc_dir, f) for f in os.listdir(doc_dir) if f.startswith('MCX_Spread_Full_Backup') and f.endswith('.zip')]
        
        if zips:
            latest_zip = max(zips, key=os.path.getmtime)
            return send_file(latest_zip, as_attachment=True, download_name='MCX_Spread_Full_Backup.zip')
        return jsonify({'success': False, 'message': 'No backup archive found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Start background auto-update & live alert scheduler on launch (both local & cloud Gunicorn)
start_auto_update_scheduler()

if __name__ == '__main__':
    print("Starting MCX Gold Spread Dashboard on http://0.0.0.0:5000 (Auto-Update Scheduler Active)")
    app.run(host='0.0.0.0', port=5000, debug=False)
