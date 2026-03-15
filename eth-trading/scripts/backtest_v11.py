#!/usr/bin/env python3
"""
ETHUSDT策略回测 V11 - 趋势强化版
目标: 周收益50%+ | 胜率60%+
优化: 趋势强度过滤 + 成交量确认 + 优化盈亏比
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
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
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    entry_count: int = 0
    
    def add_entry(self, price: float, qty: float):
        self.entries.append((price, qty))
        self.entry_count += 1
    
    @property
    def avg_price(self) -> float:
        total = sum(p * q for p, q in self.entries)
        qty = sum(q for _, q in self.entries)
        return total / qty if qty > 0 else 0
    
    @property
    def total_value(self) -> float:
        return sum(p * q for p, q in self.entries)


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime] = None
    direction: str = ""
    entries: List[Tuple[float, float]] = field(default_factory=list)
    exit_price: float = 0.0
    exit_reason: str = ""
    setup: str = ""
    trend_strength: int = 0
    
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


class V11SignalGenerator:
    """V11信号生成器 - 强化趋势过滤"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_trade_time = 0
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_trend_strength(self, closes, highs, lows):
        """
        计算趋势强度 (0-100)
        综合EMA排列、价格位置、斜率
        """
        if len(closes) < 50:
            return 0, "neutral"
        
        ema10 = self.calculate_ema(closes, 10)
        ema30 = self.calculate_ema(closes, 30)
        ema50 = self.calculate_ema(closes, 50)
        
        current = closes[-1]
        
        # 多头强度计算
        bull_score = 0
        if current > ema10[-1] > ema30[-1] > ema50[-1]:
            bull_score += 40  # 完美多头排列
        elif current > ema10[-1] > ema30[-1]:
            bull_score += 30
        elif current > ema10[-1]:
            bull_score += 15
        
        # 价格在EMA10上方距离
        if current > ema10[-1]:
            distance = (current - ema10[-1]) / ema10[-1] * 100
            if distance < 2:  # 靠近EMA，可能回调
                bull_score += 20
            elif distance < 5:
                bull_score += 10
        
        # 斜率
        ema10_slope = (ema10[-1] - ema10[-5]) / ema10[-5] * 100
        if ema10_slope > 0.5:
            bull_score += 20
        elif ema10_slope > 0:
            bull_score += 10
        
        # 空头强度计算
        bear_score = 0
        if current < ema10[-1] < ema30[-1] < ema50[-1]:
            bear_score += 40
        elif current < ema10[-1] < ema30[-1]:
            bear_score += 30
        elif current < ema10[-1]:
            bear_score += 15
        
        if current < ema10[-1]:
            distance = (ema10[-1] - current) / ema10[-1] * 100
            if distance < 2:
                bear_score += 20
            elif distance < 5:
                bear_score += 10
        
        if ema10_slope < -0.5:
            bear_score += 20
        elif ema10_slope < 0:
            bear_score += 10
        
        if bull_score >= 60:
            return bull_score, "strong_bull"
        elif bull_score >= 40:
            return bull_score, "bull"
        elif bear_score >= 60:
            return bear_score, "strong_bear"
        elif bear_score >= 40:
            return bear_score, "bear"
        
        return max(bull_score, bear_score), "neutral"
    
    def find_support_resistance(self, lows, highs, period=20):
        return min(lows[-period:]), max(highs[-period:])
    
    def check_volume_confirm(self, volumes):
        """成交量确认"""
        if len(volumes) < 10:
            return False
        vol_ma = np.mean(volumes[-10:-1])
        current_vol = volumes[-1]
        return current_vol > vol_ma * 1.2  # 放量20%
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        # 缩短冷却时间到8分钟，增加交易机会
        cooldown_seconds = 8 * 60
        if current_time < self.last_trade_time + cooldown_seconds:
            return None, None, None, None, None, None
        
        current_price = closes[-1]
        trend_strength, trend = self.get_trend_strength(closes, highs, lows)
        
        # 震荡市过滤 - 趋势强度低于30不做
        if trend_strength < 30:
            return None, None, None, None, None, None
        
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        upper, middle, lower = self.indicators.calculate_bollinger(closes, 20, 2.0)
        
        support, resistance = self.find_support_resistance(lows, highs)
        
        volume_confirm = self.check_volume_confirm(volumes)
        
        signal_type = None
        is_long = True
        setup = ""
        score = 0
        
        # ===== 做多条件 =====
        if trend in ["bull", "strong_bull"]:
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件1: EMA回调入场
            pullback_to_ema = (ema10[-1] - current_price) / current_price
            if 0.002 < pullback_to_ema < 0.02 and rsi < 65:
                if macd_signal.trend == TrendDirection.UP:
                    score = 50 + trend_strength // 2
                    if kdj_signal.golden_cross or k_values[-1] > d_values[-1]:
                        score += 15
                        setup = "EMA回调+KDJ"
                    else:
                        setup = "EMA回调"
                    
                    if volume_confirm:
                        score += 10
                        setup += "+放量"
            
            # 条件2: 突破新高
            elif highs[-2] >= resistance * 0.997 and current_price > highs[-2]:
                if rsi < 72 and macd_signal.histogram > 0:
                    score = 60 + trend_strength // 3
                    setup = "突破新高"
                    if volume_confirm:
                        score += 10
                        setup += "+放量"
            
            # 条件3: 布林带下轨反弹
            elif (current_price - lower[-1]) / current_price < 0.01:
                if macd_signal.trend == TrendDirection.UP and trend_strength >= 50:
                    score = 55 + trend_strength // 3
                    setup = "下轨反弹"
            
            if score >= 60:  # 降低门槛到60分
                signal_type = SignalType.LONG
        
        # ===== 做空条件 =====
        elif trend in ["bear", "strong_bear"]:
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件1: EMA反弹入场
            bounce_from_ema = (current_price - ema10[-1]) / current_price
            if 0.002 < bounce_from_ema < 0.02 and rsi > 35:
                if macd_signal.trend == TrendDirection.DOWN:
                    score = 50 + trend_strength // 2
                    if kdj_signal.dead_cross or k_values[-1] < d_values[-1]:
                        score += 15
                        setup = "EMA反弹+KDJ"
                    else:
                        setup = "EMA反弹"
                    
                    if volume_confirm:
                        score += 10
                        setup += "+放量"
            
            # 条件2: 跌破新低
            elif lows[-2] <= support * 1.003 and current_price < lows[-2]:
                if rsi > 28 and macd_signal.histogram < 0:
                    score = 60 + trend_strength // 3
                    setup = "跌破新低"
                    if volume_confirm:
                        score += 10
                        setup += "+放量"
            
            # 条件3: 布林带上轨回落
            elif (upper[-1] - current_price) / current_price < 0.01:
                if macd_signal.trend == TrendDirection.DOWN and trend_strength >= 50:
                    score = 55 + trend_strength // 3
                    setup = "上轨回落"
            
            if score >= 60:
                signal_type = SignalType.SHORT
                is_long = False
        
        if signal_type:
            self.last_trade_time = current_time
            return signal_type, setup, is_long, support, resistance, trend_strength
        
        return None, None, None, None, None, None


class Backtester:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        self.position_pct = 0.80  # 80%仓位
    
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
        generator = V11SignalGenerator()
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
                
                # 移动止损 - 盈利20%才启动，让利润奔跑
                if pnl_pct > 20 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.10  # 保10%利润
                    else:
                        position.trail_sl = position.avg_price * 0.90
                
                # 更新移动止损 - 盈利25%后跟踪
                if pnl_pct > 25:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.985  # 回撤1.5%止损
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.015
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
                signal_type, setup, is_long, support, resistance, trend_strength = generator.generate_signal(
                    opens, highs, lows, closes, volumes, current_kline.timestamp
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    # 每天最多4次
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 4:
                        continue
                    
                    # 止盈止损 - 盈亏比4:1
                    if is_long:
                        sl = support * 0.997
                        risk = current_price - sl
                        tp = current_price + risk * 4  # 4:1盈亏比
                        # 限制止损0.8%
                        if risk / current_price > 0.008:
                            sl = current_price * 0.992
                            risk = current_price * 0.008
                            tp = current_price + risk * 4
                    else:
                        sl = resistance * 1.003
                        risk = sl - current_price
                        tp = current_price - risk * 4
                        if risk / current_price > 0.008:
                            sl = current_price * 1.008
                            risk = current_price * 0.008
                            tp = current_price - risk * 4
                    
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
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] {setup} 趋势强度:{trend_strength}")
                    print(f"   💰 入场:{current_price:.2f} 仓位80% 止损:{sl:.2f}({risk_pct:.2f}%) 止盈:{tp:.2f}({reward_pct:.2f}%)")
        
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
    print("📊 ETHUSDT V11策略回测报告 (趋势强化版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+")
    print("🆕 优化: 趋势强度过滤 + 成交量确认 + 4:1盈亏比")
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
    print("🚀 ETHUSDT V11策略回测 - 趋势强化版")
    print("="*80)
    print("🎯 V11优化点:")
    print("   1️⃣ 趋势强度评分 (0-100)，低于30过滤")
    print("   2️⃣ 成交量确认，放量20%才入场")
    print("   3️⃣ 盈亏比提升到4:1")
    print("   4️⃣ 止损收紧到0.8%")
    print("   5️⃣ 入场门槛降低到60分")
    print("   6️⃣ 每天最多4次交易")
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
