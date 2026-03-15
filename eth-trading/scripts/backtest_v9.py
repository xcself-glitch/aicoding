#!/usr/bin/env python3
"""
ETHUSDT策略回测 V9 - 高仓位优化版
基于V4策略，最大仓位80%，分批建仓
目标: 周收益50%+ | 胜率60%+
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from strategies.gateio_client import GateIOClient, Candlestick
from strategies.indicators import TechnicalIndicators, TrendDirection

sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))
from strategy_config_v2 import CONFIG, SignalType


@dataclass
class Position:
    """持仓管理 - 支持分批建仓"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    entry_count: int = 0
    max_drawdown: float = 0.0
    
    def add_entry(self, price: float, qty: float):
        self.entries.append((price, qty))
        self.entry_count += 1
    
    @property
    def avg_price(self) -> float:
        total = sum(p * q for p, q in self.entries)
        qty = sum(q for _, q in self.entries)
        return total / qty if qty > 0 else 0
    
    @property
    def total_qty(self) -> float:
        return sum(q for _, q in self.entries)
    
    @property
    def total_value(self) -> float:
        return sum(p * q for p, q in self.entries)
    
    def get_pnl_pct(self, current_price: float) -> float:
        if self.direction == "LONG":
            change = (current_price - self.avg_price) / self.avg_price
        else:
            change = (self.avg_price - current_price) / self.avg_price
        return change * 10


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime] = None
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


class V4SignalGenerator:
    """V4信号生成器 - 保持不变"""
    
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
        if len(closes) < 30:
            return "neutral"
        ema10 = self.calculate_ema(closes, 10)
        ema30 = self.calculate_ema(closes, 30)
        if closes[-1] > ema10[-1] > ema30[-1]:
            return "uptrend"
        elif closes[-1] < ema10[-1] < ema30[-1]:
            return "downtrend"
        return "neutral"
    
    def find_support_resistance(self, lows, highs, period=20):
        support = min(lows[-period:])
        resistance = max(highs[-period:])
        return support, resistance
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        cooldown_seconds = 20 * 60
        if current_time < self.last_trade_time + cooldown_seconds:
            return None, None, None, None, None
        
        current_price = closes[-1]
        trend = self.get_trend(closes)
        
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        upper, middle, lower = self.indicators.calculate_bollinger(closes, 20, 2.0)
        
        support, resistance = self.find_support_resistance(lows, highs)
        
        signal_type = None
        is_long = True
        setup = ""
        score = 0
        
        # 做多条件
        if trend == "uptrend":
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件1: EMA回调
            pullback_to_ema = (ema10[-1] - current_price) / current_price
            if 0.003 < pullback_to_ema < 0.015 and rsi < 65:
                if macd_signal.trend == TrendDirection.UP:
                    score = 70
                    if kdj_signal.golden_cross or k_values[-1] > d_values[-1]:
                        score = 85
                        setup = "EMA回调+KDJ金叉"
                    else:
                        setup = "EMA回调"
            
            # 条件2: 突破前高
            elif highs[-2] >= resistance * 0.998 and current_price > highs[-2]:
                if rsi < 70 and macd_signal.histogram > 0:
                    score = 80
                    setup = "突破前高"
            
            # 条件3: 布林带下轨反弹
            elif (current_price - lower[-1]) / current_price < 0.008:
                if macd_signal.trend == TrendDirection.UP:
                    score = 75
                    setup = "下轨反弹"
            
            if score >= 70:
                signal_type = SignalType.LONG
        
        # 做空条件
        elif trend == "downtrend":
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件1: EMA反弹
            bounce_from_ema = (current_price - ema10[-1]) / current_price
            if 0.003 < bounce_from_ema < 0.015 and rsi > 35:
                if macd_signal.trend == TrendDirection.DOWN:
                    score = 70
                    if kdj_signal.dead_cross or k_values[-1] < d_values[-1]:
                        score = 85
                        setup = "EMA反弹+KDJ死叉"
                    else:
                        setup = "EMA反弹"
            
            # 条件2: 跌破前低
            elif lows[-2] <= support * 1.002 and current_price < lows[-2]:
                if rsi > 30 and macd_signal.histogram < 0:
                    score = 80
                    setup = "跌破新低"
            
            # 条件3: 布林带上轨回落
            elif (upper[-1] - current_price) / current_price < 0.008:
                if macd_signal.trend == TrendDirection.DOWN:
                    score = 75
                    setup = "上轨回落"
            
            if score >= 70:
                signal_type = SignalType.SHORT
                is_long = False
        
        if signal_type:
            self.last_trade_time = current_time
            return signal_type, score, setup, is_long, trend
        
        return None, None, None, None, None


class Backtester:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
        # 仓位配置 - 最大80%
        self.first_pct = 0.30   # 首仓30%
        self.second_pct = 0.30  # 二仓30%
        self.third_pct = 0.20   # 三仓20%
        self.max_exposure = 0.80  # 最大80%
    
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
        generator = V4SignalGenerator()
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
                
                # 记录最大回撤
                if pnl_pct < position.max_drawdown:
                    position.max_drawdown = pnl_pct
                
                # 移动止损 - 盈利10%启动
                if pnl_pct > 10 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.03  # 保3%利润
                    else:
                        position.trail_sl = position.avg_price * 0.97
                
                # 更新移动止损 - 盈利15%后跟踪
                if pnl_pct > 15:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.99  # 回撤1%止损
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
                    entry_info = f"均价:{position.avg_price:.2f}"
                    if position.entry_count > 1:
                        entry_info += f"({position.entry_count}次)"
                    max_dd = position.max_drawdown
                    print(f"   {emoji} [{exit_reason}] 收益:{pnl_pct*100:+.1f}% {entry_info} 最大浮亏:{max_dd*100:.1f}%")
                    position = None
                
                # 补仓逻辑
                elif position.entry_count < 3:
                    # 浮亏达到0.8%补仓
                    if pnl_pct < -0.8:
                        current_exposure = position.total_value / self.initial_capital
                        
                        if position.entry_count == 1 and current_exposure < self.max_exposure:
                            add_pct = min(self.second_pct, self.max_exposure - current_exposure)
                        elif position.entry_count == 2 and current_exposure < self.max_exposure:
                            add_pct = min(self.third_pct, self.max_exposure - current_exposure)
                        else:
                            add_pct = 0
                        
                        if add_pct > 0:
                            add_value = self.initial_capital * add_pct
                            add_qty = round(add_value / current_price, 3)
                            position.add_entry(current_price, add_qty)
                            
                            # 调整止损到新均价
                            atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
                            if position.direction == "LONG":
                                position.sl_price = position.avg_price - atr * 1.2
                            else:
                                position.sl_price = position.avg_price + atr * 1.2
                            
                            total_exposure = position.total_value / self.initial_capital
                            print(f"   ➕ 补仓#{position.entry_count} 价格:{current_price:.2f} 总仓位:{total_exposure*100:.0f}%")
            
            else:
                signal_type, score, setup, is_long, trend = generator.generate_signal(
                    opens, highs, lows, closes, volumes, current_kline.timestamp
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    # 每天最多3次
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 3:
                        continue
                    
                    # 设置止盈止损 - 盈亏比3:1
                    if is_long:
                        sl = support * 0.996 if 'support' in locals() else current_price * 0.99
                        risk = current_price - sl
                        tp = current_price + risk * 3
                        # 限制止损1.5%
                        if risk / current_price > 0.015:
                            sl = current_price * 0.985
                            risk = current_price * 0.015
                            tp = current_price + risk * 3
                    else:
                        sl = resistance * 1.004 if 'resistance' in locals() else current_price * 1.015
                        risk = sl - current_price
                        tp = current_price - risk * 3
                        if risk / current_price > 0.015:
                            sl = current_price * 1.015
                            risk = current_price * 0.015
                            tp = current_price - risk * 3
                    
                    # 首仓
                    position_value = self.initial_capital * self.first_pct
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
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] {setup}")
                    print(f"   💰 入场:{current_price:.2f} 首仓30% 止损:{sl:.2f}({risk_pct:.2f}%) 止盈:{tp:.2f}({reward_pct:.2f}%)")
        
        # 平仓未结束持仓
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
    print("📊 ETHUSDT V9策略回测报告 (高仓位版 - 最大80%)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+ | 分批建仓30%+30%+20%")
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
    
    add_trades = [t for t in result.trades if len(t.entries) > 1]
    if add_trades:
        add_wins = sum(1 for t in add_trades if t.calc_pnl()[0] > 0)
        print(f"\n📝 补仓统计: {len(add_trades)}次补仓, 胜率{add_wins/len(add_trades)*100:.1f}%")
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场':<20} {'出场':<10} {'收益':<10} {'原因':<12}")
        print("-"*80)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            avg = sum(p*q for p,q in trade.entries) / sum(q for _,q in trade.entries)
            entry_info = f"{avg:.2f}"
            if len(trade.entries) > 1:
                entry_info += f"({len(trade.entries)}次)"
            pnl_pct, _ = trade.calc_pnl()
            print(f"{entry_time:<14} {direction:<5} {entry_info:<20} {trade.exit_price:<10.2f} {pnl_pct*100:+.1f}%      {trade.exit_reason:<12}")
    
    print("="*80)
    
    avg_daily = result.total_trades / days
    weekly_est = result.total_return_pct / days * 7
    
    print("\n🎯 目标达成评估:")
    print(f"   频率: 日均{avg_daily:.1f}次")
    
    if weekly_est >= 50:
        print(f"   ✅ 收益达标: 估算周收益{weekly_est:.1f}% 🎉")
    elif weekly_est >= 30:
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
    print("🚀 ETHUSDT V9策略回测 - 高仓位版")
    print("="*80)
    print("🎯 核心特性:")
    print("   1️⃣ 基于V4策略(胜率50%，周收益23%)")
    print("   2️⃣ 分批建仓: 30%+30%+20% = 最大80%仓位")
    print("   3️⃣ 补仓条件: 浮亏2%后补仓")
    print("   4️⃣ 移动止损: 盈利10%启动，15%后跟踪")
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
