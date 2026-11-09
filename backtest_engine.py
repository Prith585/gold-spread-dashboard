import pandas as pd
import numpy as np
import datetime

class SpreadBacktester:
    def __init__(self, df, initial_capital=500000.0, lot_multiplier=100.0, num_lots=1,
                 cost_per_turn=350.0, slippage_points=1.0, exit_on_roll=True):
        """
        initial_capital: ₹ starting account balance
        lot_multiplier: 100 for GOLD (10g quote = 1000g lot), 10 for GOLDM
        cost_per_turn: ₹ round turn transaction charges per lot
        slippage_points: points deducted on entry and exit
        """
        self.df = df.copy().sort_index()
        self.initial_capital = float(initial_capital)
        self.lot_multiplier = float(lot_multiplier)
        self.num_lots = int(num_lots)
        self.cost_per_turn = float(cost_per_turn) * self.num_lots
        self.slippage_points = float(slippage_points)
        self.exit_on_roll = exit_on_roll

    def run_strategy(self, strategy_type='zscore_mean_reversion', **params):
        """
        Executes backtest according to strategy_type:
          - 'zscore_mean_reversion': entry_z, exit_z, stop_z, direction ('both', 'long_only', 'short_only')
          - 'bollinger_bands': direction ('both', 'long_only', 'short_only')
          - 'basis_carry': low_basis_thresh, target_basis_thresh
          - 'momentum_ema': crossover
        """
        df = self.df
        n = len(df)
        if n < 5:
            return {'error': 'Insufficient data for backtesting'}

        direction = params.get('direction', 'both')
        max_holding_days = params.get('max_holding_days', 30)
        point_stop_loss = params.get('point_stop_loss', None)
        point_take_profit = params.get('point_take_profit', None)

        # Extract relevant series safely
        dates = df.index
        spread_close = np.asarray(df['spread_close'])
        spread_open = np.asarray(df['spread_open']) if 'spread_open' in df else spread_close
        zscores = np.asarray(df['zscore']) if 'zscore' in df else np.zeros(n)
        bb_upper = np.asarray(df['bb_upper']) if 'bb_upper' in df else spread_close
        bb_lower = np.asarray(df['bb_lower']) if 'bb_lower' in df else spread_close
        smas = np.asarray(df['sma']) if 'sma' in df else spread_close
        basis = np.asarray(df['annualized_basis_pct']) if 'annualized_basis_pct' in df else np.zeros(n)
        roll_events = np.asarray(df['roll_event']) if 'roll_event' in df else np.zeros(n, dtype=bool)
        leg1_exps = np.asarray(df['leg1_expiry']) if 'leg1_expiry' in df else np.array([''] * n)
        leg2_exps = np.asarray(df['leg2_expiry']) if 'leg2_expiry' in df else np.array([''] * n)
        ema_fast_arr = np.asarray(df['ema_fast']) if 'ema_fast' in df else spread_close
        ema_slow_arr = np.asarray(df['ema_slow']) if 'ema_slow' in df else spread_close

        trades = []
        in_position = False
        pos_dir = 0  # +1: Long Spread (Buy Far, Sell Near), -1: Short Spread (Sell Far, Buy Near)
        entry_idx = 0
        entry_price = 0.0
        entry_date = None
        entry_z = 0.0

        daily_equity = np.zeros(n)
        daily_cash = np.zeros(n)
        daily_position = np.zeros(n)
        current_equity = self.initial_capital
        cash = self.initial_capital

        # Parameters for specific strategies
        z_entry_thresh = float(params['entry_z']) if params.get('entry_z') is not None else 1.8
        z_exit_thresh = float(params['exit_z']) if params.get('exit_z') is not None else 0.0
        z_stop_thresh = float(params['stop_z']) if params.get('stop_z') is not None else None
        low_basis = float(params['low_basis']) if params.get('low_basis') is not None else 7.0
        target_basis = float(params['target_basis']) if params.get('target_basis') is not None else 11.0

        for i in range(n):
            curr_date = dates[i]
            curr_spread = spread_close[i]
            curr_z = zscores[i]
            is_roll = bool(roll_events[i]) if self.exit_on_roll else False

            # Check exits first if in position
            if in_position:
                exit_signal = False
                exit_reason = ""
                holding_days = (curr_date - entry_date).days

                # 1. Roll event exit
                if is_roll:
                    exit_signal = True
                    exit_reason = "Contract Roll Exit"
                # 2. Max holding days
                elif max_holding_days and holding_days >= max_holding_days:
                    exit_signal = True
                    exit_reason = f"Max Duration ({holding_days}d)"
                # 3. Strategy specific exits
                elif strategy_type == 'zscore_mean_reversion':
                    if pos_dir == 1:  # Long spread
                        if curr_z >= z_exit_thresh:
                            exit_signal = True
                            exit_reason = "Mean Reversion Target"
                        elif z_stop_thresh and curr_z <= -z_stop_thresh:
                            exit_signal = True
                            exit_reason = f"Z-Score Stop Loss ({curr_z:.2f})"
                    elif pos_dir == -1:  # Short spread
                        if curr_z <= z_exit_thresh:
                            exit_signal = True
                            exit_reason = "Mean Reversion Target"
                        elif z_stop_thresh and curr_z >= z_stop_thresh:
                            exit_signal = True
                            exit_reason = f"Z-Score Stop Loss ({curr_z:.2f})"

                elif strategy_type == 'bollinger_bands':
                    if pos_dir == 1 and curr_spread >= smas[i]:
                        exit_signal = True
                        exit_reason = "Bollinger Mid-SMA Target"
                    elif pos_dir == -1 and curr_spread <= smas[i]:
                        exit_signal = True
                        exit_reason = "Bollinger Mid-SMA Target"

                elif strategy_type == 'basis_carry':
                    if pos_dir == 1 and basis[i] >= target_basis:
                        exit_signal = True
                        exit_reason = "Target Basis Reached"
                    elif pos_dir == -1 and basis[i] <= low_basis:
                        exit_signal = True
                        exit_reason = "Basis Normalization"

                elif strategy_type == 'momentum_ema':
                    ema_fast = ema_fast_arr[i]
                    ema_slow = ema_slow_arr[i]
                    if pos_dir == 1 and ema_fast < ema_slow:
                        exit_signal = True
                        exit_reason = "EMA Bearish Cross"
                    elif pos_dir == -1 and ema_fast > ema_slow:
                        exit_signal = True
                        exit_reason = "EMA Bullish Cross"

                # Check fixed point stop loss / take profit
                if in_position and not exit_signal:
                    points_pnl = (curr_spread - entry_price) * pos_dir
                    if point_stop_loss and points_pnl <= -point_stop_loss:
                        exit_signal = True
                        exit_reason = f"Point Stop Loss (-{point_stop_loss} pts)"
                    elif point_take_profit and points_pnl >= point_take_profit:
                        exit_signal = True
                        exit_reason = f"Take Profit (+{point_take_profit} pts)"

                # Execute Exit
                if exit_signal:
                    # Apply slippage on exit
                    exit_price = curr_spread - (self.slippage_points * pos_dir)
                    points_diff = (exit_price - entry_price) * pos_dir
                    gross_pnl = points_diff * self.lot_multiplier * self.num_lots
                    net_pnl = gross_pnl - self.cost_per_turn
                    current_equity += net_pnl

                    trades.append({
                        'trade_no': len(trades) + 1,
                        'direction': 'LONG SPREAD' if pos_dir == 1 else 'SHORT SPREAD',
                        'entry_date': entry_date.strftime('%Y-%m-%d'),
                        'exit_date': curr_date.strftime('%Y-%m-%d'),
                        'holding_days': holding_days,
                        'entry_price': round(entry_price, 2),
                        'exit_price': round(exit_price, 2),
                        'entry_z': round(entry_z, 2),
                        'exit_z': round(curr_z, 2),
                        'leg1_expiry': str(leg1_exps[i]),
                        'leg2_expiry': str(leg2_exps[i]),
                        'spread_points': round(points_diff, 2),
                        'gross_pnl': round(gross_pnl, 2),
                        'charges': round(self.cost_per_turn, 2),
                        'net_pnl': round(net_pnl, 2),
                        'net_return_pct': round((net_pnl / (self.initial_capital or 1)) * 100, 2),
                        'exit_reason': exit_reason,
                        'cumulative_equity': round(current_equity, 2)
                    })

                    in_position = False
                    pos_dir = 0

            # Check entries if flat and not a roll day
            if not in_position and not is_roll and i < n - 1:
                enter_long = False
                enter_short = False

                if strategy_type == 'zscore_mean_reversion':
                    if (direction in ['both', 'long_only']) and curr_z <= -z_entry_thresh:
                        enter_long = True
                    elif (direction in ['both', 'short_only']) and curr_z >= z_entry_thresh:
                        enter_short = True

                elif strategy_type == 'bollinger_bands':
                    if (direction in ['both', 'long_only']) and curr_spread <= bb_lower[i]:
                        enter_long = True
                    elif (direction in ['both', 'short_only']) and curr_spread >= bb_upper[i]:
                        enter_short = True

                elif strategy_type == 'basis_carry':
                    if (direction in ['both', 'long_only']) and basis[i] <= low_basis:
                        enter_long = True
                    elif (direction in ['both', 'short_only']) and basis[i] >= target_basis:
                        enter_short = True

                elif strategy_type == 'momentum_ema':
                    if i > 0:
                        if (direction in ['both', 'long_only']) and ema_fast_arr[i-1] <= ema_slow_arr[i-1] and ema_fast_arr[i] > ema_slow_arr[i]:
                            enter_long = True
                        elif (direction in ['both', 'short_only']) and ema_fast_arr[i-1] >= ema_slow_arr[i-1] and ema_fast_arr[i] < ema_slow_arr[i]:
                            enter_short = True

                if enter_long:
                    in_position = True
                    pos_dir = 1
                    entry_idx = i
                    entry_date = curr_date
                    # Apply slippage on entry
                    entry_price = curr_spread + self.slippage_points
                    entry_z = curr_z
                elif enter_short:
                    in_position = True
                    pos_dir = -1
                    entry_idx = i
                    entry_date = curr_date
                    entry_price = curr_spread - self.slippage_points
                    entry_z = curr_z

            # Track MTM daily equity
            if in_position:
                unrealized_points = (curr_spread - entry_price) * pos_dir
                unrealized_pnl = (unrealized_points * self.lot_multiplier * self.num_lots) - (self.cost_per_turn / 2.0)
                daily_equity[i] = current_equity + unrealized_pnl
                daily_position[i] = pos_dir
            else:
                daily_equity[i] = current_equity
                daily_position[i] = 0

        # Close any open trade on last day at market
        if in_position:
            last_date = dates[-1]
            last_spread = spread_close[-1]
            holding_days = (last_date - entry_date).days
            exit_price = last_spread - (self.slippage_points * pos_dir)
            points_diff = (exit_price - entry_price) * pos_dir
            gross_pnl = points_diff * self.lot_multiplier * self.num_lots
            net_pnl = gross_pnl - self.cost_per_turn
            current_equity += net_pnl

            trades.append({
                'trade_no': len(trades) + 1,
                'direction': 'LONG SPREAD' if pos_dir == 1 else 'SHORT SPREAD',
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'exit_date': last_date.strftime('%Y-%m-%d'),
                'holding_days': holding_days,
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'entry_z': round(entry_z, 2),
                'exit_z': round(zscores[-1], 2),
                'leg1_expiry': str(leg1_exps[-1]),
                'leg2_expiry': str(leg2_exps[-1]),
                'spread_points': round(points_diff, 2),
                'gross_pnl': round(gross_pnl, 2),
                'charges': round(self.cost_per_turn, 2),
                'net_pnl': round(net_pnl, 2),
                'net_return_pct': round((net_pnl / (self.initial_capital or 1)) * 100, 2),
                'exit_reason': 'End of Backtest Period',
                'cumulative_equity': round(current_equity, 2)
            })
            daily_equity[-1] = current_equity

        # Compile metrics
        return self._compute_performance_metrics(trades, daily_equity, dates, daily_position)

    def _compute_performance_metrics(self, trades, daily_equity, dates, daily_position):
        net_profits = [t['net_pnl'] for t in trades]
        total_net_pnl = sum(net_profits)
        total_trades = len(trades)
        wins = [p for p in net_profits if p > 0]
        losses = [p for p in net_profits if p < 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        gross_win_sum = sum(wins)
        gross_loss_sum = abs(sum(losses))
        profit_factor = (gross_win_sum / gross_loss_sum) if gross_loss_sum > 0 else (999.0 if gross_win_sum > 0 else 0.0)

        # Drawdown analysis on daily equity
        eq_series = pd.Series(daily_equity, index=dates)
        rolling_max = eq_series.cummax()
        drawdown_val = eq_series - rolling_max
        drawdown_pct = (drawdown_val / rolling_max) * 100
        max_dd_val = float(drawdown_val.min())
        max_dd_pct = float(drawdown_pct.min())

        # Daily returns for Sharpe / Sortino
        daily_ret = eq_series.pct_change().dropna()
        rf_daily = 0.06 / 252.0  # 6% annual risk-free rate
        excess_ret = daily_ret - rf_daily

        std_dev = daily_ret.std()
        sharpe = (excess_ret.mean() / std_dev * np.sqrt(252)) if std_dev > 0 else 0.0

        downside_ret = daily_ret[daily_ret < 0]
        downside_std = downside_ret.std()
        sortino = (excess_ret.mean() / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

        # Holding duration
        durations = [t['holding_days'] for t in trades]
        avg_duration = float(np.mean(durations)) if durations else 0.0

        # Consecutive wins / losses
        max_cons_wins = 0
        max_cons_losses = 0
        cur_w = 0
        cur_l = 0
        for p in net_profits:
            if p > 0:
                cur_w += 1
                cur_l = 0
                max_cons_wins = max(max_cons_wins, cur_w)
            elif p < 0:
                cur_l += 1
                cur_w = 0
                max_cons_losses = max(max_cons_losses, cur_l)

        # Total days & CAGR
        total_days = (dates[-1] - dates[0]).days if len(dates) > 1 else 365
        final_equity = float(daily_equity[-1])
        total_ret_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        years = max(total_days / 365.25, 0.1)
        cagr = ((final_equity / self.initial_capital) ** (1.0 / years) - 1.0) * 100 if final_equity > 0 else -100.0

        exposure_days = np.count_nonzero(daily_position)
        exposure_pct = (exposure_days / len(daily_position) * 100) if len(daily_position) > 0 else 0.0

        equity_curve = [
            {'date': d.strftime('%Y-%m-%d'), 'equity': round(float(e), 2), 'drawdown': round(float(dd), 2)}
            for d, e, dd in zip(dates, daily_equity, drawdown_val)
        ]

        summary = {
            'initial_capital': round(self.initial_capital, 2),
            'final_equity': round(final_equity, 2),
            'total_net_pnl': round(total_net_pnl, 2),
            'total_return_pct': round(total_ret_pct, 2),
            'cagr_pct': round(cagr, 2),
            'max_drawdown': round(max_dd_val, 2),
            'max_drawdown_pct': round(max_dd_pct, 2),
            'sharpe_ratio': round(sharpe, 2),
            'sortino_ratio': round(sortino, 2),
            'profit_factor': round(profit_factor, 2),
            'win_rate_pct': round(win_rate, 2),
            'total_trades': total_trades,
            'win_count': win_count,
            'loss_count': loss_count,
            'avg_trade_pnl': round(float(np.mean(net_profits)), 2) if net_profits else 0.0,
            'avg_win': round(float(np.mean(wins)), 2) if wins else 0.0,
            'avg_loss': round(float(np.mean(losses)), 2) if losses else 0.0,
            'max_win': round(max(wins), 2) if wins else 0.0,
            'max_loss': round(min(losses), 2) if losses else 0.0,
            'max_consecutive_wins': max_cons_wins,
            'max_consecutive_losses': max_cons_losses,
            'avg_holding_days': round(avg_duration, 1),
            'exposure_pct': round(exposure_pct, 1),
            'total_days': total_days
        }

        return {
            'summary': summary,
            'trades': trades,
            'equity_curve': equity_curve
        }
