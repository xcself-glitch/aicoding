#!/usr/bin/env python3
"""
ETHUSDT策略回测 V16 - 盈利加仓版
策略: 趋势确认后首仓 → 盈利加仓 → 移动止损保护利润
目标: 周收益50%+ | 胜率60%+
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from strategies.gateio_client import GateIOClient
from strategies.indicators import TechnicalIndicators, TrendDirection

sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))
from strategy_config_v2 import SignalType


@dataclass
class Position:
    """持仓管理 - 盈利加仓"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    highest_price: float = 0.0  # 跟踪最高盈利
    added_positions: int = 0  # 已加仓次数
    
    def add_entry(self, price: float, qty: float):
        self.entries.append((price, qty))
    
    @property
    def avg_price(self) -> float:
        total = sum(p * q for p, q in self.entries)
        qty = sum(q for _, q in self.entries)
        return total / qty if qty > 0 else 0
    
    @property
    def total_qty(self) -> float:
        return sum(q for _, q in self.entries)
    
    @property
    def total_invested(self) -> float:
        return sum(p * q for p, q in self.entries)
    
    def get_pnl_pct(self, current_price: float) -> float:
        if self.direction == "LONG":
            change = (current_price - self.avg_price) / self.avg_price
        else:
            change = (self.avg_price - current_price) / self.avg_price
        return change * 10 * 100


@dataclass
class Trade:
    entry_time: datetime
    direction: str = ""
    entries: List[Tuple[float, float]] = field(default_factory=list)
    exit_price: float = 0.0
    exit_reason: str = ""
    setup: str = ""
    
    def calc_pnl(self) -> Tuple[float, float]:
        avg = sum(p*q for p,q in self.entries) / sum(q for _,q in self.entries)
        if self.direction == "LONG":
            change = (self.exit_price - avg) / avg
        else:
            change = (avg - self.exit_price) / avg
        pct = change * 10
        usdt = sum(p*q for p,q in self.entries) * pct
        return pct, usdt


@dataclass
class BacktestResult:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_return_pct: float = 0.0
    total_return_usdt: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    trades: List[Trade] = field(default_factory=list)


class V16SignalGenerator:
    """V16信号生成器 - 多周期趋势确认"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_trade_time = 0
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_trend(self, closes):
        """三EMA趋势判断"""
        if len(closes) < 50:
            return "neutral"
        ema10 = self.calculate_ema(closes, 10)
        ema30 = self.calculate_ema(closes, 30)
        ema50 = self.calculate_ema(closes, 50)
        
        current = closes[-1]
        
        # 强多头: 价格>EMA10>EMA30>EMA50
        if current > ema10[-1] > ema30[-1] > ema50[-1]:
            return "strong_bull"
        # 强空头: 价格<EMA10<EMA30<EMA50
        elif current < ema10[-1] < ema30[-1] < ema50[-1]:
            return "strong_bear"
        # 多头
        elif current > ema10[-1] > ema30[-1]:
            return "bull"
        # 空头
        elif current < ema10[-1] < ema30[-1]:
            return "bear"
        
        return "neutral"
    
    def find_sr(self, lows, highs, period=20):
        return min(lows[-period:]), max(highs[-period:])
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        # 15分钟冷却
        if current_time < self.last_trade_time + 15 * 60:
            return None, None, None, None, None
        
        current_price = closes[-1]
        trend = self.get_trend(closes)
        
        # 过滤震荡
        if trend == "neutral":
            return None, None, None, None, None
        
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        support, resistance = self.find_sr(lows, highs)
        
        signal_type = None
        is_long = True
        setup = ""
        
        # ===== 做多条件 =====
        if trend in ["bull", "strong_bull"]:
            ema10 = self.calculate_ema(closes, 10)
            
            # EMA回调 + KDJ向上 + MACD向上
            pullback = (ema10[-1] - current_price) / current_price
            if 0.005 < pullback < 0.02 and rsi < 75:
                if macd_signal.trend == TrendDirection.UP and k_values[-1] > d_values[-1]:
                    signal_type = SignalType.LONG
                    setup = f"回调+EMA多 ({trend})"
            

        
        # ===== 做空条件 =====
        elif trend in ["bear", "strong_bear"]:
            ema10 = self.calculate_ema(closes, 10)
            
            # EMA反弹 + KDJ向下 + MACD向下
            bounce = (current_price - ema10[-1]) / current_price
            if 0.005 < bounce < 0.02 and rsi > 25:
                if macd_signal.trend == TrendDirection.DOWN and k_values[-1] < d_values[-1]:
                    signal_type = SignalType.SHORT
                    is_long = False
                    setup = f"反弹+EMA空 ({trend})"
            

        
        if signal_type:
            self.last_trade_time = current_time
            return signal_type, setup, is_long, support, resistance
        
        return None, None, None, None, None


class Backtester:
    """回测引擎 - 盈利加仓版"""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
        # === 盈利加仓配置 ===
        self.first_pct = 0.40      # 首仓40%
        self.add_pct_1 = 0.25      # 一加仓25% (盈利5%后)
        self.add_pct_2 = 0.15      # 二加仓15% (盈利10%后)
        self.max_total_pct = 0.80  # 最大80%
        
        # === 加仓条件 ===
        self.add_threshold_1 = 5.0   # 盈利5%加一仓
        self.add_threshold_2 = 10.0  # 盈利10%加二仓
        
    def fetch_historical_data(self, days: int = 7):
        client = GateIOClient()
        limit = days * 24 * 4 + 100
        print(f"📊 获取过去{days}天数据...")
        klines = client.get_futures_candlesticks("ETH_USDT", "15m", limit)
        if not klines or len(klines) < 100:
            return []
        print(f"✅ 获取{len(klines)}根K线")
        return klines
    
    def run_backtest(self, klines):
        result = BacktestResult()
        generator = V16SignalGenerator()
        position: Optional[Position] = None
        daily_trades = {}
        
        for i in range(50, len(klines)):
            current_kline = klines[i]
            current_time = datetime.fromtimestamp(current_kline.timestamp)
            current_price = current_kline.close
            
            hist = klines[max(0, i-100):i+1]
            opens = np.array([k.open for k in hist])
            highs = np.array([k.high for k in hist])
            lows = np.array([k.low for k in hist])
            closes = np.array([k.close for k in hist])
            volumes = np.array([k.volume for k in hist])
            
            self.equity_curve.append((current_time, self.current_capital))
            
            if position:
                pnl_pct = position.get_pnl_pct(current_price)
                
                # 记录最高盈利
                if pnl_pct > position.highest_price:
                    position.highest_price = pnl_pct
                
                # ===== 盈利加仓逻辑 =====
                # 一加仓: 盈利5%且只有首仓
                if position.added_positions == 0 and pnl_pct >= self.add_threshold_1:
                    current_exposure = position.total_invested / self.initial_capital
                    available = self.max_total_pct - current_exposure
                    
                    if available >= self.add_pct_1:
                        invest = self.initial_capital * self.add_pct_1
                        qty = round(invest / current_price, 3)
                        position.add_entry(current_price, qty)
                        position.added_positions = 1
                        
                        new_avg = position.avg_price
                        total_pct = position.total_invested / self.initial_capital * 100
                        print(f"   ➕ 一加仓 (+25%) 价格:{current_price:.2f} 新均价:{new_avg:.2f} 仓位:{total_pct:.0f}%")
                
                # 二加仓: 盈利10%且已加一仓
                elif position.added_positions == 1 and pnl_pct >= self.add_threshold_2:
                    current_exposure = position.total_invested / self.initial_capital
                    available = self.max_total_pct - current_exposure
                    
                    if available >= self.add_pct_2:
                        invest = self.initial_capital * self.add_pct_2
                        qty = round(invest / current_price, 3)
                        position.add_entry(current_price, qty)
                        position.added_positions = 2
                        
                        new_avg = position.avg_price
                        total_pct = position.total_invested / self.initial_capital * 100
                        print(f"   ➕ 二加仓 (+15%) 价格:{current_price:.2f} 新均价:{new_avg:.2f} 仓位:{total_pct:.0f}%")
                
                # ===== 移动止损逻辑 =====
                # 盈利10%启动移动止损
                if pnl_pct > 10 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.05  # 保5%利润
                    else:
                        position.trail_sl = position.avg_price * 0.95
                
                # 盈利15%后，回撤3%止盈
                if pnl_pct > 15:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.97
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.03
                        if new_sl < position.trail_sl or position.trail_sl == 0:
                            position.trail_sl = new_sl
                
                # 盈利25%后，回撤2%止盈
                if pnl_pct > 25:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.98
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.02
                        if new_sl < position.trail_sl or position.trail_sl == 0:
                            position.trail_sl = new_sl
                
                # ===== 检查平仓 =====
                exit_trade = False
                exit_price = current_price
                exit_reason = ""
                
                if position.direction == "LONG":
                    if current_kline.low <= position.sl_price:
                        exit_price = position.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif position.trail_sl > 0 and current_kline.low <= position.trail_sl:
                        exit_price = position.trail_sl
                        exit_reason = "移动止盈"
                        exit_trade = True
                    elif current_kline.high >= position.tp_price:
                        exit_price = position.tp_price
                        exit_reason = "止盈"
                        exit_trade = True
                else:
                    if current_kline.high >= position.sl_price:
                        exit_price = position.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif position.trail_sl > 0 and current_kline.high >= position.trail_sl:
                        exit_price = position.trail_sl
                        exit_reason = "移动止盈"
                        exit_trade = True
                    elif current_kline.low <= position.tp_price:
                        exit_price = position.tp_price
                        exit_reason = "止盈"
                        exit_trade = True
                
                if exit_trade:
                    trade = Trade(
                        entry_time=position.entry_time,
                        direction=position.direction,
                        entries=position.entries.copy(),
                        exit_price=exit_price,
                        exit_reason=exit_reason
                    )
                    pnl_pct, pnl_usdt = trade.calc_pnl()
                    self.current_capital += pnl_usdt
                    result.trades.append(trade)
                    
                    if pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if pnl_pct > 0 else "❌"
                    avg_entry = position.avg_price
                    num_entries = len(position.entries)
                    print(f"   {emoji} [{exit_reason}] 收益:{pnl_pct*100:+.1f}% 均价:{avg_entry:.2f} 加仓{num_entries-1}次")
                    position = None
            
            else:
                signal_type, setup, is_long, support, resistance = generator.generate_signal(
                    opens, highs, lows, closes, volumes, current_kline.timestamp
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 3:
                        continue
                    
                    # 设置止盈止损 - 1%止损，4%止盈
                    if is_long:
                        sl = support * 0.996
                        risk = current_price - sl
                        tp = current_price + risk * 4
                        if risk / current_price > 0.01:
                            sl = current_price * 0.99
                            risk = current_price * 0.01
                            tp = current_price + risk * 4
                    else:
                        sl = resistance * 1.004
                        risk = sl - current_price
                        tp = current_price - risk * 4
                        if risk / current_price > 0.01:
                            sl = current_price * 1.01
                            risk = current_price * 0.01
                            tp = current_price - risk * 4
                    
                    # 首仓: 40%
                    invest = self.initial_capital * self.first_pct
                    qty = round(invest / current_price, 3)
                    
                    position = Position(
                        entry_time=current_time,
                        direction=direction,
                        tp_price=tp,
                        sl_price=sl,
                        trail_sl=0,
                        highest_price=0,
                        added_positions=0
                    )
                    position.add_entry(current_price, qty)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct = abs(current_price - sl) / current_price * 100
                    reward_pct = abs(tp - current_price) / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] {setup}")
                    print(f"   💰 首仓40% 入场:{current_price:.2f} 止损:{sl:.2f}({risk_pct:.2f}%) 止盈:{tp:.2f}({reward_pct:.2f}%)")
                    print(f"   📈 加仓计划: 盈利5%→+25% | 盈利10%→+15% (最大80%)")
        
        if position:
            last_price = klines[-1].close
            trade = Trade(
                entry_time=position.entry_time,
                direction=position.direction,
                entries=position.entries.copy(),
                exit_price=last_price,
                exit_reason="结束"
            )
            pnl_pct, pnl_usdt = trade.calc_pnl()
            self.current_capital += pnl_usdt
            result.trades.append(trade)
            
            if pnl_pct > 0:
                result.winning_trades += 1
            else:
                result.losing_trades += 1
        
        self._calc_stats(result)
        return result
    
    def _calc_stats(self, result):
        if result.total_trades == 0:
            return
        
        result.win_rate = result.winning_trades / result.total_trades * 100
        
        wins = [t.calc_pnl()[0] for t in result.trades if t.calc_pnl()[0] > 0]
        losses = [t.calc_pnl()[0] for t in result.trades if t.calc_pnl()[0] <= 0]
        
        if wins:
            result.avg_win_pct = sum(wins) / len(wins)
        if losses:
            result.avg_loss_pct = sum(losses) / len(losses)
        
        result.total_return_usdt = self.current_capital - self.initial_capital
        result.total_return_pct = result.total_return_usdt / self.initial_capital * 100
        
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0.001
        result.profit_factor = total_wins / total_losses
        
        peak = self.initial_capital
        max_dd = 0
        for _, capital in self.equity_curve:
            if capital > peak:
                peak = capital
            dd = (peak - capital) / peak
            max_dd = max(max_dd, dd)
        result.max_drawdown_pct = max_dd * 100


def print_report(result, initial_capital, days):
    print("\n" + "="*80)
    print("📊 ETHUSDT V16策略回测报告 (盈利加仓版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+")
    print("🆕 策略: 首仓40% → 盈利5%→+25% → 盈利10%→+15%")
    print("-"*80)
    
    print(f"\n💰 资金情况:")
    print(f"   初始: {initial_capital:.2f} USDT | 最终: {initial_capital + result.total_return_usdt:.2f} USDT")
    print(f"   总收益: {result.total_return_usdt:+.2f} USDT ({result.total_return_pct:+.2f}%)")
    daily_return = result.total_return_pct / days
    weekly_return = daily_return * 7
    print(f"   日均: {daily_return:+.2f}% | 估算周收益: {weekly_return:+.2f}%")
    
    print(f"\n📈 交易统计:")
    print(f"   总交易: {result.total_trades}次 (日均{result.total_trades/days:.1f}次)")
    print(f"   盈利: {result.winning_trades}次 | 亏损: {result.losing_trades}次")
    print(f"   胜率: {result.win_rate:.1f}% | 盈亏比: {result.profit_factor:.2f}")
    
    print(f"\n📉 收益统计:")
    print(f"   平均盈利: {result.avg_win_pct*100:+.1f}% | 平均亏损: {result.avg_loss_pct*100:+.1f}%")
    print(f"   最大回撤: {result.max_drawdown_pct:.2f}%")
    
    # 加仓统计
    multi_entry_trades = [t for t in result.trades if len(t.entries) > 1]
    if multi_entry_trades:
        print(f"\n📝 盈利加仓统计: {len(multi_entry_trades)}次成功加仓")
        for t in multi_entry_trades:
            num_adds = len(t.entries) - 1
            pnl, _ = t.calc_pnl()
            entry_prices = [f"{p:.0f}" for p, _ in t.entries]
            print(f"   加仓{num_adds}次 收益:{pnl*100:+.1f}% 入场:{','.join(entry_prices)}")
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场均价':<12} {'出场':<10} {'收益':<10} {'加仓':<8} {'原因':<12}")
        print("-"*80)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            avg = sum(p*q for p,q in trade.entries) / sum(q for _,q in trade.entries)
            pnl_pct, _ = trade.calc_pnl()
            num_adds = len(trade.entries) - 1
            print(f"{entry_time:<14} {direction:<5} {avg:<12.2f} {trade.exit_price:<10.2f} {pnl_pct*100:+.1f}%      {num_adds:<8} {trade.exit_reason:<12}")
    
    print("="*80)
    
    avg_daily = result.total_trades / days
    weekly_est = result.total_return_pct / days * 7
    
    print("\n🎯 目标达成评估:")
    print(f"   频率: 日均{avg_daily:.1f}次")
    
    if weekly_est >= 50:
        print(f"   ✅ 收益达标: 估算周收益{weekly_est:.1f}% 🎉")
    elif weekly_est >= 35:
        print(f"   ⚠️ 收益接近: 估算周收益{weekly_est:.1f}% (目标50%+)")
    else:
        print(f"   ❌ 收益偏低: 估算周收益{weekly_est:.1f}%")
    
    if result.win_rate >= 60:
        print(f"   ✅ 胜率达标: {result.win_rate:.1f}% 🎉")
    elif result.win_rate >= 50:
        print(f"   ⚠️ 胜率接近: {result.win_rate:.1f}% (目标60%+)")
    else:
        print(f"   ❌ 胜率偏低: {result.win_rate:.1f}%")


def main():
    print("🚀 ETHUSDT V16策略回测 - 盈利加仓版")
    print("="*80)
    print("🎯 V16优化点:")
    print("   1️⃣ 盈利加仓: 首仓40% → 盈利5%→+25% → 盈利10%→+15%")
    print("   2️⃣ 只在趋势明确时入场 (EMA10>EMA30 或 EMA10<EMA30)")
    print("   3️⃣ 移动止盈: 盈利10%启动 → 15%回撤3% → 25%回撤2%")
    print("   4️⃣ 最大仓位80%，亏损时只亏首仓40%")
    print("   5️⃣ 盈亏比4:1")
    print("="*80)
    
    days = 7
    initial_capital = 10000.0
    backtester = Backtester(initial_capital)
    
    klines = backtester.fetch_historical_data(days)
    if not klines:
        return
    
    print("\n🔄 开始回测...\n")
    result = backtester.run_backtest(klines)
    
    print_report(result, initial_capital, days)


if __name__ == "__main__":
    main()
