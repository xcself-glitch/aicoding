#!/usr/bin/env python3
"""
ETHUSDT策略回测 V3 - 趋势过滤版
优化：增加EMA趋势判断，避免逆势操作，提高胜率
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
    signal_score: int = 0
    trend: str = ""
    
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
    long_trades: int = 0
    long_wins: int = 0
    short_trades: int = 0
    short_wins: int = 0
    trades: List[Trade] = field(default_factory=list)


class TrendFilteredSignalGenerator:
    """带趋势过滤的信号生成器"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.daily_high = None
        self.daily_low = None
        
    def calculate_ema(self, prices, period):
        """计算EMA"""
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_trend(self, closes):
        """判断趋势方向"""
        if len(closes) < 50:
            return "neutral"
        
        ema20 = self.calculate_ema(closes, 20)
        ema50 = self.calculate_ema(closes, 50)
        
        current_price = closes[-1]
        ema20_current = ema20[-1]
        ema50_current = ema50[-1]
        
        # 强势上涨
        if current_price > ema20_current > ema50_current and ema20_current > ema50[-5]:
            return "strong_up"
        # 弱势上涨
        elif current_price > ema20_current > ema50_current:
            return "weak_up"
        # 强势下跌
        elif current_price < ema20_current < ema50_current and ema20_current < ema50[-5]:
            return "strong_down"
        # 弱势下跌
        elif current_price < ema20_current < ema50_current:
            return "weak_down"
        else:
            return "neutral"
    
    def generate_signal(self, opens, highs, lows, closes, volumes):
        """生成信号 - 带趋势过滤"""
        
        # 计算指标
        rsi_values = self.indicators.calculate_rsi(closes, CONFIG.rsi.period)
        rsi_signal = self.indicators.analyze_rsi(
            closes, rsi_values, CONFIG.rsi.overbought, CONFIG.rsi.oversold
        )
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(
            highs, lows, closes, CONFIG.kdj.k_period, CONFIG.kdj.d_period, CONFIG.kdj.j_period
        )
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(
            closes, CONFIG.macd.fast, CONFIG.macd.slow, CONFIG.macd.signal
        )
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        upper, middle, lower = self.indicators.calculate_bollinger(
            closes, CONFIG.bollinger.period, CONFIG.bollinger.std_dev
        )
        boll_signal = self.indicators.analyze_bollinger(
            closes[-1], upper, middle, lower, CONFIG.bollinger.touch_threshold
        )
        
        vol_signal = self.indicators.analyze_volume(
            volumes[-1], volumes, CONFIG.volume.ma_period, CONFIG.volume.spike_threshold
        )
        
        current_price = closes[-1]
        trend = self.get_trend(closes)
        
        # 计算日内价格位置
        if self.daily_high and self.daily_low:
            price_pos = (current_price - self.daily_low) / (self.daily_high - self.daily_low)
        else:
            price_pos = 0.5
        
        long_score = 0
        long_reasons = []
        
        # RSI评分
        if rsi_signal.is_oversold:
            long_score += 35
            long_reasons.append(f"RSI超卖({rsi_signal.value:.0f})")
        elif rsi_signal.value < 40:
            long_score += 20
            long_reasons.append(f"RSI低({rsi_signal.value:.0f})")
        if rsi_signal.divergence == "bullish":
            long_score += 25
            long_reasons.append("RSI底背离")
            
        # KDJ评分
        if kdj_signal.golden_cross and k_values[-1] < 45:
            long_score += 30
            long_reasons.append("KDJ金叉")
        if kdj_signal.is_oversold:
            long_score += 20
            long_reasons.append("KDJ超卖")
            
        # MACD评分
        if macd_signal.cross_up:
            long_score += 25
            long_reasons.append("MACD金叉")
        elif macd_signal.trend == TrendDirection.UP:
            long_score += 15
            long_reasons.append("MACD多")
            
        # 布林带评分
        if boll_signal.touch_lower:
            long_score += 25
            long_reasons.append("触下轨")
        elif boll_signal.position < 0.25:
            long_score += 15
            long_reasons.append("价低")
            
        # 价格位置评分
        if price_pos <= 0.3:
            long_score += 20
            long_reasons.append(f"低位({price_pos:.0%})")
        elif price_pos <= 0.45:
            long_score += 10
            
        # 趋势加分
        if trend in ["strong_up", "weak_up"]:
            long_score += 10
            long_reasons.append("趋势多")
        elif trend == "neutral":
            long_score += 5
            
        # 成交量
        if vol_signal.is_spike:
            long_score += 10
            long_reasons.append("放量")
            
        # 做空评分
        short_score = 0
        short_reasons = []
        
        if rsi_signal.is_overbought:
            short_score += 35
            short_reasons.append(f"RSI超买({rsi_signal.value:.0f})")
        elif rsi_signal.value > 60:
            short_score += 20
            short_reasons.append(f"RSI高({rsi_signal.value:.0f})")
        if rsi_signal.divergence == "bearish":
            short_score += 25
            short_reasons.append("RSI顶背离")
            
        if kdj_signal.dead_cross and k_values[-1] > 55:
            short_score += 30
            short_reasons.append("KDJ死叉")
        if kdj_signal.is_overbought:
            short_score += 20
            short_reasons.append("KDJ超买")
            
        if macd_signal.cross_down:
            short_score += 25
            short_reasons.append("MACD死叉")
        elif macd_signal.trend == TrendDirection.DOWN:
            short_score += 15
            short_reasons.append("MACD空")
            
        if boll_signal.touch_upper:
            short_score += 25
            short_reasons.append("触上轨")
        elif boll_signal.position > 0.75:
            short_score += 15
            short_reasons.append("价高")
            
        if price_pos >= 0.7:
            short_score += 20
            short_reasons.append(f"高位({price_pos:.0%})")
        elif price_pos >= 0.55:
            short_score += 10
            
        if trend in ["strong_down", "weak_down"]:
            short_score += 10
            short_reasons.append("趋势空")
        elif trend == "neutral":
            short_score += 5
            
        if vol_signal.is_spike:
            short_score += 10
            short_reasons.append("放量")
        
        # 判断信号 - 考虑趋势
        min_score = CONFIG.signal_score.min_score_to_enter  # 45
        
        # 趋势过滤：强趋势时只顺势操作
        if trend == "strong_up":
            # 强势上涨，只做多
            if long_score >= min_score:
                return SignalType.LONG, long_score, " | ".join(long_reasons[:3]), True, trend
        elif trend == "strong_down":
            # 强势下跌，只做空
            if short_score >= min_score:
                return SignalType.SHORT, short_score, " | ".join(short_reasons[:3]), False, trend
        else:
            # 震荡或弱趋势，双向操作但需要更高分数
            if long_score >= min_score + 5 and long_score > short_score:
                return SignalType.LONG, long_score, " | ".join(long_reasons[:3]), True, trend
            elif short_score >= min_score + 5 and short_score > long_score:
                return SignalType.SHORT, short_score, " | ".join(short_reasons[:3]), False, trend
        
        reason = f"多:{long_score}空:{short_score}|{trend[:4]}"
        return SignalType.HOLD, max(long_score, short_score), reason, None, trend


class Backtester:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
    def fetch_historical_data(self, days: int = 7):
        client = GateIOClient()
        limit = days * 24 * 4 + 100
        print(f"📊 获取过去{days}天的数据...")
        klines = client.get_futures_candlesticks("ETH_USDT", "15m", limit)
        
        if not klines or len(klines) < 100:
            print(f"❌ 数据获取失败")
            return []
        
        print(f"✅ 获取{len(klines)}根K线")
        return klines
    
    def run_backtest(self, klines):
        result = BacktestResult()
        generator = TrendFilteredSignalGenerator()
        
        current_trade = None
        last_trade_time = 0
        cooldown_seconds = CONFIG.risk.cooldown_minutes * 60
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
            
            day_lookback = min(96, len(hist_klines))
            day_high = max([k.high for k in hist_klines[-day_lookback:]])
            day_low = min([k.low for k in hist_klines[-day_lookback:]])
            generator.daily_high = day_high
            generator.daily_low = day_low
            
            self.equity_curve.append((current_time, self.current_capital))
            
            # 平仓检查
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
                        if current_trade.direction == "LONG":
                            result.long_wins += 1
                        else:
                            result.short_wins += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if current_trade.pnl_pct > 0 else "❌"
                    print(f"   {emoji} 平仓 [{exit_reason}] {current_trade.pnl_pct:+.2f}%")
                    
                    last_trade_time = current_kline.timestamp
                    current_trade = None
            
            # 开仓检查
            elif current_kline.timestamp >= last_trade_time + cooldown_seconds:
                signal_type, score, reason, is_long, trend = generator.generate_signal(
                    opens, highs, lows, closes, volumes
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > CONFIG.risk.max_daily_trades:
                        continue
                    
                    price_pos = (current_price - day_low) / (day_high - day_low) if day_high != day_low else 0.5
                    profit_cfg = get_profit_target(price_pos, is_long)
                    
                    if is_long:
                        tp = current_price * (1 + profit_cfg['optimal'])
                        sl = current_price * (1 - CONFIG.risk.stop_loss_pct)
                    else:
                        tp = current_price * (1 - profit_cfg['optimal'])
                        sl = current_price * (1 + CONFIG.risk.stop_loss_pct)
                    
                    position_value = min(
                        CONFIG.leverage.max_position_value,
                        self.current_capital * CONFIG.leverage.leverage * 0.8
                    )
                    quantity = round(position_value / current_price, 3)
                    
                    trade = Trade(
                        entry_time=current_time,
                        direction=direction,
                        entry_price=current_price,
                        quantity=quantity,
                        leverage=CONFIG.leverage.leverage,
                        tp_price=tp,
                        sl_price=sl,
                        signal_score=score,
                        trend=trend
                    )
                    
                    current_trade = trade
                    result.total_trades += 1
                    if direction == "LONG":
                        result.long_trades += 1
                    else:
                        result.short_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] 价:{current_price:.2f} 趋势:{trend}")
                    print(f"   📊 分:{score} | {reason}")
                    print(f"   🎯 止盈:{tp:.2f} | 止损:{sl:.2f}")
        
        # 平仓未结束交易
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
    print("📊 ETHUSDT V3策略回测报告 (趋势过滤版)")
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
    
    if result.long_trades > 0:
        long_win_rate = result.long_wins / result.long_trades * 100
        print(f"   做多: {result.long_trades}次 (胜率{long_win_rate:.1f}%)")
    if result.short_trades > 0:
        short_win_rate = result.short_wins / result.short_trades * 100
        print(f"   做空: {result.short_trades}次 (胜率{short_win_rate:.1f}%)")
    
    print(f"\n📉 收益统计:")
    print(f"   平均盈利: {result.avg_win_pct:+.2f}% | 平均亏损: {result.avg_loss_pct:+.2f}%")
    print(f"   最大回撤: {result.max_drawdown_pct:.2f}%")
    
    if result.trades:
        print(f"\n📋 最近10笔交易:")
        print("-"*75)
        print(f"{'时间':<14} {'方向':<5} {'入场':<9} {'出场':<9} {'收益':<8} {'趋势':<10}")
        print("-"*75)
        
        for trade in result.trades[-10:]:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            pnl_str = f"{trade.pnl_pct:+.2f}%"
            trend_short = trade.trend[:8]
            print(f"{entry_time:<14} {direction:<5} {trade.entry_price:<9.2f} {trade.exit_price:<9.2f} {pnl_str:<8} {trend_short:<10}")
    
    print("="*75)
    
    avg_daily = result.total_trades / days
    weekly_est = result.total_return_pct / days * 7
    
    print("\n🎯 目标达成评估:")
    if 1 <= avg_daily <= 3:
        print(f"   ✅ 频率达标: 日均{avg_daily:.1f}次")
    else:
        print(f"   ⚠️ 频率{'偏高' if avg_daily > 3 else '偏低'}: 日均{avg_daily:.1f}次")
    
    if weekly_est >= 30:
        print(f"   ✅ 收益达标: 估算周收益{weekly_est:.1f}%")
    elif weekly_est >= 15:
        print(f"   ⚠️ 收益接近: 估算周收益{weekly_est:.1f}%")
    else:
        print(f"   ❌ 收益偏低: 估算周收益{weekly_est:.1f}%")


def main():
    print("🚀 ETHUSDT V3策略回测 - 趋势过滤优化版")
    print("="*75)
    print(f"📌 配置: 阈值{CONFIG.signal_score.min_score_to_enter} | 止损{CONFIG.risk.stop_loss_pct*100:.1f}% | 止盈1.2-1.8%")
    print("🎯 优化: EMA趋势过滤 + 顺势操作 + 震荡双向")
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
