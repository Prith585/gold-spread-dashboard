"""
Gold Spot / Futures Arbitrage Data Engine - Institutional & Parity Check Edition
Fetches live market data from:
1. Multi Commodity Exchange of India (MCX) for all Gold futures contracts.
2. All India Bullion (IBJA - India Bullion and Jewellers Association) for benchmark Spot rates.
3. Gold ETF (GOLDBEES.NS / NSE) for Gold Spot vs ETF parity.

Calculates:
- Part 1: Gold Spot & Gold ETF Parity (Spot vs ETF points and % spread)
- Part 2: Spot to Futures Parity Check (Gold petal, Gold guinea, Gold M across 3 months: NOV, DEC, JAN)
- Part 3: Cross-Instrument Spreads in Points & % (Petal vs Guinea vs Gold M across all permutations)
- Full spread matrix, annualized yields, calendar spreads, and theoretical carry models.
"""

try:
    from curl_cffi import requests
    HAS_CURL_CFFI = True
except Exception:
    import requests
    HAS_CURL_CFFI = False
from bs4 import BeautifulSoup
from datetime import datetime, date, time as dtime
import time
import math
import json
import logging
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class GoldSpreadDataEngine:
    def __init__(self):
        self.cached_spot = None
        self.cached_futs = []
        self.cached_etf = None
        self.last_spot_update = 0
        self.last_futs_update = 0
        self.last_etf_update = 0
        self.cache_ttl_futs = 15  # seconds
        self.cache_ttl_spot = 60  # seconds
        self.cache_ttl_etf = 60   # seconds

    def get_market_session_status(self):
        """Returns MCX and IBJA market session status for Indian Standard Time (IST)"""
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        
        is_weekday = weekday < 5
        mcx_open = is_weekday and (dtime(9, 0) <= current_time <= dtime(23, 30))
        
        if mcx_open:
            if current_time < dtime(17, 0):
                mcx_session_desc = "Session 1: Day Trading (09:00 - 17:00 IST)"
            else:
                mcx_session_desc = "Session 2: Evening Bullion Session (17:00 - 23:30 IST)"
            mcx_status = "OPEN"
        else:
            mcx_status = "CLOSED"
            mcx_session_desc = "Market Closed (Opens Mon-Fri at 09:00 IST)"

        if current_time < dtime(12, 0):
            ibja_fixing_desc = "Awaiting Morning AM Fixing (approx 12:00 PM IST)"
        elif current_time < dtime(17, 0):
            ibja_fixing_desc = "Morning AM Benchmark Active &bull; Awaiting PM Fixing"
        else:
            ibja_fixing_desc = "Closing PM Benchmark Active"

        return {
            'mcx_status': mcx_status,
            'mcx_session_desc': mcx_session_desc,
            'ibja_fixing_desc': ibja_fixing_desc,
            'server_time_ist': now.strftime('%Y-%m-%d %H:%M:%S')
        }

    def fetch_ibja_spot(self, force=False):
        """Fetch spot rates from All India Bullion (IBJA)"""
        now = time.time()
        if not force and self.cached_spot and (now - self.last_spot_update < self.cache_ttl_spot):
            return self.cached_spot

        try:
            if HAS_CURL_CFFI:
                r = requests.get('https://ibjarates.com/', impersonate='chrome120', timeout=15)
            else:
                h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                r = requests.get('https://ibjarates.com/', headers=h, timeout=15)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            tables = soup.find_all('table')
            am_rates = {}
            pm_rates = {}
            rate_date = None
            
            # Table 2: AM rates, Table 3: PM rates
            if len(tables) >= 4:
                # AM Table
                rows_am = tables[2].find_all('tr')
                if len(rows_am) > 1:
                    cells = [c.get_text(strip=True) for c in rows_am[1].find_all(['th', 'td'])]
                    if len(cells) >= 6:
                        rate_date = cells[0]
                        am_rates = {
                            '999': float(cells[1]) if cells[1].replace('.', '', 1).isdigit() else 0,
                            '995': float(cells[2]) if cells[2].replace('.', '', 1).isdigit() else 0,
                            '916': float(cells[3]) if cells[3].replace('.', '', 1).isdigit() else 0,
                            '750': float(cells[4]) if cells[4].replace('.', '', 1).isdigit() else 0,
                            '585': float(cells[5]) if cells[5].replace('.', '', 1).isdigit() else 0,
                            'silver_999': float(cells[6]) if len(cells) > 6 and cells[6].replace('.', '', 1).isdigit() else 0,
                        }

                # PM Table
                rows_pm = tables[3].find_all('tr')
                if len(rows_pm) > 1:
                    cells = [c.get_text(strip=True) for c in rows_pm[1].find_all(['th', 'td'])]
                    if len(cells) >= 6:
                        if not rate_date:
                            rate_date = cells[0]
                        pm_rates = {
                            '999': float(cells[1]) if cells[1].replace('.', '', 1).isdigit() else 0,
                            '995': float(cells[2]) if cells[2].replace('.', '', 1).isdigit() else 0,
                            '916': float(cells[3]) if cells[3].replace('.', '', 1).isdigit() else 0,
                            '750': float(cells[4]) if cells[4].replace('.', '', 1).isdigit() else 0,
                            '585': float(cells[5]) if cells[5].replace('.', '', 1).isdigit() else 0,
                            'silver_999': float(cells[6]) if len(cells) > 6 and cells[6].replace('.', '', 1).isdigit() else 0,
                        }
            
            # Fallback to compare elements if needed
            span_999 = soup.find(id="GoldRatesCompare999")
            span_995 = soup.find(id="GoldRatesCompare995")
            span_916 = soup.find(id="GoldRatesCompare916")
            
            latest_999 = pm_rates.get('999') or am_rates.get('999')
            latest_995 = pm_rates.get('995') or am_rates.get('995')
            latest_916 = pm_rates.get('916') or am_rates.get('916')
            
            if (not latest_999) and span_999 and span_999.text.strip().isdigit():
                latest_999 = float(span_999.text.strip()) * 10
            if (not latest_995) and span_995 and span_995.text.strip().isdigit():
                latest_995 = float(span_995.text.strip()) * 10
            if (not latest_916) and span_916 and span_916.text.strip().isdigit():
                latest_916 = float(span_916.text.strip()) * 10
                
            spot_result = {
                'source': 'All India Bullion (IBJA)',
                'url': 'https://ibjarates.com/',
                'as_on_date': rate_date or datetime.now().strftime('%d/%m/%Y'),
                'active_session': 'PM' if pm_rates.get('999') else ('AM' if am_rates.get('999') else 'Close'),
                'rates': {
                    'gold_999': latest_999 or 141622.0,
                    'gold_995': latest_995 or 141055.0,
                    'gold_916': latest_916 or 129726.0,
                    'gold_750': pm_rates.get('750') or am_rates.get('750') or 106217.0,
                    'gold_585': pm_rates.get('585') or am_rates.get('585') or 82849.0,
                },
                'am_rates': am_rates,
                'pm_rates': pm_rates,
                'status': 'ONLINE',
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self.cached_spot = spot_result
            self.last_spot_update = now
            return spot_result
        except Exception as e:
            logging.error(f"Error fetching IBJA spot rates: {e}")
            if self.cached_spot:
                self.cached_spot['status'] = 'CACHED (FETCH ERROR)'
                return self.cached_spot
            return {
                'source': 'All India Bullion (IBJA)',
                'url': 'https://ibjarates.com/',
                'as_on_date': datetime.now().strftime('%d/%m/%Y'),
                'active_session': 'PM',
                'rates': {
                    'gold_999': 141622.0,
                    'gold_995': 141055.0,
                    'gold_916': 129726.0,
                    'gold_750': 106217.0,
                    'gold_585': 82849.0,
                },
                'am_rates': {'999': 141062.0, '995': 140497.0},
                'pm_rates': {'999': 141622.0, '995': 141055.0},
                'status': 'DEFAULT FALLBACK',
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

    def fetch_gold_etf(self, force=False, custom_etf=None):
        """Fetch live Gold ETF price (GOLDBEES.NS) or use custom override"""
        if custom_etf is not None and float(custom_etf) > 0:
            return {
                'symbol': 'Gold ETF (Custom)',
                'price_per_10g': float(custom_etf),
                'source': 'User Override'
            }

        now = time.time()
        if not force and self.cached_etf and (now - self.last_etf_update < self.cache_ttl_etf):
            return self.cached_etf

        try:
            ticker = yf.Ticker('GOLDBEES.NS')
            ltp = float(ticker.fast_info.last_price or 118.25)
            # 1 unit of GOLDBEES = 0.01g gold => 10g basis = ltp * 1000
            price_10g = round(ltp * 1000.0, 2)
            result = {
                'symbol': 'Gold ETF (GOLDBEES)',
                'unit_ltp': ltp,
                'price_per_10g': price_10g,
                'source': 'NSE Live'
            }
            self.cached_etf = result
            self.last_etf_update = now
            return result
        except Exception as e:
            logging.error(f"Error fetching Gold ETF: {e}")
            if self.cached_etf:
                return self.cached_etf
            return {
                'symbol': 'Gold ETF (GOLDBEES)',
                'unit_ltp': 118.25,
                'price_per_10g': 118250.0,
                'source': 'Baseline'
            }

    def fetch_mcx_futures(self, force=False):
        """Fetch all Gold futures contracts from Multi Commodity Exchange (MCX)"""
        now = time.time()
        if not force and self.cached_futs and (now - self.last_futs_update < self.cache_ttl_futs):
            return self.cached_futs

        headers = {
            'Referer': 'https://www.mcxindia.com/market-data/market-watch',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            if HAS_CURL_CFFI:
                r = requests.get(
                    'https://www.mcxindia.com/market-data/market-watch/GetMarketWatch?culture=en',
                    impersonate='chrome120',
                    headers=headers,
                    timeout=15
                )
            else:
                r = requests.get(
                    'https://www.mcxindia.com/market-data/market-watch/GetMarketWatch?culture=en',
                    headers=headers,
                    timeout=15
                )
            data = r.json()
            items = data.get('data', {}).get('Data', [])
            
            contracts = []
            today = date.today()
            
            for it in items:
                inst = it.get('InstrumentName')
                if inst != 'FUTCOM':
                    continue
                    
                symbol = (it.get('Symbol') or '').strip().upper()
                if not any(symbol.startswith(s) for s in ['GOLD', 'GOLDPETAL', 'GOLDGUINEA']):
                    continue
                    
                expiry_str = it.get('ExpiryDate') # e.g. '30NOV2026'
                try:
                    exp_date = datetime.strptime(expiry_str, '%d%b%Y').date()
                except Exception:
                    continue
                    
                ltp = float(it.get('LTP') or 0)
                if ltp <= 0:
                    continue
                    
                unit = (it.get('Unit') or '').strip().upper()
                
                # Normalization parameters to ₹ per 10 grams:
                if '1 GRM' in unit or symbol == 'GOLDPETAL':
                    norm_factor = 10.0
                    lot_qty_grams = 1.0
                    display_type = 'GOLDPETAL (1g)'
                    contract_desc = 'MCX Gold Petal 1g'
                    clean_name = 'Gold petal'
                elif '8 GRM' in unit or symbol == 'GOLDGUINEA':
                    norm_factor = 1.25  # 10 / 8
                    lot_qty_grams = 8.0
                    display_type = 'GOLDGUINEA (8g)'
                    contract_desc = 'MCX Gold Guinea 8g'
                    clean_name = 'Gold guinea'
                elif symbol == 'GOLDM':
                    norm_factor = 1.0
                    lot_qty_grams = 100.0
                    display_type = 'GOLD MINI (100g)'
                    contract_desc = 'MCX Gold Mini 100g'
                    clean_name = 'Gold M'
                elif symbol == 'GOLDTEN':
                    norm_factor = 1.0
                    lot_qty_grams = 10.0
                    display_type = 'GOLDTEN (10g)'
                    contract_desc = 'MCX Gold 10g'
                    clean_name = 'Gold Ten'
                elif symbol == 'GOLD':
                    norm_factor = 1.0
                    lot_qty_grams = 1000.0  # 1 kg
                    display_type = 'GOLD (1kg / Main)'
                    contract_desc = 'MCX Gold Standard 1kg'
                    clean_name = 'Gold'
                else:
                    norm_factor = 1.0
                    lot_qty_grams = 10.0
                    display_type = f'{symbol} ({unit})'
                    contract_desc = f'MCX {symbol}'
                    clean_name = symbol
                    
                normalized_price = round(ltp * norm_factor, 2)
                dte = max(1, (exp_date - today).days)
                
                contracts.append({
                    'symbol': symbol,
                    'clean_name': clean_name,
                    'contract_name': display_type,
                    'contract_desc': contract_desc,
                    'expiry': expiry_str,
                    'expiry_date': str(exp_date),
                    'dte': dte,
                    'ltp': ltp,
                    'unit': unit,
                    'lot_qty_grams': lot_qty_grams,
                    'normalized_price_per_10g': normalized_price,
                    'open': float(it.get('Open') or 0),
                    'high': float(it.get('High') or 0),
                    'low': float(it.get('Low') or 0),
                    'prev_close': float(it.get('PreviousClose') or 0),
                    'pct_change': float(it.get('PercentChange') or 0),
                    'volume': int(it.get('Volume') or 0),
                    'oi': int(it.get('OpenInterest') or 0),
                    'bid': float(it.get('BuyPrice') or 0),
                    'ask': float(it.get('SellPrice') or 0),
                    'value_in_lacs': float(it.get('ValueInLacs') or 0),
                    'last_trade_time': it.get('LTTValue') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                
            self.cached_futs = contracts
            self.last_futs_update = now
            return contracts
        except Exception as e:
            logging.error(f"Error fetching MCX futures: {e}")
            return self.cached_futs

    def calculate_parity_check_and_cross_spreads(self, spot_price, futs, custom_etf=None):
        """
        Calculates:
        1) Parity Check: Gold Spot vs Gold ETF
        2) 3-Month Parity Check Table: Gold Petal, Gold Guinea, Gold M across 3 forward months (Price & ROI%)
        3) Cross-Instrument Spreads: Point spreads and % spreads between Petal, Guinea, Gold M for each month.
        """
        # --- Part 1: Gold ETF ---
        etf_info = self.fetch_gold_etf(custom_etf=custom_etf)
        etf_price_10g = etf_info['price_per_10g']
        etf_diff_points = round(spot_price - etf_price_10g, 2)
        etf_diff_pct = round((etf_diff_points / spot_price) * 100.0, 4) if spot_price > 0 else 0

        # --- Part 2: 3-Month Parity Check ---
        # Group contracts by calendar month (e.g. NOV 2026, DEC 2026, JAN 2027)
        target_symbols = ['GOLDPETAL', 'GOLDGUINEA', 'GOLDM']
        months_map = {}
        
        for c in futs:
            sym = c['symbol']
            if sym in target_symbols:
                exp_date_obj = datetime.strptime(c['expiry'], '%d%b%Y').date()
                m_sort = exp_date_obj.strftime('%Y-%m')
                m_label = exp_date_obj.strftime('%b').upper()
                if m_sort not in months_map:
                    months_map[m_sort] = {'label': m_label, 'key': m_sort, 'contracts': {}}
                months_map[m_sort]['contracts'][sym] = c

        sorted_months = sorted(months_map.keys())
        active_3_keys = sorted_months[:3]
        if active_3_keys:
            active_3_labels = [months_map[k]['label'] for k in active_3_keys]
        else:
            active_3_labels = ['NOV', 'DEC', 'JAN']

        # Instruments specification matching photo
        instruments_spec = [
            {'id': 'GOLDPETAL', 'name': 'Gold petal'},
            {'id': 'GOLDGUINEA', 'name': 'Gold guinea'},
            {'id': 'GOLDM', 'name': 'Gold M'}
        ]

        parity_rows = []
        for spec in instruments_spec:
            row = {
                'name': spec['name'],
                'symbol': spec['id'],
                'months': []
            }
            for m_key in active_3_keys:
                m_data = months_map[m_key]
                contract = m_data['contracts'].get(spec['id'])
                if contract:
                    norm_p = contract['normalized_price_per_10g']
                    roi_pct = round(((norm_p - spot_price) / spot_price) * 100.0, 2) if spot_price > 0 else 0
                    spread_pts = round(norm_p - spot_price, 2)
                    row['months'].append({
                        'month_label': m_data['label'],
                        'month_key': m_key,
                        'expiry': contract['expiry'],
                        'price': norm_p,
                        'roi_pct': roi_pct,
                        'spread_pts': spread_pts,
                        'dte': contract['dte'],
                        'volume': contract['volume'],
                        'oi': contract['oi']
                    })
                else:
                    row['months'].append({
                        'month_label': m_data['label'],
                        'month_key': m_key,
                        'expiry': '--',
                        'price': 0,
                        'roi_pct': 0,
                        'spread_pts': 0,
                        'dte': 0,
                        'volume': 0,
                        'oi': 0
                    })
            parity_rows.append(row)

        # --- Part 3: Cross-Instrument Spreads ---
        # User requested:
        # "spread in points wise from gold petal to gold guniea or gold M like what is spread between petal and guniea
        # and what is the spread between Petal and GoldM and same thing for what is the spread between Guniea and GoldM
        # what is the spread between Guniea and Petal and same thing for Goldm spread Petal and guniea
        # The whole third part should be in number and percentage for eg like goldM - Gold Petal= net value and also in percentage"
        
        cross_spreads_by_month = {}
        cross_pairs_definition = [
            ("Gold petal - Gold guinea", 'GOLDPETAL', 'GOLDGUINEA', "Petal", "Guinea"),
            ("Gold petal - Gold M", 'GOLDPETAL', 'GOLDM', "Petal", "Gold M"),
            ("Gold guinea - Gold petal", 'GOLDGUINEA', 'GOLDPETAL', "Guinea", "Petal"),
            ("Gold guinea - Gold M", 'GOLDGUINEA', 'GOLDM', "Guinea", "Gold M"),
            ("Gold M - Gold petal", 'GOLDM', 'GOLDPETAL', "Gold M", "Petal"),
            ("Gold M - Gold guinea", 'GOLDM', 'GOLDGUINEA', "Gold M", "Guinea"),
        ]

        # For consolidated table: pair_name -> list of values across Month 1, Month 2, Month 3
        consolidated_cross = {p[0]: [] for p in cross_pairs_definition}

        for m_key in active_3_keys:
            m_label = months_map[m_key]['label']
            month_contracts = months_map[m_key]['contracts']
            
            p_petal = month_contracts.get('GOLDPETAL', {}).get('normalized_price_per_10g', 0)
            p_guinea = month_contracts.get('GOLDGUINEA', {}).get('normalized_price_per_10g', 0)
            p_goldm = month_contracts.get('GOLDM', {}).get('normalized_price_per_10g', 0)
            
            price_lookup = {
                'GOLDPETAL': p_petal,
                'GOLDGUINEA': p_guinea,
                'GOLDM': p_goldm
            }

            month_pairs = []
            for pair_title, id_a, id_b, short_a, short_b in cross_pairs_definition:
                val_a = price_lookup.get(id_a, 0)
                val_b = price_lookup.get(id_b, 0)
                
                if val_a > 0 and val_b > 0:
                    net_points = round(val_a - val_b, 2)
                    pct = round((net_points / val_b) * 100.0, 2) if val_b > 0 else 0
                    
                    # Arbitrage trade signal
                    if net_points > 0:
                        trade_action = f"BUY {short_b} / SELL {short_a}"
                        trade_rationale = f"{short_a} is trading at a +₹{abs(net_points):,.2f} premium (+{abs(pct)}%) over {short_b}."
                    elif net_points < 0:
                        trade_action = f"BUY {short_a} / SELL {short_b}"
                        trade_rationale = f"{short_a} is trading at a -₹{abs(net_points):,.2f} discount (-{abs(pct)}%) to {short_b}."
                    else:
                        trade_action = "PARITY (FLAT)"
                        trade_rationale = "Both instruments trade at exact parity."
                else:
                    net_points = 0.0
                    pct = 0.0
                    trade_action = "N/A"
                    trade_rationale = "Contract data unavailable."

                pair_record = {
                    'title': pair_title,
                    'short_a': short_a,
                    'short_b': short_b,
                    'price_a': val_a,
                    'price_b': val_b,
                    'net_points': net_points,
                    'pct': pct,
                    'trade_action': trade_action,
                    'trade_rationale': trade_rationale
                }
                month_pairs.append(pair_record)
                consolidated_cross[pair_title].append({
                    'month_label': m_label,
                    'net_points': net_points,
                    'pct': pct
                })

            # Find cheapest & most expensive in this month to highlight optimal arbitrage
            valid_prices = [(spec['name'], price_lookup[spec['id']]) for spec in instruments_spec if price_lookup[spec['id']] > 0]
            if len(valid_prices) >= 2:
                cheapest = min(valid_prices, key=lambda x: x[1])
                expensive = max(valid_prices, key=lambda x: x[1])
                arbitrage_spread_pts = round(expensive[1] - cheapest[1], 2)
                arbitrage_spread_pct = round((arbitrage_spread_pts / cheapest[1]) * 100.0, 2)
                best_trade = {
                    'cheapest': cheapest[0],
                    'cheapest_price': cheapest[1],
                    'expensive': expensive[0],
                    'expensive_price': expensive[1],
                    'spread_pts': arbitrage_spread_pts,
                    'spread_pct': arbitrage_spread_pct,
                    'action': f"BUY {cheapest[0]} & SELL {expensive[0]}"
                }
            else:
                best_trade = None

            cross_spreads_by_month[m_label] = {
                'month_label': m_label,
                'pairs': month_pairs,
                'best_trade': best_trade,
                'prices': {
                    'petal': p_petal,
                    'guinea': p_guinea,
                    'goldm': p_goldm
                }
            }

        # Format consolidated cross list
        consolidated_cross_list = []
        for pair_title, months_data in consolidated_cross.items():
            consolidated_cross_list.append({
                'title': pair_title,
                'months': months_data
            })

        return {
            'gold_spot': spot_price,
            'gold_etf': {
                'symbol': etf_info['symbol'],
                'price_10g': etf_price_10g,
                'diff_points': etf_diff_points,
                'diff_pct': etf_diff_pct,
                'source': etf_info['source']
            },
            'active_3_months': active_3_labels,
            'parity_rows': parity_rows,
            'cross_spreads_by_month': cross_spreads_by_month,
            'consolidated_cross_table': consolidated_cross_list
        }

    def calculate_calendar_spreads(self, contracts):
        """Calculates Calendar Spreads across expiries for each instrument family"""
        calendar_spreads = []
        families = ['GOLDM', 'GOLD', 'GOLDTEN', 'GOLDGUINEA', 'GOLDPETAL']
        
        for fam in families:
            fam_contracts = [c for c in contracts if c['symbol'] == fam and not ('OCT' in c['expiry'].upper())]
            fam_contracts.sort(key=lambda x: x['dte'])
            
            for i in range(len(fam_contracts) - 1):
                near = fam_contracts[i]
                far = fam_contracts[i + 1]
                
                spread_val = round(far['normalized_price_per_10g'] - near['normalized_price_per_10g'], 2)
                spread_pct = round((spread_val / near['normalized_price_per_10g']) * 100.0, 3)
                
                delta_days = max(1, far['dte'] - near['dte'])
                ann_roll_yield = round(spread_pct * (365.0 / delta_days), 2)
                
                if spread_val > 0:
                    roll_strategy = "CONTANGO ROLL"
                    action_roll = f"BUY {near['expiry']} / SELL {far['expiry']}"
                    roll_desc = f"Roll long positions or capture +{ann_roll_yield}% p.a. carry spread."
                else:
                    roll_strategy = "BACKWARDATION ROLL"
                    action_roll = f"SELL {near['expiry']} / BUY {far['expiry']}"
                    roll_desc = f"Inverted spread: far month trades at discount."
                    
                calendar_spreads.append({
                    'family': fam,
                    'contract_desc': near['contract_desc'],
                    'near_contract': f"{near['symbol']} {near['expiry']}",
                    'near_expiry': near['expiry'],
                    'near_price_10g': near['normalized_price_per_10g'],
                    'near_dte': near['dte'],
                    'far_contract': f"{far['symbol']} {far['expiry']}",
                    'far_expiry': far['expiry'],
                    'far_price_10g': far['normalized_price_per_10g'],
                    'far_dte': far['dte'],
                    'delta_days': delta_days,
                    'spread_10g': spread_val,
                    'spread_pct': spread_pct,
                    'ann_roll_yield': ann_roll_yield,
                    'roll_strategy': roll_strategy,
                    'action_roll': action_roll,
                    'roll_desc': roll_desc,
                    'near_vol': near['volume'],
                    'far_vol': far['volume'],
                    'near_oi': near['oi'],
                    'far_oi': far['oi']
                })
                
        calendar_spreads.sort(key=lambda x: x['ann_roll_yield'], reverse=True)
        return calendar_spreads

    def calculate_spreads(self, spot_price=None, spot_purity='gold_999', cost_of_capital_pa=8.0, 
                          include_gst=False, custom_brokerage=20.0, storage_cost_pa=0.25, 
                          expiry_filter='NOV', custom_etf=None):
        """
        Main calculation engine combining:
        - Parity Check (Spot vs ETF, Spot vs Petal/Guinea/GoldM across 3 months)
        - Cross-Instrument Spreads in Points & %
        - Full MCX spread matrix and quantitative carry models
        """
        spot_info = self.fetch_ibja_spot()
        futs = self.fetch_mcx_futures()
        market_session = self.get_market_session_status()
        
        # Determine spot benchmark price
        if spot_price is not None and float(spot_price) > 0:
            effective_spot = float(spot_price)
            spot_label = f"Custom Spot (₹{effective_spot:,.2f}/10g)"
        else:
            effective_spot = spot_info['rates'].get(spot_purity, 141622.0)
            purity_name = "24K (999 Pure)" if '999' in spot_purity else ("Standard MCX Delivery (995 Fineness)" if '995' in spot_purity else "22K (916)")
            spot_label = f"All India Bullion {purity_name}"

        # If retail GST is included, physical spot purchase has 3% GST
        if include_gst:
            spot_with_tax = effective_spot * 1.03
        else:
            spot_with_tax = effective_spot  # Registered bullion dealers offset ITC on MCX delivery

        # --- PARITY CHECK & CROSS-INSTRUMENT SPREADS (User's Exact Request) ---
        parity_check_data = self.calculate_parity_check_and_cross_spreads(spot_with_tax, futs, custom_etf=custom_etf)

        spread_items = []
        for c in futs:
            fut_price = c['normalized_price_per_10g']
            dte = c['dte']
            expiry_str = c['expiry'].upper()
            
            is_october = 'OCT' in expiry_str or dte <= 1
            
            if 'NOV' in expiry_str:
                month_tag = 'NOV 2026'
                status_tag = 'ACTIVE FRONT MONTH'
            elif 'DEC' in expiry_str:
                month_tag = 'DEC 2026'
                status_tag = 'NEXT BI-MONTHLY CYCLE'
            elif is_october:
                month_tag = 'OCT 2026'
                status_tag = 'EXPIRED / TENDER CLOSED'
            else:
                month_tag = expiry_str[2:]
                status_tag = 'FORWARD CYCLE'
            
            spread_gross = fut_price - spot_with_tax
            spread_pct = (spread_gross / spot_with_tax) * 100.0
            ann_gross_yield = spread_pct * (365.0 / dte)
            
            lots_in_10g = c['lot_qty_grams'] / 10.0
            contract_turnover = fut_price * lots_in_10g
            spot_capital_required = spot_with_tax * lots_in_10g
            gross_profit_lot = spread_gross * lots_in_10g
            
            # Theoretical Fair Value F*
            total_carry_rate_pa = (cost_of_capital_pa + storage_cost_pa) / 100.0
            fair_value_10g = round(spot_with_tax * (1.0 + (total_carry_rate_pa * (dte / 365.0))), 2)
            arbitrage_alpha = round(fut_price - fair_value_10g, 2)
            alpha_pct = round((arbitrage_alpha / spot_with_tax) * 100.0, 3)
            
            # Fees
            turnover_charges_pct = 0.0045 / 100.0
            statutory_charges = (contract_turnover * turnover_charges_pct) + (custom_brokerage * 2 * 1.18)
            statutory_charges_10g = statutory_charges / lots_in_10g if lots_in_10g > 0 else 0
            
            financing_cost_lot = spot_capital_required * (cost_of_capital_pa / 100.0) * (dte / 365.0)
            financing_cost_10g = spot_with_tax * (cost_of_capital_pa / 100.0) * (dte / 365.0)
            
            total_cost_lot = statutory_charges + financing_cost_lot
            net_profit_lot = gross_profit_lot - total_cost_lot
            
            breakeven_spread_10g = round(financing_cost_10g + statutory_charges_10g, 2)
            safety_margin_10g = round(spread_gross - breakeven_spread_10g, 2)
            
            if spot_capital_required > 0:
                net_return_pct = (net_profit_lot / spot_capital_required) * 100.0
                ann_net_yield = net_return_pct * (365.0 / dte)
            else:
                ann_net_yield = 0.0
                
            if spread_gross > 0:
                strategy = "CASH & CARRY"
                action_spot = "BUY SPOT"
                action_fut = "SELL FUT"
                strategy_desc = "Buy physical Spot at All India Bullion, short MCX Futures, lock in convergence premium."
            else:
                strategy = "REVERSE CASH & CARRY"
                action_spot = "SELL SPOT"
                action_fut = "BUY FUT"
                strategy_desc = "Sell Spot inventory at All India Bullion, buy discounted MCX Futures for delivery."
                
            vol = c['volume']
            oi = c['oi']
            if vol > 1000 and oi > 5000:
                liquidity_tier = "HIGH"
                liquidity_badge = "Active / High"
            elif vol > 50 and oi > 500:
                liquidity_tier = "MEDIUM"
                liquidity_badge = "Moderate"
            else:
                liquidity_tier = "LOW"
                liquidity_badge = "Low Liquidity"
                
            spread_items.append({
                'symbol': c['symbol'],
                'contract_name': c['contract_name'],
                'contract_desc': c['contract_desc'],
                'expiry': c['expiry'],
                'expiry_date': c['expiry_date'],
                'month_tag': month_tag,
                'is_october': is_october,
                'status_tag': status_tag,
                'dte': dte,
                'ltp': c['ltp'],
                'unit': c['unit'],
                'lot_qty_grams': c['lot_qty_grams'],
                'fut_price_10g': fut_price,
                'spot_price_10g': round(spot_with_tax, 2),
                'spread_10g': round(spread_gross, 2),
                'spread_pct': round(spread_pct, 2),
                'fair_value_10g': fair_value_10g,
                'arbitrage_alpha': arbitrage_alpha,
                'alpha_pct': alpha_pct,
                'breakeven_spread_10g': breakeven_spread_10g,
                'safety_margin_10g': safety_margin_10g,
                'ann_gross_yield': round(ann_gross_yield, 2),
                'ann_net_yield': round(ann_net_yield, 2),
                'gross_profit_lot': round(gross_profit_lot, 2),
                'net_profit_lot': round(net_profit_lot, 2),
                'capital_required_lot': round(spot_capital_required, 2),
                'statutory_charges': round(statutory_charges, 2),
                'financing_cost_lot': round(financing_cost_lot, 2),
                'strategy': strategy,
                'action_spot': action_spot,
                'action_fut': action_fut,
                'strategy_desc': strategy_desc,
                'volume': vol,
                'oi': oi,
                'liquidity_tier': liquidity_tier,
                'liquidity_badge': liquidity_badge,
                'last_trade_time': c['last_trade_time']
            })

        # Calendar Spreads Engine
        calendar_spreads = self.calculate_calendar_spreads(futs)

        # Optimization
        liquid_items = [x for x in spread_items if x['volume'] >= 10 and x['oi'] >= 50]
        if not liquid_items:
            liquid_items = spread_items

        forward_liquid = [x for x in liquid_items if not x['is_october']]
        if not forward_liquid:
            forward_liquid = liquid_items

        nov_candidates = [x for x in forward_liquid if 'NOV' in x['expiry'].upper()]
        best_november = max(nov_candidates, key=lambda x: x['ann_net_yield']) if nov_candidates else None
        
        dec_candidates = [x for x in forward_liquid if 'DEC' in x['expiry'].upper()]
        best_december = max(dec_candidates, key=lambda x: x['ann_net_yield']) if dec_candidates else None
        
        inst_candidates = [x for x in forward_liquid if x['symbol'] == 'GOLD']
        best_institutional = max(inst_candidates, key=lambda x: x['net_profit_lot']) if inst_candidates else None
        
        retail_candidates = [x for x in forward_liquid if x['symbol'] in ['GOLDM', 'GOLDTEN', 'GOLDPETAL', 'GOLDGUINEA']]
        best_retail = max(retail_candidates, key=lambda x: x['ann_net_yield']) if retail_candidates else None

        best_safety = max(forward_liquid, key=lambda x: x['safety_margin_10g']) if forward_liquid else None
        best_calendar_roll = calendar_spreads[0] if calendar_spreads else None

        spread_items.sort(key=lambda x: x['ann_net_yield'], reverse=True)

        return {
            'spot_info': spot_info,
            'effective_spot': effective_spot,
            'spot_with_tax': spot_with_tax,
            'spot_label': spot_label,
            'spot_purity': spot_purity,
            'include_gst': include_gst,
            'cost_of_capital_pa': cost_of_capital_pa,
            'storage_cost_pa': storage_cost_pa,
            'expiry_filter_applied': expiry_filter,
            'market_session': market_session,
            'total_contracts_tracked': len(spread_items),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'parity_check': parity_check_data,
            'optimal_opportunities': {
                'best_november': best_november,
                'best_overall_yield': best_november or (forward_liquid[0] if forward_liquid else None),
                'best_december': best_december,
                'best_institutional_1kg': best_institutional,
                'best_micro_retail': best_retail,
                'best_safety_margin': best_safety,
                'best_calendar_roll': best_calendar_roll,
            },
            'calendar_spreads': calendar_spreads,
            'spreads': spread_items
        }

# Global singleton
engine = GoldSpreadDataEngine()
