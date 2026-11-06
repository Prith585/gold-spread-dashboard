"""
Flask Web Application for Gold Spot / Futures Spread Dashboard - Institutional Terminal
"""

import os
import sys
import threading
import time
import io
import csv
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response
from data_engine import engine

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Background worker to keep data fresh
def background_data_refresher():
    """Periodically refreshes MCX futures and All India Bullion spot data in background"""
    while True:
        try:
            # Refresh every 30 seconds
            engine.fetch_ibja_spot(force=False)
            engine.fetch_mcx_futures(force=True)
        except Exception as e:
            print(f"Background refresh error: {e}")
        time.sleep(30)

refresh_thread = threading.Thread(target=background_data_refresher, daemon=True)
refresh_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tunnel', methods=['GET'])
def get_tunnel():
    """Returns currently active Cloudflare public tunnel URL"""
    tunnel_file = os.path.join(os.path.dirname(__file__), 'active_tunnel.txt')
    try:
        if os.path.exists(tunnel_file):
            with open(tunnel_file, 'r') as f:
                url = f.read().strip()
                if url and url.startswith('http'):
                    return jsonify({'success': True, 'url': url})
    except Exception:
        pass
    return jsonify({'success': True, 'url': 'https://organisations-gps-infants-morgan.trycloudflare.com'})

@app.route('/api/data', methods=['GET'])
def get_live_data():
    """Returns current live data with default settings"""
    try:
        force = request.args.get('force', 'false').lower() == 'true'
        purity = request.args.get('purity', 'gold_999')
        custom_spot = request.args.get('custom_spot', None)
        custom_etf = request.args.get('custom_etf', None)
        cost_capital = float(request.args.get('cost_capital', 8.0))
        include_gst = request.args.get('include_gst', 'false').lower() == 'true'
        brokerage = float(request.args.get('brokerage', 20.0))
        expiry_filter = request.args.get('expiry_filter', 'NOV').upper()
        
        if force:
            engine.fetch_ibja_spot(force=True)
            engine.fetch_mcx_futures(force=True)
            engine.fetch_gold_etf(force=True)
            
        custom_spot_val = float(custom_spot) if custom_spot and float(custom_spot) > 0 else None
        custom_etf_val = float(custom_etf) if custom_etf and float(custom_etf) > 0 else None
        
        data = engine.calculate_spreads(
            spot_price=custom_spot_val,
            spot_purity=purity,
            cost_of_capital_pa=cost_capital,
            include_gst=include_gst,
            custom_brokerage=brokerage,
            expiry_filter=expiry_filter,
            custom_etf=custom_etf_val
        )
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/recalculate', methods=['POST'])
def recalculate():
    """Recalculates spreads dynamically with user-provided parameters"""
    try:
        payload = request.get_json(force=True) or {}
        purity = payload.get('purity', 'gold_999')
        custom_spot = payload.get('custom_spot')
        custom_etf = payload.get('custom_etf')
        cost_capital = float(payload.get('cost_capital', 8.0))
        include_gst = bool(payload.get('include_gst', False))
        brokerage = float(payload.get('brokerage', 20.0))
        expiry_filter = payload.get('expiry_filter', 'NOV').upper()
        force = bool(payload.get('force_refresh', False))
        
        if force:
            engine.fetch_ibja_spot(force=True)
            engine.fetch_mcx_futures(force=True)
            engine.fetch_gold_etf(force=True)
            
        custom_spot_val = float(custom_spot) if custom_spot and float(custom_spot) > 0 else None
        custom_etf_val = float(custom_etf) if custom_etf and float(custom_etf) > 0 else None
        
        data = engine.calculate_spreads(
            spot_price=custom_spot_val,
            spot_purity=purity,
            cost_of_capital_pa=cost_capital,
            include_gst=include_gst,
            custom_brokerage=brokerage,
            expiry_filter=expiry_filter,
            custom_etf=custom_etf_val
        )
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar-spreads', methods=['GET'])
def get_calendar_spreads():
    """Returns futures vs futures calendar roll spreads"""
    try:
        futs = engine.fetch_mcx_futures(force=False)
        cal = engine.calculate_calendar_spreads(futs)
        return jsonify({'success': True, 'calendar_spreads': cal})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export-csv', methods=['GET'])
def export_csv():
    """Generates and downloads a clean, institutional CSV report of all spreads"""
    try:
        purity = request.args.get('purity', 'gold_999')
        cost_capital = float(request.args.get('cost_capital', 8.0))
        include_gst = request.args.get('include_gst', 'false').lower() == 'true'
        
        data = engine.calculate_spreads(
            spot_purity=purity,
            cost_of_capital_pa=cost_capital,
            include_gst=include_gst
        )
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow([
            "Gold Arbitrage Terminal - Live MCX vs All India Bullion Report",
            f"Generated: {data['timestamp']}",
            f"Benchmark Spot: Rs {data['spot_with_tax']}/10g ({data['spot_label']})"
        ])
        writer.writerow([])
        writer.writerow([
            "Symbol", "Contract Type", "Expiry", "DTE (Days)", "MCX Futures LTP", 
            "Norm Price (Rs/10g)", "Spot Price (Rs/10g)", "Spread (Rs/10g)", "Spread %",
            "Theoretical Fair Value F*", "Arbitrage Alpha (Mispricing)", "Breakeven Spread (Rs/10g)",
            "Safety Margin (Rs/10g)", "Annualized Gross Yield (% p.a.)", "Annualized Net ROI (% p.a.)",
            "Net Profit per Lot (Rs)", "Volume", "Open Interest", "Strategy", "Liquidity"
        ])
        
        for s in data['spreads']:
            writer.writerow([
                s['symbol'],
                s['contract_desc'],
                s['expiry'],
                s['dte'],
                s['ltp'],
                s['fut_price_10g'],
                s['spot_price_10g'],
                s['spread_10g'],
                f"{s['spread_pct']}%",
                s['fair_value_10g'],
                s['arbitrage_alpha'],
                s['breakeven_spread_10g'],
                s['safety_margin_10g'],
                f"{s['ann_gross_yield']}%",
                f"{s['ann_net_yield']}%",
                s['net_profit_lot'],
                s['volume'],
                s['oi'],
                s['strategy'],
                s['liquidity_tier']
            ])
            
        output.seek(0)
        filename = f"Gold_Arbitrage_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/simulate-trade', methods=['POST'])
def simulate_trade():
    """Detailed trade simulation for a specific contract and lot quantity"""
    try:
        payload = request.get_json(force=True) or {}
        symbol = payload.get('symbol')
        expiry = payload.get('expiry')
        lots = int(payload.get('lots', 1))
        cost_capital = float(payload.get('cost_capital', 8.0))
        custom_spot = payload.get('custom_spot')
        purity = payload.get('purity', 'gold_999')
        include_gst = bool(payload.get('include_gst', False))
        
        custom_spot_val = float(custom_spot) if custom_spot and float(custom_spot) > 0 else None
        data = engine.calculate_spreads(
            spot_price=custom_spot_val,
            spot_purity=purity,
            cost_of_capital_pa=cost_capital,
            include_gst=include_gst
        )
        
        # Find chosen contract
        target = None
        for item in data['spreads']:
            if item['symbol'] == symbol and item['expiry'] == expiry:
                target = item
                break
                
        if not target:
            return jsonify({'success': False, 'error': 'Contract not found'}), 404
            
        # Multiple lots calculations
        total_grams = target['lot_qty_grams'] * lots
        total_10g_units = total_grams / 10.0
        
        spot_price_10g = target['spot_price_10g']
        fut_price_10g = target['fut_price_10g']
        
        total_spot_capital = spot_price_10g * total_10g_units
        total_fut_turnover = fut_price_10g * total_10g_units
        
        # MCX Margin ~ 10-12% for futures
        fut_margin_required = total_fut_turnover * 0.11
        total_outlay = total_spot_capital + fut_margin_required
        
        gross_profit = target['spread_10g'] * total_10g_units
        statutory_fees = target['statutory_charges'] * lots
        financing_interest = total_spot_capital * (cost_capital / 100.0) * (target['dte'] / 365.0)
        net_profit = gross_profit - statutory_fees - financing_interest
        
        roi_absolute = (net_profit / total_spot_capital) * 100.0 if total_spot_capital > 0 else 0
        roi_annualized = roi_absolute * (365.0 / target['dte'])
        
        # Broker Order Generation Specs
        broker_order = {
            'leg1_spot': {
                'action': target['action_spot'],
                'asset': 'Gold Physical / EGR (Electronic Gold Receipt)',
                'quantity_grams': total_grams,
                'rate_per_10g': spot_price_10g,
                'total_amount': total_spot_capital,
                'venue': 'All India Bullion / IBJA Accredited Vault / NSE-BSE EGR'
            },
            'leg2_futures': {
                'action': target['action_fut'],
                'exchange': 'MCX',
                'symbol': target['symbol'],
                'expiry': target['expiry'],
                'lots': lots,
                'order_type': 'LIMIT',
                'limit_price': target['ltp'],
                'margin_approx': fut_margin_required,
                'product': 'NRML (Carry Forward)'
            }
        }
        
        simulation = {
            'symbol': target['symbol'],
            'expiry': target['expiry'],
            'contract_name': target['contract_name'],
            'dte': target['dte'],
            'lots': lots,
            'total_grams': round(total_grams, 2),
            'spot_price_10g': spot_price_10g,
            'fut_price_10g': fut_price_10g,
            'spread_10g': target['spread_10g'],
            'fair_value_10g': target['fair_value_10g'],
            'arbitrage_alpha': target['arbitrage_alpha'],
            'breakeven_spread_10g': target['breakeven_spread_10g'],
            'safety_margin_10g': target['safety_margin_10g'],
            'total_spot_capital': round(total_spot_capital, 2),
            'fut_margin_required': round(fut_margin_required, 2),
            'total_outlay': round(total_outlay, 2),
            'gross_profit': round(gross_profit, 2),
            'statutory_fees': round(statutory_fees, 2),
            'financing_interest': round(financing_interest, 2),
            'net_profit': round(net_profit, 2),
            'roi_absolute_pct': round(roi_absolute, 2),
            'roi_annualized_pct': round(roi_annualized, 2),
            'strategy': target['strategy'],
            'action_spot': target['action_spot'],
            'action_fut': target['action_fut'],
            'broker_order': broker_order
        }
        return jsonify({'success': True, 'simulation': simulation})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5055))
    print(f"[*] Starting Gold Spread Arbitrage Terminal on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
