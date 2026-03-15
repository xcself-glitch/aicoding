#!/usr/bin/env python3
"""
ETHUSDT策略回测 V4 - 趋势跟踪突破版
优化：减少交易次数，只在高概率突破点入场，盈亏比3:1
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
from strategy_config_v2 import CONFIG, SignalType, get_profit_target


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime] = None
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    leverage: int = 10
    tp_price: float = 0.0
    sl_price: float = 0.0
    pnl_pct: float = 0.0
    pnl_usdt: float = 0.0
    exit_reason: str = ""
    setup: str = ""  # 入场形态
    
    def calculate_pnl(self):
        if self.direction == "LONG":
            price_change = (self.exit_price - self.entry_price) / self.entry_price
        else:
            price_change = (self.entry_price - self.exit_price) / self.entry_price
        self.pnl_pct = price_change * self.leverage
        position_value = self.quantity * self.entry_price
        self.pnl_usdt = position_value * self.pnl_pct


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


class BreakoutSignalGenerator:
    """突破信号生成器 - 高胜率策略"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_trend(self, closes):
        """判断趋势 - 简化版"""
        if len(closes) < 30:
            return "neutral"
        
        ema10 = self.calculate_ema(closes, 10)
        ema30 = self.calculate_ema(closes, 30)
        
        # 短期趋势
        if closes[-1] > ema10[-1] > ema30[-1]:
            return "uptrend"
        elif closes[-1] < ema10[-1] < ema30[-1]:
            return "downtrend"
        return "neutral"
    
    def find_support_resistance(self, lows, highs, period=20):
        """找支撑阻力位"""
        recent_lows = lows[-period:]
        recent_highs = highs[-period:]
        return min(recent_lows), max(recent_highs)
    
    def generate_signal(self, opens, highs, lows, closes, volumes):
        """生成突破信号 - 严格筛选"""
        
        current_price = closes[-1]
        trend = self.get_trend(closes)
        
        # 计算指标
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        current_rsi = rsi_values[-1] if len(rsi_values) > 0 else 50
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        upper, middle, lower = self.indicators.calculate_bollinger(closes, 20, 2.0)
        
        # 找支撑阻力
        support, resistance = self.find_support_resistance(lows, highs)
        
        # 计算波动率
        atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
        atr_pct = atr / current_price
        
        long_setup = None
        short_setup = None
        
        # === 做多条件 ===
        if trend == "uptrend":
            # 条件1: 回调到EMA10附近 + RSI未超买
            ema10 = self.calculate_ema(closes, 10)
            near_ema = abs(current_price - ema10[-1]) / current_price < 0.003
            
            if near_ema and current_rsi < 65 and macd_signal.trend == TrendDirection.UP:
                if kdj_signal.golden_cross or k_values[-1] > d_values[-1]:
                    long_setup = "趋势回调入场"
            
            # 条件2: 突破前高
            if highs[-2] >= resistance * 0.998 and current_price > highs[-2]:
                if current_rsi < 70 and macd_signal.histogram > 0:
                    long_setup = "突破新高"
            
            # 条件3: 布林带中轨反弹
            if abs(current_price - middle[-1]) / current_price < 0.002:
                if macd_signal.trend == TrendDirection.UP and current_rsi > 40:
                    long_setup = "中轨反弹"
        
        # === 做空条件 ===
        if trend == "downtrend":
            # 条件1: 反弹到EMA10附近 + RSI未超卖
            ema10 = self.calculate_ema(closes, 10)
            near_ema = abs(current_price - ema10[-1]) / current_price < 0.003
            
            if near_ema and current_rsi > 35 and macd_signal.trend == TrendDirection.DOWN:
                if kdj_signal.dead_cross or k_values[-1] < d_values[-1]:
                    short_setup = "趋势反弹入场"
            
            # 条件2: 跌破前低
            if lows[-2] <= support * 1.002 and current_price < lows[-2]:
                if current_rsi > 30 and macd_signal.histogram < 0:
                    short_setup = "跌破新低"
            
            # 条件3: 布林带中轨回落
            if abs(current_price - middle[-1]) / current_price < 0.002:
                if macd_signal.trend == TrendDirection.DOWN and current_rsi < 60:
                    short_setup = "中轨回落"
        
        # 返回信号
        if long_setup:
            return SignalType.LONG, 80, long_setup, True, trend, support, resistance
        elif short_setup:
            return SignalType.SHORT, 80, short_setup, False, trend, support, resistance
        
        return SignalType.HOLD, 0, "", None, trend, support, resistance


class Backtester:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
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
        generator = BreakoutSignalGenerator()
        
        current_trade = None
        last_trade_time = 0
        cooldown_seconds = 20 * 60  # 20分钟冷却
        daily_trades = {}
        
        for i in range(50, len(klines)):
            current_kline = klines[i]
            current_time = datetime.fromtimestamp(current_kline.timestamp)
            current_price = current_kline.close
            
            hist_klines = klines[max(0, i-100):i+1]
            opens = np.array([k.open for k in hist_klines])
            highs = np.array([k.high for k in hist_klines])
            lows = np.array([k.low for k in hist_klines])
            closes = np.array([k.close for k in hist_klines])
            volumes = np.array([k.volume for k in hist_klines])
            
            self.equity_curve.append((current_time, self.current_capital))
            
            # 平仓
            if current_trade:
                exit_trade = False
                exit_price = current_price
                exit_reason = ""
                
                if current_trade.direction == "LONG":
                    if current_kline.low <= current_trade.sl_price:
                        exit_price = current_trade.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif current_kline.high >= current_trade.tp_price:
                        exit_price = current_trade.tp_price
                        exit_reason = "止盈"
                        exit_trade = True
                else:
                    if current_kline.high >= current_trade.sl_price:
                        exit_price = current_trade.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif current_kline.low <= current_trade.tp_price:
                        exit_price = current_trade.tp_price
                        exit_reason = "止盈"
                        exit_trade = True
                
                if exit_trade:
                    current_trade.exit_time = current_time
                    current_trade.exit_price = exit_price
                    current_trade.exit_reason = exit_reason
                    current_trade.calculate_pnl()
                    
                    self.current_capital += current_trade.pnl_usdt
                    result.trades.append(current_trade)
                    
                    if current_trade.pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if current_trade.pnl_pct > 0 else "❌"
                    print(f"   {emoji} [{exit_reason}] {current_trade.pnl_pct*100:+.2f}%")
                    
                    last_trade_time = current_kline.timestamp
                    current_trade = None
            
            # 开仓
            elif current_kline.timestamp >= last_trade_time + cooldown_seconds:
                signal_type, score, setup, is_long, trend, support, resistance = generator.generate_signal(
                    opens, highs, lows, closes, volumes
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 3:  # 每天最多3次
                        continue
                    
                    # 设置止盈止损 - 盈亏比3:1
                    if is_long:
                        sl = support * 0.996  # 支撑位下方0.4%
                        risk = current_price - sl
                        tp = current_price + risk * 3  # 3倍盈亏比
                    else:
                        sl = resistance * 1.004  # 阻力位上方0.4%
                        risk = sl - current_price
                        tp = current_price - risk * 3
                    
                    # 限制最大止损1%
                    max_sl_pct = 0.01
                    if abs(current_price - sl) / current_price > max_sl_pct:
                        if is_long:
                            sl = current_price * (1 - max_sl_pct)
                        else:
                            sl = current_price * (1 + max_sl_pct)
                        risk = abs(current_price - sl)
                        tp = current_price + risk * 3 if is_long else current_price - risk * 3
                    
                    position_value = min(3000, self.current_capital * 10 * 0.85)  # 提高仓位
                    quantity = round(position_value / current_price, 3)
                    
                    trade = Trade(
                        entry_time=current_time,
                        direction=direction,
                        entry_price=current_price,
                        quantity=quantity,
                        leverage=10,
                        tp_price=tp,
                        sl_price=sl,
                        setup=setup
                    )
                    
                    current_trade = trade
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct = abs(current_price - sl) / current_price * 100
                    reward_pct = abs(tp - current_price) / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] {setup}")
                    print(f"   💰 入场:{current_price:.2f} 止损:{sl:.2f}({risk_pct:.2f}%) 止盈:{tp:.2f}({reward_pct:.2f}%)")
        
        # 平仓未结束
        if current_trade:
            last_price = klines[-1].close
            last_time = datetime.fromtimestamp(klines[-1].timestamp)
            current_trade.exit_time = last_time
            current_trade.exit_price = last_price
            current_trade.exit_reason = "结束"
            current_trade.calculate_pnl()
            self.current_capital += current_trade.pnl_usdt
            result.trades.append(current_trade)
            
            if current_trade.pnl_pct > 0:
                result.winning_trades += 1
            else:
                result.losing_trades += 1
        
        self._calculate_stats(result)
        return result
    
    def _calculate_stats(self, result):
        if result.total_trades == 0:
            return
        
        result.win_rate = result.winning_trades / result.total_trades * 100
        
        wins = [t.pnl_pct for t in result.trades if t.pnl_pct > 0]
        losses = [t.pnl_pct for t in result.trades if t.pnl_pct <= 0]
        
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
    print("\n" + "="*75)
    print("📊 ETHUSDT V4策略回测报告 (趋势突破版)")
    print("="*75)
    
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
    print(f"   平均盈利: {result.avg_win_pct*100:+.2f}% | 平均亏损: {result.avg_loss_pct*100:+.2f}%")
    print(f"   最大回撤: {result.max_drawdown_pct:.2f}%")
    
    if result.trades:
        print(f"\n📋 全部交易:")
        print("-"*75)
        print(f"{'时间':<14} {'方向':<5} {'入场':<9} {'出场':<9} {'收益':<8} {'形态':<15}")
        print("-"*75)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            pnl_str = f"{trade.pnl_pct*100:+.2f}%"
            print(f"{entry_time:<14} {direction:<5} {trade.entry_price:<9.2f} {trade.exit_price:<9.2f} {pnl_str:<8} {trade.setup:<15}")
    
    print("="*75)
    
    avg_daily = result.total_trades / days
    weekly_est = result.total_return_pct / days * 7
    
    print("\n🎯 目标达成评估:")
    if 1 <= avg_daily <= 3:
        print(f"   ✅ 频率达标: 日均{avg_daily:.1f}次")
    else:
        print(f"   {'⚠️ 频率偏高' if avg_daily > 3 else '⚠️ 频率偏低'}: 日均{avg_daily:.1f}次")
    
    if weekly_est >= 30:
        print(f"   ✅ 收益达标: 估算周收益{weekly_est:.1f}%")
    elif weekly_est >= 15:
        print(f"   ⚠️ 收益接近: 估算周收益{weekly_est:.1f}%")
    else:
        print(f"   ❌ 收益偏低: 估算周收益{weekly_est:.1f}%")


def main():
    print("🚀 ETHUSDT V4策略回测 - 趋势突破版")
    print("="*75)
    print("🎯 策略: 趋势跟踪 + 回调入场 + 突破确认")
    print("📌 盈亏比: 3:1 | 每天最多3次 | 20分钟冷却")
    print("="*75)
    
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
