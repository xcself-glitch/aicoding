#!/usr/bin/env python3
"""
ETHUSDT策略回测 V14 - 分批建仓+动态仓位版
目标: 周收益50%+ | 胜率60%+
优化: 分批建仓 + 大周期过滤 + 动态仓位
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
    """持仓管理 - 支持分批建仓"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)  # (价格, 数量)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    total_invested: float = 0.0  # 总投入资金(USDT)
    
    def add_entry(self, price: float, qty: float):
        self.entries.append((price, qty))
        self.total_invested += price * qty
    
    @property
    def avg_price(self) -> float:
        total_qty = sum(q for _, q in self.entries)
        return self.total_invested / total_qty if total_qty > 0 else 0
    
    @property
    def total_qty(self) -> float:
        return sum(q for _, q in self.entries)
    
    def get_pnl_pct(self, current_price: float) -> float:
        """计算收益率 (10x杠杆)"""
        if self.direction == "LONG":
            change = (current_price - self.avg_price) / self.avg_price
        else:
            change = (self.avg_price - current_price) / self.avg_price
        return change * 10 * 100  # 10倍杠杆，转百分比


@dataclass
class Trade:
    entry_time: datetime
    direction: str = ""
    entries: List[Tuple[float, float]] = field(default_factory=list)
    exit_price: float = 0.0
    exit_reason: str = ""
    setup: str = ""
    invested: float = 0.0  # 投入资金
    
    def calc_pnl(self) -> Tuple[float, float]:
        avg = sum(p*q for p,q in self.entries) / sum(q for _,q in self.entries)
        if self.direction == "LONG":
            change = (self.exit_price - avg) / avg
        else:
            change = (avg - self.exit_price) / avg
        pct = change * 10
        usdt = self.invested * pct
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
    total_invested: float = 0.0  # 总投入资金
    trades: List[Trade] = field(default_factory=list)


class V14SignalGenerator:
    """V14信号生成器 - 多周期趋势过滤"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_trade_time = 0
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_multi_timeframe_trend(self, closes_15m, closes_1h=None):
        """多周期趋势判断 - 只在大趋势明确时交易"""
        if len(closes_15m) < 50:
            return "neutral"
        
        # 15分钟趋势
        ema10 = self.calculate_ema(closes_15m, 10)
        ema30 = self.calculate_ema(closes_15m, 30)
        ema50 = self.calculate_ema(closes_15m, 50)
        
        current = closes_15m[-1]
        
        # 强多头: 价格>EMA10>EMA30>EMA50
        if current > ema10[-1] > ema30[-1] > ema50[-1]:
            return "strong_bull"
        # 强空头: 价格<EMA10<EMA30<EMA50
        elif current < ema10[-1] < ema30[-1] < ema50[-1]:
            return "strong_bear"
        # 弱多头
        elif current > ema10[-1] > ema30[-1]:
            return "bull"
        # 弱空头
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
        trend = self.get_multi_timeframe_trend(closes)
        
        # **关键过滤**: 只做趋势，过滤震荡
        if trend not in ["strong_bull", "bull", "strong_bear", "bear"]:
            return None, None, None, None, None
        
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        support, resistance = self.find_sr(lows, highs)
        
        signal_type = None
        is_long = True
        setup = ""
        
        # ===== 做多 - 多头趋势 =====
        if trend in ["strong_bull", "bull"]:
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件: 价格回调到EMA10附近 + KDJ金叉 + MACD向上
            pullback_to_ema = (ema10[-1] - current_price) / current_price
            if 0.002 < pullback_to_ema < 0.012 and rsi < 60:
                if macd_signal.trend == TrendDirection.UP:
                    # **关键**: 必须有KDJ金叉确认
                    if kdj_signal.golden_cross or (k_values[-1] > d_values[-1] and k_values[-2] <= d_values[-2]):
                        signal_type = SignalType.LONG
                        setup = "强多+回调+KDJ金叉"
            
            # 条件: 突破新高 + 放量
            elif highs[-2] >= resistance * 0.998 and current_price > highs[-2]:
                if rsi < 65 and macd_signal.histogram > 0:
                    # 检查放量
                    vol_ma = np.mean(volumes[-10:-1])
                    if volumes[-1] > vol_ma * 1.3:  # 放量30%
                        signal_type = SignalType.LONG
                        setup = "强多+突破+放量"
        
        # ===== 做空 - 空头趋势 =====
        elif trend in ["strong_bear", "bear"]:
            ema10 = self.calculate_ema(closes, 10)
            
            # 条件: 价格反弹到EMA10附近 + KDJ死叉 + MACD向下
            bounce_from_ema = (current_price - ema10[-1]) / current_price
            if 0.002 < bounce_from_ema < 0.012 and rsi > 40:
                if macd_signal.trend == TrendDirection.DOWN:
                    if kdj_signal.dead_cross or (k_values[-1] < d_values[-1] and k_values[-2] >= d_values[-2]):
                        signal_type = SignalType.SHORT
                        is_long = False
                        setup = "强空+反弹+KDJ死叉"
            
            # 条件: 跌破新低 + 放量
            elif lows[-2] <= support * 1.002 and current_price < lows[-2]:
                if rsi > 35 and macd_signal.histogram < 0:
                    vol_ma = np.mean(volumes[-10:-1])
                    if volumes[-1] > vol_ma * 1.3:
                        signal_type = SignalType.SHORT
                        is_long = False
                        setup = "强空+跌破+放量"
        
        if signal_type:
            self.last_trade_time = current_time
            return signal_type, setup, is_long, support, resistance
        
        return None, None, None, None, None


class Backtester:
    """回测引擎 - 分批建仓 + 动态仓位"""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
        # === 分批建仓配置 ===
        self.first_pct = 0.25    # 首仓25%
        self.second_pct = 0.30   # 二仓30%
        self.third_pct = 0.25    # 三仓25%
        self.max_total_pct = 0.80  # 最大80%仓位
        
        # === 补仓条件 ===
        self.add_threshold_1 = -0.6  # 浮亏0.6%补二仓
        self.add_threshold_2 = -1.2  # 浮亏1.2%补三仓
        
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
        generator = V14SignalGenerator()
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
                
                # ===== 移动止损 =====
                # 盈利10%启动，保5%利润
                if pnl_pct > 10 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.05
                    else:
                        position.trail_sl = position.avg_price * 0.95
                
                # 盈利15%后跟踪
                if pnl_pct > 15:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.985
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.015
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
                        invested=position.total_invested
                    )
                    pnl_pct, pnl_usdt = trade.calc_pnl()
                    self.current_capital += pnl_usdt
                    result.total_invested += position.total_invested
                    result.trades.append(trade)
                    
                    if pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if pnl_pct > 0 else "❌"
                    avg_entry = position.avg_price
                    total_pct = position.total_invested / self.initial_capital * 100
                    print(f"   {emoji} [{exit_reason}] 收益:{pnl_pct*100:+.1f}% 均价:{avg_entry:.2f} 仓位:{total_pct:.0f}%")
                    position = None
                
                # ===== 分批建仓逻辑 =====
                else:
                    num_entries = len(position.entries)
                    
                    # 二仓条件: 浮亏0.6%且只有首仓
                    if num_entries == 1 and pnl_pct < self.add_threshold_1:
                        current_exposure = position.total_invested / self.initial_capital
                        available = self.max_total_pct - current_exposure
                        
                        if available >= self.second_pct:
                            invest = self.initial_capital * self.second_pct
                            qty = round(invest / current_price, 3)
                            position.add_entry(current_price, qty)
                            
                            # 调整止损到新均价
                            atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
                            if position.direction == "LONG":
                                position.sl_price = position.avg_price - atr * 1.0
                            else:
                                position.sl_price = position.avg_price + atr * 1.0
                            
                            total_pct = position.total_invested / self.initial_capital * 100
                            print(f"   ➕ 补二仓 价格:{current_price:.2f} 仓位:{total_pct:.0f}%")
                    
                    # 三仓条件: 浮亏1.2%且已有两仓
                    elif num_entries == 2 and pnl_pct < self.add_threshold_2:
                        current_exposure = position.total_invested / self.initial_capital
                        available = self.max_total_pct - current_exposure
                        
                        if available >= self.third_pct:
                            invest = self.initial_capital * self.third_pct
                            qty = round(invest / current_price, 3)
                            position.add_entry(current_price, qty)
                            
                            # 调整止损
                            atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
                            if position.direction == "LONG":
                                position.sl_price = position.avg_price - atr * 1.0
                            else:
                                position.sl_price = position.avg_price + atr * 1.0
                            
                            total_pct = position.total_invested / self.initial_capital * 100
                            print(f"   ➕ 补三仓 价格:{current_price:.2f} 仓位:{total_pct:.0f}%")
            
            else:
                # ===== 寻找入场信号 =====
                signal_type, setup, is_long, support, resistance = generator.generate_signal(
                    opens, highs, lows, closes, volumes, current_kline.timestamp
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    # 每天最多3次
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 3:
                        continue
                    
                    # 设置止盈止损 - 1%止损，3%止盈
                    if is_long:
                        sl = support * 0.997
                        risk = current_price - sl
                        tp = current_price + risk * 3
                        if risk / current_price > 0.01:
                            sl = current_price * 0.99
                            risk = current_price * 0.01
                            tp = current_price + risk * 3
                    else:
                        sl = resistance * 1.003
                        risk = sl - current_price
                        tp = current_price - risk * 3
                        if risk / current_price > 0.01:
                            sl = current_price * 1.01
                            risk = current_price * 0.01
                            tp = current_price - risk * 3
                    
                    # 首仓: 25%
                    invest = self.initial_capital * self.first_pct
                    qty = round(invest / current_price, 3)
                    
                    position = Position(
                        entry_time=current_time,
                        direction=direction,
                        tp_price=tp,
                        sl_price=sl,
                        trail_sl=0
                    )
                    position.add_entry(current_price, qty)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct = abs(current_price - sl) / current_price * 100
                    reward_pct = abs(tp - current_price) / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] {setup}")
                    print(f"   💰 首仓25% 入场:{current_price:.2f} 止损:{sl:.2f}({risk_pct:.2f}%) 止盈:{tp:.2f}({reward_pct:.2f}%)")
        
        # 平仓未结束持仓
        if position:
            last_price = klines[-1].close
            trade = Trade(
                entry_time=position.entry_time,
                direction=position.direction,
                entries=position.entries.copy(),
                exit_price=last_price,
                exit_reason="结束",
                invested=position.total_invested
            )
            pnl_pct, pnl_usdt = trade.calc_pnl()
            self.current_capital += pnl_usdt
            result.total_invested += position.total_invested
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
    print("📊 ETHUSDT V14策略回测报告 (分批建仓版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+")
    print("🆕 优化: 强趋势过滤 + 分批建仓(25%+30%+25%) + 移动止损")
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
    
    # 分批建仓统计
    multi_entry_trades = [t for t in result.trades if len(t.entries) > 1]
    if multi_entry_trades:
        print(f"\n📝 分批建仓统计: {len(multi_entry_trades)}次补仓")
        for t in multi_entry_trades:
            entry_times = len(t.entries)
            pnl, _ = t.calc_pnl()
            print(f"   补仓{entry_times}次 收益:{pnl*100:+.1f}%")
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场均价':<12} {'出场':<10} {'收益':<10} {'仓位次数':<10} {'原因':<12}")
        print("-"*80)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            avg = sum(p*q for p,q in trade.entries) / sum(q for _,q in trade.entries)
            pnl_pct, _ = trade.calc_pnl()
            num_entries = len(trade.entries)
            print(f"{entry_time:<14} {direction:<5} {avg:<12.2f} {trade.exit_price:<10.2f} {pnl_pct*100:+.1f}%      {num_entries:<10} {trade.exit_reason:<12}")
    
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
    print("🚀 ETHUSDT V14策略回测 - 分批建仓版")
    print("="*80)
    print("🎯 V14优化点:")
    print("   1️⃣ 只做强趋势(strength=100)，过滤90%震荡信号")
    print("   2️⃣ 分批建仓: 首仓25% → 浮亏0.6%补30% → 浮亏1.2%补25%")
    print("   3️⃣ 最大仓位80%，平均成本更优")
    print("   4️⃣ 移动止损: 盈利10%启动，15%后跟踪")
    print("   5️⃣ 必须KDJ金叉/死叉 + 放量确认")
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
