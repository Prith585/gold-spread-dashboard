import os
import time
import json
import datetime
from curl_cffi import requests as c_req

_cached_session = None
_last_session_time = 0
_cache_live_data = None
_cache_live_time = 0

def get_live_session():
    global _cached_session, _last_session_time
    now = time.time()
    # Refresh session every 10 minutes
    if _cached_session is None or (now - _last_session_time) > 600:
        s = c_req.Session(impersonate='chrome120')
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.mcxindia.com/market-data/market-watch',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01'
        })
        try:
            s.get('https://www.mcxindia.com/market-data/market-watch', timeout=12)
        except Exception as e:
            print(f"[MCX Live] Session init notice: {e}")
        _cached_session = s
        _last_session_time = now
    return _cached_session

def is_market_open():
    """
    MCX Trading Hours:
    Monday to Friday: 09:00 to 23:30 (or 23:55 depending on US daylight saving)
    Saturday/Sunday: Closed
    """
    now = datetime.datetime.now()
    if now.weekday() >= 5: # Saturday or Sunday
        return False
    hour = now.hour
    minute = now.minute
    total_mins = hour * 60 + minute
    # 09:00 is 540, 23:30 is 1410
    return 540 <= total_mins <= 1410

def fetch_live_mcx_quotes():
    """
    Fetches raw live market watch quotes for GOLD, GOLDM, GOLDPETAL, GOLDGUINEA.
    Caches results for 5 seconds to prevent overwhelming MCX.
    """
    global _cache_live_data, _cache_live_time
    now = time.time()
    if _cache_live_data and (now - _cache_live_time) < 5:
        return _cache_live_data

    url = 'https://www.mcxindia.com/market-data/market-watch/GetMarketWatch?culture=en'
    s = get_live_session()
    
    try:
        r = s.get(url, timeout=8)
        if r.status_code != 200:
            return _cache_live_data or []
        res = r.json()
        items = res.get('data', {}).get('Data', [])
        
        target_symbols = {'GOLD', 'GOLDM', 'GOLDPETAL', 'GOLDGUINEA'}
        futcoms = []
        for it in items:
            if it.get('InstrumentName') == 'FUTCOM' and it.get('Symbol') in target_symbols:
                ltp = float(it.get('LTP') or 0.0)
                prev_close = float(it.get('PreviousClose') or 0.0)
                # If LTP is 0 (untraded today yet), fall back to PreviousClose
                eff_price = ltp if ltp > 0 else prev_close
                
                futcoms.append({
                    'symbol': it.get('Symbol'),
                    'product_code': it.get('ProductCode'),
                    'expiry': it.get('ExpiryDate'),
                    'ltp': ltp,
                    'prev_close': prev_close,
                    'effective_price': eff_price,
                    'open': float(it.get('Open') or 0.0),
                    'high': float(it.get('High') or 0.0),
                    'low': float(it.get('Low') or 0.0),
                    'volume': int(it.get('Volume') or 0),
                    'open_interest': int(it.get('OpenInterest') or 0),
                    'unit': it.get('Unit', '')
                })
        
        _cache_live_data = futcoms
        _cache_live_time = now
        return futcoms
    except Exception as e:
        print(f"[MCX Live] Error fetching quotes: {e}")
        return _cache_live_data or []

def parse_expiry(exp_str):
    try:
        return datetime.datetime.strptime(exp_str.strip(), '%d%b%Y').date()
    except:
        return datetime.date.max

def get_live_calendar_spreads(symbol='GOLDM', formula='leg2_minus_leg1'):
    """
    Computes real-time calendar spreads for consecutive expiries of the given symbol.
    """
    all_quotes = fetch_live_mcx_quotes()
    sym_quotes = [q for q in all_quotes if q['symbol'] == symbol]
    sym_quotes.sort(key=lambda x: parse_expiry(x['expiry']))
    
    spreads = []
    for i in range(len(sym_quotes) - 1):
        near = sym_quotes[i]
        next_m = sym_quotes[i + 1]
        
        near_price = near['effective_price']
        next_price = next_m['effective_price']
        
        if near_price <= 0:
            continue
            
        if formula == 'leg2_minus_leg1':
            spread = next_price - near_price
        else:
            spread = near_price - next_price
            
        spread_pct = (spread / near_price) * 100.0
        
        # Previous close spread & daily change
        near_prev = near['prev_close']
        next_prev = next_m['prev_close']
        if near_prev > 0 and next_prev > 0:
            if formula == 'leg2_minus_leg1':
                prev_spread = next_prev - near_prev
            else:
                prev_spread = near_prev - next_prev
            spread_change = spread - prev_spread
        else:
            spread_change = 0.0

        near_dt = parse_expiry(near['expiry'])
        next_dt = parse_expiry(next_m['expiry'])
        label = f"{near_dt.strftime('%b %Y')} - {next_dt.strftime('%b %Y')}"
        
        spreads.append({
            'label': label,
            'symbol': symbol,
            'near_expiry': near['expiry'],
            'near_ltp': near['ltp'],
            'near_effective': near_price,
            'near_volume': near['volume'],
            'next_expiry': next_m['expiry'],
            'next_ltp': next_m['ltp'],
            'next_effective': next_price,
            'next_volume': next_m['volume'],
            'spread': round(spread, 2),
            'spread_pct': round(spread_pct, 3),
            'spread_change': round(spread_change, 2),
            'is_live': near['ltp'] > 0 and next_m['ltp'] > 0
        })
    return spreads

def normalize_live_price(symbol, price, basis='10g'):
    if price is None or price <= 0:
        return 0.0
    sym = symbol.upper()
    if basis == '10g':
        if sym in ['GOLDM', 'GOLD']:
            return price
        elif sym == 'GOLDPETAL':
            return price * 10.0 # 1g * 10
        elif sym == 'GOLDGUINEA':
            return (price / 8.0) * 10.0 # 8g to 10g
    elif basis == '1g':
        if sym in ['GOLDM', 'GOLD']:
            return price / 10.0
        elif sym == 'GOLDPETAL':
            return price
        elif sym == 'GOLDGUINEA':
            return price / 8.0
    return price

def get_live_cross_spreads(sym1='GOLDM', sym2='GOLDPETAL', basis='10g', formula='leg1_minus_leg2'):
    """
    Computes real-time cross-contract spreads for same/matching calendar months.
    """
    all_quotes = fetch_live_mcx_quotes()
    quotes1 = {parse_expiry(q['expiry']).strftime('%Y-%m'): q for q in all_quotes if q['symbol'] == sym1}
    quotes2 = {parse_expiry(q['expiry']).strftime('%Y-%m'): q for q in all_quotes if q['symbol'] == sym2}
    
    common_months = sorted(set(quotes1.keys()) & set(quotes2.keys()))
    results = []
    
    for ym in common_months:
        q1 = quotes1[ym]
        q2 = quotes2[ym]
        
        p1 = q1['effective_price']
        p2 = q2['effective_price']
        
        if p1 <= 0 or p2 <= 0:
            continue
            
        norm1 = normalize_live_price(sym1, p1, basis)
        norm2 = normalize_live_price(sym2, p2, basis)
        
        if norm2 <= 0 or norm1 <= 0:
            continue
            
        if formula == 'leg1_minus_leg2':
            spread = norm1 - norm2
            spread_pct = (spread / norm2) * 100.0
        else:
            spread = norm2 - norm1
            spread_pct = (spread / norm1) * 100.0
            
        dt = datetime.datetime.strptime(ym, '%Y-%m')
        label = dt.strftime('%b %Y')
        
        results.append({
            'month': label,
            'year_month': ym,
            'leg1_symbol': sym1,
            'leg1_expiry': q1['expiry'],
            'leg1_ltp': q1['ltp'],
            'leg1_norm': round(norm1, 2),
            'leg2_symbol': sym2,
            'leg2_expiry': q2['expiry'],
            'leg2_ltp': q2['ltp'],
            'leg2_norm': round(norm2, 2),
            'spread': round(spread, 2),
            'spread_pct': round(spread_pct, 3),
            'basis': basis,
            'is_live': q1['ltp'] > 0 and q2['ltp'] > 0
        })
    return results

def get_live_cross_matrix(basis='10g'):
    """
    Computes real-time cross-instrument spread matrix across active months
    matching Photo 3 (Gold Petal, Gold Guinea, Gold M comparisons).
    """
    all_quotes = fetch_live_mcx_quotes()
    pairs_def = [
        ('GOLDPETAL', 'GOLDGUINEA', 'Gold petal - Gold guinea'),
        ('GOLDPETAL', 'GOLDM', 'Gold petal - Gold M'),
        ('GOLDGUINEA', 'GOLDPETAL', 'Gold guinea - Gold petal'),
        ('GOLDGUINEA', 'GOLDM', 'Gold guinea - Gold M'),
        ('GOLDM', 'GOLDPETAL', 'Gold M - Gold petal'),
        ('GOLDM', 'GOLDGUINEA', 'Gold M - Gold guinea')
    ]

    all_by_sym_month = {}
    available_months_dict = {}

    for q in all_quotes:
        sym = q['symbol']
        if sym not in ['GOLDPETAL', 'GOLDGUINEA', 'GOLDM']:
            continue
        exp_dt = parse_expiry(q['expiry'])
        if exp_dt == datetime.date.max:
            continue
        ym = exp_dt.strftime('%Y-%m')
        if ym not in available_months_dict or exp_dt < available_months_dict[ym]:
            available_months_dict[ym] = exp_dt
        
        all_by_sym_month.setdefault(sym, {})[ym] = {
            'quote': q,
            'norm': normalize_live_price(sym, q['effective_price'], basis),
            'ltp': q['ltp'],
            'expiry': q['expiry'],
            'volume': q['volume']
        }

    # Sort months chronologically
    sorted_months = sorted(available_months_dict.items(), key=lambda x: x[1])
    month_cols = []
    for ym, dt in sorted_months:
        month_cols.append({
            'code': ym,
            'short_label': dt.strftime('%b').upper(),
            'full_label': dt.strftime('%b %Y')
        })

    matrix_rows = []
    for s1, s2, label in pairs_def:
        row_months = {}
        for m in month_cols:
            ym = m['code']
            d1 = all_by_sym_month.get(s1, {}).get(ym)
            d2 = all_by_sym_month.get(s2, {}).get(ym)
            if d1 and d2 and d1['norm'] > 0 and d2['norm'] > 0:
                spread = d1['norm'] - d2['norm']
                spread_pct = (spread / d2['norm']) * 100.0 if d2['norm'] > 0 else 0.0
                row_months[ym] = {
                    'available': True,
                    'spread': round(spread, 2),
                    'spread_pct': round(spread_pct, 2),
                    'leg1_price': d1['norm'],
                    'leg2_price': d2['norm'],
                    'leg1_ltp': d1['ltp'],
                    'leg2_ltp': d2['ltp'],
                    'is_live': d1['ltp'] > 0 and d2['ltp'] > 0
                }
            else:
                row_months[ym] = {
                    'available': False,
                    'spread': 0.0,
                    'spread_pct': 0.0,
                    'leg1_price': 0.0,
                    'leg2_price': 0.0,
                    'is_live': False
                }
        matrix_rows.append({
            'pair_label': label,
            'leg1_symbol': s1,
            'leg2_symbol': s2,
            'months': row_months
        })

    return {
        'months': month_cols,
        'rows': matrix_rows,
        'basis': basis
    }

def get_live_all_calendar_spreads(limit_per_sym=2, formula='leg2_minus_leg1'):
    """
    Fetches live calendar spreads for all 4 commodities (GOLDM, GOLDPETAL, GOLDGUINEA, GOLD),
    optionally limiting to the front 2 active spreads per commodity.
    """
    symbols = ['GOLDM', 'GOLDPETAL', 'GOLDGUINEA', 'GOLD']
    grouped = {}
    flat_list = []
    
    for sym in symbols:
        sym_spreads = get_live_calendar_spreads(symbol=sym, formula=formula)
        if limit_per_sym and limit_per_sym > 0:
            active_spreads = sym_spreads[:limit_per_sym]
        else:
            active_spreads = sym_spreads
        grouped[sym] = active_spreads
        flat_list.extend(active_spreads)
        
    return {
        'symbols': symbols,
        'grouped': grouped,
        'spreads': flat_list
    }

if __name__ == '__main__':
    print("Market Open:", is_market_open())
    quotes = fetch_live_mcx_quotes()
    print("Live quotes count:", len(quotes))
    cal = get_live_calendar_spreads('GOLDM')
    print("GOLDM Live Calendar Spreads:")
    for c in cal:
        print(f"  {c['label']:20} | Near: {c['near_ltp']} ({c['near_expiry']}) | Next: {c['next_ltp']} ({c['next_expiry']}) | Spread: {c['spread']} ({c['spread_pct']}%)")
    cross = get_live_cross_spreads('GOLDM', 'GOLDPETAL')
    print("\nGOLDM vs GOLDPETAL Live Cross Spreads (Rs/10g):")
    for cr in cross:
        print(f"  {cr['month']:10} | GOLDM: {cr['leg1_norm']} | GOLDPETAL: {cr['leg2_norm']} | Spread: {cr['spread']} ({cr['spread_pct']}%)")
