import sqlite3
import os
import datetime
import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), 'mcx_gold_data.db')

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def get_available_contracts():
    """Returns all available contracts in the database with their trading ranges."""
    conn = get_db_connection()
    query = """
        SELECT 
            symbol,
            expiry_date,
            MIN(trade_date) as start_date,
            MAX(trade_date) as end_date,
            COUNT(*) as trading_days,
            ROUND(AVG(volume), 1) as avg_volume,
            MAX(open_interest) as max_oi
        FROM gold_futures
        GROUP BY symbol, expiry_date
        ORDER BY symbol, expiry_date
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Sort expiries chronologically
    def parse_exp(s):
        try:
            return datetime.datetime.strptime(s.strip(), '%d%b%Y')
        except:
            return datetime.datetime(2000, 1, 1)
            
    df['exp_dt'] = df['expiry_date'].apply(parse_exp)
    df = df.sort_values(by=['symbol', 'exp_dt']).reset_index(drop=True)
    return df

def load_contract_df(symbol, expiry):
    """Loads cleaned daily OHLCV series for a single contract."""
    conn = get_db_connection()
    query = """
        SELECT trade_date, open, high, low, close, prev_close, volume, open_interest, value_lacs
        FROM gold_futures
        WHERE symbol = ? AND expiry_date = ?
        ORDER BY trade_date ASC
    """
    df = pd.read_sql_query(query, conn, params=(symbol, expiry))
    conn.close()
    
    if df.empty:
        return pd.DataFrame()
        
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    return df

def load_warehouse_inventory(symbol='GOLDM'):
    """
    Loads daily MCX warehouse deliverable stock position (vault stock).
    Returns DataFrame indexed by trade_date with inventory_qty, inventory_display, inventory_unit.
    """
    conn = get_db_connection()
    try:
        q = "SELECT trade_date, gold_kg, gold_mini_gm, gold_petal_gm, gold_guinea_gm FROM warehouse_inventory"
        df_inv = pd.read_sql_query(q, conn)
        if df_inv.empty:
            return pd.DataFrame()
        df_inv['trade_date'] = pd.to_datetime(df_inv['trade_date'])
        df_inv = df_inv.set_index('trade_date').sort_index()
        
        # Pick relevant commodity column
        if symbol == 'GOLD':
            df_inv['inventory_qty'] = df_inv['gold_kg']
            df_inv['inventory_display'] = df_inv['gold_kg'].apply(lambda x: f"{x:,.1f} KG" if pd.notna(x) else "—")
            df_inv['inventory_unit'] = 'KG'
        elif symbol == 'GOLDM':
            df_inv['inventory_qty'] = df_inv['gold_mini_gm'] / 1000.0  # in KG
            df_inv['inventory_display'] = df_inv.apply(lambda r: f"{r['gold_mini_gm']/1000.0:,.1f} KG ({int(r['gold_mini_gm']/100):,} lots)" if pd.notna(r['gold_mini_gm']) else "—", axis=1)
            df_inv['inventory_unit'] = 'KG'
        elif symbol == 'GOLDPETAL':
            df_inv['inventory_qty'] = df_inv['gold_petal_gm'] # in GM
            df_inv['inventory_display'] = df_inv.apply(lambda r: f"{r['gold_petal_gm']:,.0f} GM ({r['gold_petal_gm']/1000.0:,.2f} KG)" if pd.notna(r['gold_petal_gm']) else "—", axis=1)
            df_inv['inventory_unit'] = 'GM'
        elif symbol == 'GOLDGUINEA':
            df_inv['inventory_qty'] = df_inv['gold_guinea_gm'] # in GM
            df_inv['inventory_display'] = df_inv.apply(lambda r: f"{r['gold_guinea_gm']:,.0f} GM ({int(r['gold_guinea_gm']/8):,} Guineas)" if pd.notna(r['gold_guinea_gm']) else "—", axis=1)
            df_inv['inventory_unit'] = 'GM'
        else:
            df_inv['inventory_qty'] = df_inv['gold_kg']
            df_inv['inventory_display'] = df_inv['gold_kg'].apply(lambda x: f"{x:,.1f} KG" if pd.notna(x) else "—")
            df_inv['inventory_unit'] = 'KG'
            
        return df_inv[['inventory_qty', 'inventory_display', 'inventory_unit']]
    except Exception as e:
        print("Error loading inventory:", e)
        return pd.DataFrame()
    finally:
        conn.close()

def build_pair_spread(symbol1, expiry1, symbol2, expiry2, spread_formula='leg2_minus_leg1'):
    """
    Builds clean daily closing spread series between two specific contracts.
    spread_formula: 
       'leg2_minus_leg1': Next Month Future Close - Current Month Future Close (Default)
       'leg1_minus_leg2': Current Month Future Close - Next Month Future Close
    """
    df1 = load_contract_df(symbol1, expiry1)
    df2 = load_contract_df(symbol2, expiry2)
    
    if df1.empty or df2.empty:
        return pd.DataFrame(), {}
        
    # Inner join on common trading dates
    merged = df1.join(df2, lsuffix='_leg1', rsuffix='_leg2', how='inner')
    if len(merged) < 2:
        return pd.DataFrame(), {}
        
    merged = merged.sort_index()
    
    close1 = merged['close_leg1']
    close2 = merged['close_leg2']
    
    if spread_formula == 'leg1_minus_leg2':
        # Active Future - Next Future
        merged['spread_close'] = close1 - close2
    else:
        # Next Future - Active Future
        merged['spread_close'] = close2 - close1
        
    # Calculate Spread % relative to Leg 1 (Active Future)
    merged['spread_pct'] = (merged['spread_close'] / close1.replace(0, np.nan)) * 100.0
    
    # Calculate daily changes
    merged['spread_change'] = merged['spread_close'].diff().fillna(0.0)
    merged['spread_pct_change'] = merged['spread_pct'].diff().fillna(0.0)
    
    merged['leg1_symbol'] = symbol1
    merged['leg1_expiry'] = expiry1
    merged['leg2_symbol'] = symbol2
    merged['leg2_expiry'] = expiry2
    merged['pair_label'] = f"{expiry1} - {expiry2}"
    
    # Parse expiry dates for basis calculation
    try:
        dt1 = datetime.datetime.strptime(expiry1.strip(), '%d%b%Y')
        dt2 = datetime.datetime.strptime(expiry2.strip(), '%d%b%Y')
        days_diff = abs((dt2 - dt1).days) or 30
    except:
        days_diff = 30
        
    merged['days_diff'] = days_diff
    merged['annualized_basis_pct'] = merged['spread_pct'] * (365.0 / days_diff)
    
    # Attach MCX warehouse inventory (Stock position)
    inv_df = load_warehouse_inventory(symbol1)
    if not inv_df.empty:
        merged = merged.join(inv_df, how='left')
        merged['inventory_qty'] = merged['inventory_qty'].ffill().bfill().fillna(0.0)
        merged['inventory_display'] = merged['inventory_display'].ffill().bfill().fillna('—')
        merged['inventory_unit'] = merged['inventory_unit'].ffill().bfill().fillna('KG')
    else:
        merged['inventory_qty'] = 0.0
        merged['inventory_display'] = '—'
        merged['inventory_unit'] = 'KG'
    
    # Metadata
    meta = {
        'type': 'pair',
        'symbol1': symbol1,
        'expiry1': expiry1,
        'symbol2': symbol2,
        'expiry2': expiry2,
        'days_diff': days_diff,
        'formula': spread_formula,
        'total_days': len(merged),
        'start_date': merged.index.min().strftime('%Y-%m-%d'),
        'end_date': merged.index.max().strftime('%Y-%m-%d'),
        'latest_close_leg1': float(close1.iloc[-1]),
        'latest_close_leg2': float(close2.iloc[-1]),
        'latest_spread': float(merged['spread_close'].iloc[-1]),
        'latest_spread_pct': float(merged['spread_pct'].iloc[-1]),
        'avg_spread': float(merged['spread_close'].mean()),
        'avg_spread_pct': float(merged['spread_pct'].mean()),
        'max_spread': float(merged['spread_close'].max()),
        'min_spread': float(merged['spread_close'].min())
    }
    return merged, meta

def build_rolling_calendar_spread(symbol='GOLD', roll_days_before_expiry=5, spread_formula='leg2_minus_leg1'):
    """
    Constructs continuous 1-year calendar spread series (Next Month Future Close - Current Month Future Close).
    Automatically rolls forward to the next cycle when current active future is within roll_days_before_expiry.
    spread_formula:
       'leg2_minus_leg1': Next Month Future Close - Current Month Future Close (Default)
       'leg1_minus_leg2': Current Month Future Close - Next Month Future Close
    """
    conn = get_db_connection()
    q = "SELECT DISTINCT expiry_date FROM gold_futures WHERE symbol = ?"
    exp_rows = pd.read_sql_query(q, conn, params=(symbol,))
    conn.close()
    
    if exp_rows.empty:
        return pd.DataFrame(), {}
        
    def parse_exp(s):
        try:
            return datetime.datetime.strptime(s.strip(), '%d%b%Y').date()
        except:
            return None
            
    exp_rows['exp_dt'] = exp_rows['expiry_date'].apply(parse_exp)
    exp_rows = exp_rows.dropna().sort_values('exp_dt').reset_index(drop=True)
    
    conn = get_db_connection()
    q_all = """
        SELECT trade_date, expiry_date, close, volume, open_interest
        FROM gold_futures
        WHERE symbol = ?
        ORDER BY trade_date ASC
    """
    df_all = pd.read_sql_query(q_all, conn, params=(symbol,))
    conn.close()
    
    if df_all.empty:
        return pd.DataFrame(), {}
        
    df_all['trade_date'] = pd.to_datetime(df_all['trade_date']).dt.date
    df_all['exp_dt'] = df_all['expiry_date'].apply(parse_exp)
    
    trade_dates = sorted(df_all['trade_date'].unique())
    indexed = df_all.set_index(['trade_date', 'expiry_date'])
    
    records = []
    
    for t_date in trade_dates:
        # Active M1 contracts: expiry > t_date + roll_days_before_expiry
        cutoff = t_date + datetime.timedelta(days=roll_days_before_expiry)
        active_expiries = exp_rows[exp_rows['exp_dt'] > cutoff].copy()
        
        if len(active_expiries) < 2:
            continue
            
        m1_exp = active_expiries.iloc[0]['expiry_date']
        m2_exp = active_expiries.iloc[1]['expiry_date']
        
        key1 = (t_date, m1_exp)
        key2 = (t_date, m2_exp)
        
        if key1 in indexed.index and key2 in indexed.index:
            row1 = indexed.loc[key1]
            row2 = indexed.loc[key2]
            
            if isinstance(row1, pd.DataFrame):
                row1 = row1.iloc[0]
            if isinstance(row2, pd.DataFrame):
                row2 = row2.iloc[0]
                
            close1 = float(row1['close'])
            close2 = float(row2['close'])
            
            if spread_formula == 'leg1_minus_leg2':
                spread_close = close1 - close2  # Active minus Next
            else:
                spread_close = close2 - close1  # Next minus Active
            
            spread_pct = (spread_close / (close1 or 1)) * 100.0
            
            exp_dt1 = active_expiries.iloc[0]['exp_dt']
            exp_dt2 = active_expiries.iloc[1]['exp_dt']
            days_diff = abs((exp_dt2 - exp_dt1).days) or 30
            annualized_pct = spread_pct * (365.0 / days_diff)
            pair_label = f"{exp_dt1.strftime('%b %Y')} - {exp_dt2.strftime('%b %Y')}"
            
            records.append({
                'trade_date': pd.to_datetime(t_date),
                'pair_label': pair_label,
                'close_leg1': close1,
                'volume_leg1': int(row1['volume']),
                'oi_leg1': int(row1['open_interest']),
                'leg1_symbol': symbol,
                'leg1_expiry': m1_exp,
                
                'close_leg2': close2,
                'volume_leg2': int(row2['volume']),
                'oi_leg2': int(row2['open_interest']),
                'leg2_symbol': symbol,
                'leg2_expiry': m2_exp,
                
                'spread_close': spread_close,
                'spread_pct': spread_pct,
                'days_diff': days_diff,
                'annualized_basis_pct': annualized_pct
            })
            
    if not records:
        return pd.DataFrame(), {}
        
    df_res = pd.DataFrame(records).set_index('trade_date').sort_index()
    
    # Calculate daily changes
    df_res['spread_change'] = df_res['spread_close'].diff().fillna(0.0)
    df_res['spread_pct_change'] = df_res['spread_pct'].diff().fillna(0.0)
    
    # Mark roll dates where leg1_expiry changes
    df_res['roll_event'] = (df_res['leg1_expiry'] != df_res['leg1_expiry'].shift(1)) & (df_res['leg1_expiry'].shift(1).notna())
    
    # Attach MCX warehouse inventory (Stock position)
    inv_df = load_warehouse_inventory(symbol)
    if not inv_df.empty:
        df_res = df_res.join(inv_df, how='left')
        df_res['inventory_qty'] = df_res['inventory_qty'].ffill().bfill().fillna(0.0)
        df_res['inventory_display'] = df_res['inventory_display'].ffill().bfill().fillna('—')
        df_res['inventory_unit'] = df_res['inventory_unit'].ffill().bfill().fillna('KG')
    else:
        df_res['inventory_qty'] = 0.0
        df_res['inventory_display'] = '—'
        df_res['inventory_unit'] = 'KG'
    
    close1 = df_res['close_leg1']
    close2 = df_res['close_leg2']
    
    meta = {
        'type': 'continuous_rolling',
        'symbol': symbol,
        'roll_days_before_expiry': roll_days_before_expiry,
        'formula': spread_formula,
        'total_days': len(df_res),
        'start_date': df_res.index.min().strftime('%Y-%m-%d'),
        'end_date': df_res.index.max().strftime('%Y-%m-%d'),
        'total_rolls': int(df_res['roll_event'].sum()),
        'latest_close_leg1': float(close1.iloc[-1]),
        'latest_close_leg2': float(close2.iloc[-1]),
        'latest_spread': float(df_res['spread_close'].iloc[-1]),
        'latest_spread_pct': float(df_res['spread_pct'].iloc[-1]),
        'avg_spread': float(df_res['spread_close'].mean()),
        'avg_spread_pct': float(df_res['spread_pct'].mean()),
        'max_spread': float(df_res['spread_close'].max()),
        'min_spread': float(df_res['spread_close'].min())
    }
    return df_res, meta

def get_consecutive_monthly_pairs(symbol='GOLDM', formula='leg2_minus_leg1'):
    """
    Returns data for the consecutive monthly spread pairs:
    Spread = Next Month Future Close - Current Month Future Close
    Spread % = (Spread / Current Month Future Close) * 100
    Oct 2025 - Nov 2025, Nov 2025 - Dec 2025, ..., Nov 2026 - Dec 2026.
    """
    conn = get_db_connection()
    q = "SELECT DISTINCT expiry_date FROM gold_futures WHERE symbol = ?"
    exp_rows = pd.read_sql_query(q, conn, params=(symbol,))
    conn.close()
    
    if exp_rows.empty:
        return []

    def parse_exp(s):
        try:
            return datetime.datetime.strptime(s.strip(), '%d%b%Y').date()
        except:
            return None

    exp_rows['exp_dt'] = exp_rows['expiry_date'].apply(parse_exp)
    exp_rows = exp_rows.dropna().sort_values('exp_dt').reset_index(drop=True)
    
    # Filter for expiries starting around Sep/Oct 2025 to Jan 2027
    start_filter = datetime.date(2025, 9, 15)
    end_filter = datetime.date(2027, 1, 15)
    exp_rows = exp_rows[(exp_rows['exp_dt'] >= start_filter) & (exp_rows['exp_dt'] <= end_filter)].reset_index(drop=True)

    pairs_summary = []

    # Loop through consecutive pairs (E_i, E_{i+1})
    for i in range(len(exp_rows) - 1):
        near_exp = exp_rows.iloc[i]['expiry_date']
        next_exp = exp_rows.iloc[i+1]['expiry_date']
        near_dt = exp_rows.iloc[i]['exp_dt']
        next_dt = exp_rows.iloc[i+1]['exp_dt']

        # Label: e.g. "Oct 2025 - Nov 2025"
        label = f"{near_dt.strftime('%b %Y')} - {next_dt.strftime('%b %Y')}"

        df_pair, meta = build_pair_spread(symbol, near_exp, symbol, next_exp, spread_formula=formula)
        if df_pair.empty:
            continue

        close1 = df_pair['close_leg1']
        close2 = df_pair['close_leg2']
        spread = df_pair['spread_close']
        spread_pct = df_pair['spread_pct']

        latest_d = df_pair.index[-1].strftime('%Y-%m-%d')
        latest_c1 = float(close1.iloc[-1])
        latest_c2 = float(close2.iloc[-1])
        latest_sp = float(spread.iloc[-1])
        latest_sp_pct = float(spread_pct.iloc[-1])

        avg_sp = float(spread.mean())
        avg_sp_pct = float(spread_pct.mean())
        max_sp = float(spread.max())
        min_sp = float(spread.min())

        pairs_summary.append({
            'label': label,
            'near_expiry': near_exp,
            'next_expiry': next_exp,
            'near_date': near_dt.strftime('%Y-%m-%d'),
            'next_date': next_dt.strftime('%Y-%m-%d'),
            'latest_date': latest_d,
            'near_close': round(latest_c1, 1),
            'next_close': round(latest_c2, 1),
            'spread': round(latest_sp, 1),
            'spread_pct': round(latest_sp_pct, 2),
            'avg_spread': round(avg_sp, 1),
            'avg_spread_pct': round(avg_sp_pct, 2),
            'max_spread': round(max_sp, 1),
            'min_spread': round(min_sp, 1),
            'trading_days': len(df_pair),
            'start_date': df_pair.index[0].strftime('%Y-%m-%d'),
            'end_date': latest_d
        })

    return pairs_summary

def normalize_price(symbol, close, basis='10g'):
    """
    Normalizes MCX gold contract prices to a common weight basis:
    - GOLDM: Quoted per 10 grams (close)
    - GOLDPETAL: Quoted per 1 gram (close * 10 for 10g)
    - GOLDGUINEA: Quoted per 8 grams (close / 8 * 10 for 10g)
    """
    if close is None or pd.isna(close):
        return 0.0
    close = float(close)
    if basis == '10g':
        if symbol == 'GOLDM':
            return close
        elif symbol == 'GOLDPETAL':
            return close * 10.0
        elif symbol == 'GOLDGUINEA':
            return (close / 8.0) * 10.0
    elif basis == '1g':
        if symbol == 'GOLDM':
            return close / 10.0
        elif symbol == 'GOLDPETAL':
            return close
        elif symbol == 'GOLDGUINEA':
            return close / 8.0
    return close

def build_cross_commodity_spread(symbol1='GOLDM', symbol2='GOLDPETAL', basis='10g', spread_formula='leg1_minus_leg2'):
    """
    Calculates daily cross-commodity spread between any two MCX gold contract variants
    (GOLDM, GOLDPETAL, GOLDGUINEA) normalized to common weight basis ('10g', '1g', or 'raw').
    """
    conn = get_db_connection()
    q = "SELECT trade_date, symbol, expiry_date, close, volume, open_interest FROM gold_futures WHERE symbol IN (?, ?) ORDER BY trade_date ASC"
    df = pd.read_sql_query(q, conn, params=(symbol1, symbol2))
    conn.close()
    
    if df.empty:
        return pd.DataFrame(), {}
        
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    
    def parse_exp(s):
        try:
            return datetime.datetime.strptime(s.strip(), '%d%b%Y')
        except:
            return None
            
    df['exp_dt'] = df['expiry_date'].apply(parse_exp)
    df_act = df[df['exp_dt'] >= df['trade_date']].sort_values(['trade_date', 'exp_dt', 'volume'], ascending=[True, True, False])
    
    df1 = df_act[df_act['symbol'] == symbol1].drop_duplicates(subset=['trade_date'], keep='first').set_index('trade_date')
    df2 = df_act[df_act['symbol'] == symbol2].drop_duplicates(subset=['trade_date'], keep='first').set_index('trade_date')
    
    if df1.empty or df2.empty:
        return pd.DataFrame(), {}
        
    merged = df1.join(df2, lsuffix='_leg1', rsuffix='_leg2', how='inner')
    if merged.empty:
        return pd.DataFrame(), {}
        
    merged = merged.sort_index()
    
    c1_raw = merged['close_leg1']
    c2_raw = merged['close_leg2']
    
    p1 = c1_raw.apply(lambda c: normalize_price(symbol1, c, basis))
    p2 = c2_raw.apply(lambda c: normalize_price(symbol2, c, basis))
    
    if spread_formula == 'leg1_minus_leg2':
        spread = p1 - p2
        spread_pct = (spread / p2.replace(0, np.nan)) * 100.0
    else:
        spread = p2 - p1
        spread_pct = (spread / p1.replace(0, np.nan)) * 100.0
        
    merged['norm_price_leg1'] = p1
    merged['norm_price_leg2'] = p2
    merged['spread_close'] = spread
    merged['spread_pct'] = spread_pct
    merged['spread_change'] = spread.diff().fillna(0.0)
    merged['spread_pct_change'] = spread_pct.diff().fillna(0.0)
    
    unit_label = '₹ / 10g' if basis == '10g' else ('₹ / 1g' if basis == '1g' else 'Quoted Points')
    merged['unit_label'] = unit_label
    
    # Month period label for grouping
    merged['pair_label'] = merged.index.strftime('%b %Y')
    
    # Inventory
    inv_df = load_warehouse_inventory('GOLDM')
    if not inv_df.empty:
        merged = merged.join(inv_df, how='left')
        merged['inventory_qty'] = merged['inventory_qty'].ffill().bfill().fillna(0.0)
        merged['inventory_display'] = merged['inventory_display'].ffill().bfill().fillna('—')
        merged['inventory_unit'] = merged['inventory_unit'].ffill().bfill().fillna('KG')
    else:
        merged['inventory_qty'] = 0.0
        merged['inventory_display'] = '—'
        merged['inventory_unit'] = 'KG'
        
    meta = {
        'type': 'cross_commodity',
        'symbol1': symbol1,
        'symbol2': symbol2,
        'basis': basis,
        'unit_label': unit_label,
        'formula': spread_formula,
        'total_days': len(merged),
        'start_date': merged.index.min().strftime('%Y-%m-%d'),
        'end_date': merged.index.max().strftime('%Y-%m-%d'),
        'latest_c1_raw': float(c1_raw.iloc[-1]),
        'latest_c2_raw': float(c2_raw.iloc[-1]),
        'latest_p1_norm': float(p1.iloc[-1]),
        'latest_p2_norm': float(p2.iloc[-1]),
        'latest_spread': float(spread.iloc[-1]),
        'latest_spread_pct': float(spread_pct.iloc[-1]),
        'avg_spread': float(spread.mean()),
        'avg_spread_pct': float(spread_pct.mean()),
        'max_spread': float(spread.max()),
        'min_spread': float(spread.min())
    }
    return merged, meta

def get_cross_commodity_monthly_summary(symbol1='GOLDM', symbol2='GOLDPETAL', basis='10g', spread_formula='leg1_minus_leg2'):
    """
    Groups the cross-commodity spread into consecutive monthly periods from Sep 2025 to Nov 2026.
    """
    df_cross, meta = build_cross_commodity_spread(symbol1, symbol2, basis=basis, spread_formula=spread_formula)
    if df_cross.empty:
        return []
        
    df_cross['month_period'] = df_cross.index.to_period('M')
    
    summary = []
    for p, grp in df_cross.groupby('month_period'):
        last = grp.iloc[-1]
        lbl = p.strftime('%b %Y')
        sp = grp['spread_close']
        sp_pct = grp['spread_pct']
        
        summary.append({
            'month': lbl,
            'trading_days': len(grp),
            'start_date': grp.index.min().strftime('%Y-%m-%d'),
            'end_date': grp.index.max().strftime('%Y-%m-%d'),
            'leg1_expiry': str(last['expiry_date_leg1']),
            'leg2_expiry': str(last['expiry_date_leg2']),
            'close_leg1_raw': round(float(last['close_leg1']), 1),
            'close_leg2_raw': round(float(last['close_leg2']), 1),
            'norm_p1': round(float(last['norm_price_leg1']), 1),
            'norm_p2': round(float(last['norm_price_leg2']), 1),
            'latest_spread': round(float(last['spread_close']), 1),
            'latest_spread_pct': round(float(last['spread_pct']), 2),
            'avg_spread': round(float(sp.mean()), 1),
            'avg_spread_pct': round(float(sp_pct.mean()), 2),
            'max_spread': round(float(sp.max()), 1),
            'min_spread': round(float(sp.min()), 1),
            'inventory': str(last.get('inventory_display', '—'))
        })
    return summary
