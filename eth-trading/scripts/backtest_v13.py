#!/usr/bin/env python3
"""
ETHUSDT策略回测 V13 - 综合优化版
综合V4/V10/V11优点，目标: 周收益50%+ | 胜率60%+
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
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    
    def add_entry(self, price: float, qty: float):
        self.entries.append((price, qty))
    
    @property
    def avg_price(self) -> float:
        total = sum(p * q for p, q in self.entries)
        qty = sum(q for _, q in self.entries)
        return total / qty if qty > 0 else 0


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


class V13SignalGenerator:
    """V13信号生成器 - 综合优化"""
    
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
        """判断趋势方向"""
        if len(closes) < 30:
            return "neutral"
        ema10 = self.calculate_ema(closes, 10)
        ema30 = self.calculate_ema(closes, 30)
        if closes[-1] > ema10[-1] > ema30[-1]:
            return "uptrend"
        elif closes[-1] < ema10[-1] < ema30[-1]:
            return "downtrend"
        return "neutral"
    
    def find_sr(self, lows, highs, period=20):
        return min(lows[-period:]), max(highs[-period:])
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        # 10分钟冷却
        if current_time < self.last_trade_time + 10 * 60:
            return None, None, None, None, None
        
        current_price = closes[-1]
        trend = self.get_trend(closes)
        
        # 震荡市过滤
        if trend == "neutral":
            return None, None, None, None, None
        
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        upper, middle, lower = self.indicators.calculate_bollinger(closes, 20, 2.0)
        
        support, resistance = self.find_sr(lows, highs)
        
        signal_type = None
        is_long = True
        setup = ""
        score = 0
        
        # ===== 做多条件 (只在uptrend) =====
        if trend == "uptrend":
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件1: EMA回调 (V4原版)
            pullback_to_ema = (ema10[-1] - current_price) / current_price
            if 0.003 < pullback_to_ema < 0.015 and rsi < 65:
                if macd_signal.trend == TrendDirection.UP:
                    score = 70
                    if kdj_signal.golden_cross or k_values[-1] > d_values[-1]:
                        score = 85
                        setup = "趋势回调+KDJ"
                    else:
                        setup = "趋势回调"
            
            # 条件2: 突破前高
            elif highs[-2] >= resistance * 0.998 and current_price > highs[-2]:
                if rsi < 70 and macd_signal.histogram > 0:
                    score = 75
                    setup = "突破新高"
            
            # 条件3: 布林带下轨反弹
            elif (current_price - lower[-1]) / current_price < 0.008:
                if macd_signal.trend == TrendDirection.UP:
                    score = 70
                    setup = "下轨反弹"
            
            if score >= 65:  # 门槛65分
                signal_type = SignalType.LONG
        
        # ===== 做空条件 (只在downtrend) =====
        elif trend == "downtrend":
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件1: EMA反弹
            bounce_from_ema = (current_price - ema10[-1]) / current_price
            if 0.003 < bounce_from_ema < 0.015 and rsi > 35:
                if macd_signal.trend == TrendDirection.DOWN:
                    score = 70
                    if kdj_signal.dead_cross or k_values[-1] < d_values[-1]:
                        score = 85
                        setup = "趋势反弹+KDJ"
                    else:
                        setup = "趋势反弹"
            
            # 条件2: 跌破新低
            elif lows[-2] <= support * 1.002 and current_price < lows[-2]:
                if rsi > 30 and macd_signal.histogram < 0:
                    score = 75
                    setup = "跌破新低"
            
            # 条件3: 布林带上轨回落
            elif (upper[-1] - current_price) / current_price < 0.008:
                if macd_signal.trend == TrendDirection.DOWN:
                    score = 70
                    setup = "上轨回落"
            
            if score >= 65:
                signal_type = SignalType.SHORT
                is_long = False
        
        if signal_type:
            self.last_trade_time = current_time
            return signal_type, score, setup, is_long, support, resistance
        
        return None, None, None, None, None, None


class Backtester:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        self.position_pct = 0.80
    
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
        generator = V13SignalGenerator()
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
                pnl_pct = ((current_price - position.avg_price) / position.avg_price * 10 * 100) if position.direction == "LONG" else ((position.avg_price - current_price) / position.avg_price * 10 * 100)
                
                # 移动止损 - 盈利12%启动
                if pnl_pct > 12 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.06
                    else:
                        position.trail_sl = position.avg_price * 0.94
                
                if pnl_pct > 18:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.99
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.01
                        if new_sl < position.trail_sl or position.trail_sl == 0:
                            position.trail_sl = new_sl
                
                # 检查平仓
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
                        exit_reason = "移动止损"
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
                        exit_reason = "移动止损"
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
                        exit_reason=exit_reason,
                        setup=""
                    )
                    pnl_pct, pnl_usdt = trade.calc_pnl()
                    self.current_capital += pnl_usdt
                    result.trades.append(trade)
                    
                    if pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if pnl_pct > 0 else "❌"
                    print(f"   {emoji} [{exit_reason}] {pnl_pct*100:+.1f}%")
                    position = None
            
            else:
                signal_result = generator.generate_signal(
                    opens, highs, lows, closes, volumes, current_kline.timestamp
                )
                if signal_result[0] is None:
                    continue
                signal_type, score, setup, is_long, support, resistance = signal_result
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 4:
                        continue
                    
                    # 止盈止损 - 1%止损，3%止盈，3:1盈亏比
                    if is_long:
                        sl = support * 0.996
                        risk = current_price - sl
                        tp = current_price + risk * 3
                        if risk / current_price > 0.01:
                            sl = current_price * 0.99
                            risk = current_price * 0.01
                            tp = current_price + risk * 3
                    else:
                        sl = resistance * 1.004
                        risk = sl - current_price
                        tp = current_price - risk * 3
                        if risk / current_price > 0.01:
                            sl = current_price * 1.01
                            risk = current_price * 0.01
                            tp = current_price - risk * 3
                    
                    position_value = self.current_capital * self.position_pct
                    quantity = round(position_value / current_price, 3)
                    
                    position = Position(
                        entry_time=current_time,
                        direction=direction,
                        tp_price=tp,
                        sl_price=sl,
                        trail_sl=0
                    )
                    position.add_entry(current_price, quantity)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct = abs(current_price - sl) / current_price * 100
                    reward_pct = abs(tp - current_price) / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] {setup} 分数:{score}")
                    print(f"   💰 入场:{current_price:.2f} 仓位80% 止损:{sl:.2f}({risk_pct:.2f}%) 止盈:{tp:.2f}({reward_pct:.2f}%)")
        
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
    print("📊 ETHUSDT V13策略回测报告 (综合优化版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+")
    print("🆕 综合V4+V10+V11优点")
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
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场':<12} {'出场':<10} {'收益':<10} {'原因':<12}")
        print("-"*80)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            pnl_pct, _ = trade.calc_pnl()
            print(f"{entry_time:<14} {direction:<5} {trade.entries[0][0]:<12.2f} {trade.exit_price:<10.2f} {pnl_pct*100:+.1f}%      {trade.exit_reason:<12}")
    
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
    print("🚀 ETHUSDT V13策略回测 - 综合优化版")
    print("="*80)
    print("🎯 V13优化点:")
    print("   1️⃣ V4入场逻辑 (胜率50%基础)")
    print("   2️⃣ 80%仓位 (V10)")
    print("   3️⃣ 移动止损优化 (V11改进)")
    print("   4️⃣ 入场门槛65分，每天最多4次")
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
