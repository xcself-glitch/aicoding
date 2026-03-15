#!/usr/bin/env python3
"""
ETHUSDT策略回测 V6 - 专业仓位管理版
核心优化:
1. 分级仓位：信号强度决定仓位大小 (30%-50%-70%-100%)
2. 补仓机制：价格偏离成本价1%后允许补仓
3. 趋势确认：必须与日线趋势同向
4. 动态止盈：根据盈利情况调整止盈点
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
class Position:
    """持仓管理"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)  # (价格, 数量)列表
    tp_price: float = 0.0
    sl_price: float = 0.0
    avg_price: float = 0.0
    total_quantity: float = 0.0
    max_position_value: float = 0.0
    add_count: int = 0  # 补仓次数
    
    def add_entry(self, price: float, quantity: float):
        """添加入场"""
        self.entries.append((price, quantity))
        self._update_avg()
        
    def _update_avg(self):
        """更新均价"""
        total_value = sum(p * q for p, q in self.entries)
        self.total_quantity = sum(q for _, q in self.entries)
        if self.total_quantity > 0:
            self.avg_price = total_value / self.total_quantity


@dataclass
class Trade:
    """交易记录"""
    entry_time: datetime
    exit_time: Optional[datetime] = None
    direction: str = ""
    entries: List[Tuple[float, float]] = field(default_factory=list)  # 所有入场记录
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    pnl_usdt: float = 0.0
    exit_reason: str = ""
    signal_strength: str = ""  # 信号强度
    trend_aligned: bool = False
    
    def calculate_pnl(self):
        """计算盈亏"""
        total_value = sum(p * q for p, q in self.entries)
        total_qty = sum(q for _, q in self.entries)
        avg_entry = total_value / total_qty if total_qty > 0 else 0
        
        if self.direction == "LONG":
            price_change = (self.exit_price - avg_entry) / avg_entry
        else:
            price_change = (avg_entry - self.exit_price) / avg_entry
        
        self.pnl_pct = price_change * 10  # 10倍杠杆
        self.pnl_usdt = total_value * self.pnl_pct


@dataclass
class BacktestResult:
    """回测结果"""
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


class ProfessionalSignalGenerator:
    """专业信号生成器 - 含仓位管理和补仓逻辑"""
    
    def __init__(self, max_capital: float = 10000.0):
        self.indicators = TechnicalIndicators()
        self.max_capital = max_capital
        self.max_single_position = max_capital * 0.4  # 单次最大40%
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_daily_trend(self, closes):
        """判断日线趋势"""
        if len(closes) < 50:
            return "neutral"
        
        ema20 = self.calculate_ema(closes, 20)
        ema50 = self.calculate_ema(closes, 50)
        
        # 趋势强度
        trend_strength = (ema20[-1] - ema50[-1]) / ema50[-1]
        
        if trend_strength > 0.002:
            return "strong_bull"
        elif trend_strength > 0:
            return "weak_bull"
        elif trend_strength < -0.002:
            return "strong_bear"
        elif trend_strength < 0:
            return "weak_bear"
        return "neutral"
    
    def calculate_signal_score(self, opens, highs, lows, closes, volumes, trend):
        """计算信号分数 0-100"""
        score = 0
        reasons = []
        
        current_price = closes[-1]
        
        # RSI评分
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        if trend in ["strong_bull", "weak_bull"]:
            # 多头趋势，RSI在40-60区间较好
            if 40 <= rsi <= 60:
                score += 25
                reasons.append(f"RSI健康({rsi:.0f})")
            elif rsi < 40:
                score += 20
                reasons.append(f"RSI超卖({rsi:.0f})")
        else:
            # 空头趋势
            if 40 <= rsi <= 60:
                score += 25
                reasons.append(f"RSI健康({rsi:.0f})")
            elif rsi > 60:
                score += 20
                reasons.append(f"RSI超买({rsi:.0f})")
        
        # MACD评分
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        if trend in ["strong_bull", "weak_bull"]:
            if macd_signal.cross_up:
                score += 25
                reasons.append("MACD金叉")
            elif macd_signal.trend == TrendDirection.UP:
                score += 15
                reasons.append("MACD多头")
        else:
            if macd_signal.cross_down:
                score += 25
                reasons.append("MACD死叉")
            elif macd_signal.trend == TrendDirection.DOWN:
                score += 15
                reasons.append("MACD空头")
        
        # KDJ评分
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        if trend in ["strong_bull", "weak_bull"]:
            if kdj_signal.golden_cross:
                score += 20
                reasons.append("KDJ金叉")
            elif k_values[-1] > d_values[-1]:
                score += 10
                reasons.append("KDJ多头")
        else:
            if kdj_signal.dead_cross:
                score += 20
                reasons.append("KDJ死叉")
            elif k_values[-1] < d_values[-1]:
                score += 10
                reasons.append("KDJ空头")
        
        # 布林带评分
        upper, middle, lower = self.indicators.calculate_bollinger(closes, 20, 2.0)
        boll_signal = self.indicators.analyze_bollinger(current_price, upper, middle, lower, 0.002)
        
        if trend in ["strong_bull", "weak_bull"]:
            if boll_signal.touch_lower:
                score += 20
                reasons.append("触及下轨")
            elif boll_signal.position < 0.3:
                score += 15
                reasons.append("价格低位")
        else:
            if boll_signal.touch_upper:
                score += 20
                reasons.append("触及上轨")
            elif boll_signal.position > 0.7:
                score += 15
                reasons.append("价格高位")
        
        # 成交量确认
        vol_signal = self.indicators.analyze_volume(volumes[-1], volumes, 10, 1.5)
        if vol_signal.is_spike:
            score += 10
            reasons.append("放量确认")
        
        return min(score, 100), reasons
    
    def get_position_size(self, score: int, is_add: bool = False) -> Tuple[float, str]:
        """根据分数决定仓位大小"""
        if is_add:
            # 补仓固定20%
            return 0.20, "补仓20%"
        
        if score >= 85:
            return 0.35, "重仓35%"  # 高分重仓
        elif score >= 70:
            return 0.25, "中仓25%"  # 中分中仓
        elif score >= 55:
            return 0.15, "轻仓15%"  # 低分轻仓
        else:
            return 0, "观望"
    
    def generate_signal(self, opens, highs, lows, closes, volumes, 
                       current_position: Optional[Position] = None) -> Tuple[Optional[str], float, str, int, str]:
        """
        生成交易信号
        返回: (direction, size_pct, setup, score, trend)
        """
        current_price = closes[-1]
        trend = self.get_daily_trend(closes)
        
        # 检查是否允许补仓
        if current_position and current_position.add_count < 2:
            # 计算当前浮亏
            if current_position.direction == "LONG":
                loss_pct = (current_position.avg_price - current_price) / current_position.avg_price
                if loss_pct > 0.008:  # 浮亏超过0.8%允许补仓
                    return "ADD", 0.20, "补仓", 50, trend
            else:
                loss_pct = (current_price - current_position.avg_price) / current_position.avg_price
                if loss_pct > 0.008:
                    return "ADD", 0.20, "补仓", 50, trend
        
        # 计算信号分数
        score, reasons = self.calculate_signal_score(opens, highs, lows, closes, volumes, trend)
        
        # 趋势过滤 - 必须与日线趋势同向
        if trend == "strong_bull":
            # 强势多头，只做多或观望
            if score >= 60:
                size_pct, size_desc = self.get_position_size(score)
                if size_pct > 0:
                    return "LONG", size_pct, f"强势多头|{'|'.join(reasons[:2])}", score, trend
        elif trend == "weak_bull":
            # 弱势多头，谨慎做多
            if score >= 70:  # 需要更高分数
                size_pct, size_desc = self.get_position_size(score)
                if size_pct > 0:
                    return "LONG", size_pct, f"弱势多头|{'|'.join(reasons[:2])}", score, trend
        elif trend == "strong_bear":
            # 强势空头，只做空
            if score >= 60:
                size_pct, size_desc = self.get_position_size(score)
                if size_pct > 0:
                    return "SHORT", size_pct, f"强势空头|{'|'.join(reasons[:2])}", score, trend
        elif trend == "weak_bear":
            # 弱势空头，谨慎做空
            if score >= 70:
                size_pct, size_desc = self.get_position_size(score)
                if size_pct > 0:
                    return "SHORT", size_pct, f"弱势空头|{'|'.join(reasons[:2])}", score, trend
        
        return None, 0, "", score, trend


class Backtester:
    """回测引擎 - 专业版"""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        self.generator = None
        
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
        self.generator = ProfessionalSignalGenerator(self.current_capital)
        
        current_position: Optional[Position] = None
        cooldown_bars = 0
        
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
            
            # 冷却期递减
            if cooldown_bars > 0:
                cooldown_bars -= 1
            
            # 检查持仓
            if current_position:
                # 检查止损止盈
                exit_trade = False
                exit_price = current_price
                exit_reason = ""
                
                if current_position.direction == "LONG":
                    if current_kline.low <= current_position.sl_price:
                        exit_price = current_position.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif current_kline.high >= current_position.tp_price:
                        exit_price = current_position.tp_price
                        exit_reason = "止盈"
                        exit_trade = True
                else:
                    if current_kline.high >= current_position.sl_price:
                        exit_price = current_position.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif current_kline.low <= current_position.tp_price:
                        exit_price = current_position.tp_price
                        exit_reason = "止盈"
                        exit_trade = True
                
                if exit_trade:
                    # 平仓
                    trade = Trade(
                        entry_time=current_position.entry_time,
                        direction=current_position.direction,
                        entries=current_position.entries.copy(),
                        exit_price=exit_price,
                        exit_reason=exit_reason
                    )
                    trade.calculate_pnl()
                    
                    self.current_capital += trade.pnl_usdt
                    result.trades.append(trade)
                    
                    if trade.pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if trade.pnl_pct > 0 else "❌"
                    entry_info = f"均价:{trade.entries[0][0]:.2f}" if len(trade.entries) == 1 else f"均价:{sum(p*q for p,q in trade.entries)/sum(q for _,q in trade.entries):.2f}({len(trade.entries)}次)"
                    print(f"   {emoji} [{exit_reason}] 收益:{trade.pnl_pct:+.2f}% {entry_info}")
                    
                    current_position = None
                    cooldown_bars = 3  # 平仓后冷却3根K线
                else:
                    # 检查是否可以补仓
                    signal, size_pct, setup, score, trend = self.generator.generate_signal(
                        opens, highs, lows, closes, volumes, current_position
                    )
                    
                    if signal == "ADD" and current_position.add_count < 2:
                        # 执行补仓
                        add_value = self.current_capital * size_pct
                        add_qty = round(add_value / current_price, 3)
                        
                        current_position.add_entry(current_price, add_qty)
                        current_position.add_count += 1
                        
                        # 调整止损为新的均价
                        atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
                        if current_position.direction == "LONG":
                            current_position.sl_price = current_position.avg_price - atr * 0.8
                        else:
                            current_position.sl_price = current_position.avg_price + atr * 0.8
                        
                        print(f"   ➕ 补仓 #{current_position.add_count} 价格:{current_price:.2f} 数量:{add_qty}")
            
            # 开新仓
            elif cooldown_bars == 0:
                signal, size_pct, setup, score, trend = self.generator.generate_signal(
                    opens, highs, lows, closes, volumes
                )
                
                if signal in ["LONG", "SHORT"] and size_pct > 0:
                    # 计算仓位
                    position_value = self.current_capital * size_pct
                    quantity = round(position_value / current_price, 3)
                    
                    # 创建持仓
                    atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
                    
                    if signal == "LONG":
                        sl_price = current_price - atr * 1.0  # 1倍ATR止损
                        tp_price = current_price + atr * 2.5  # 2.5倍ATR止盈
                    else:
                        sl_price = current_price + atr * 1.0
                        tp_price = current_price - atr * 2.5
                    
                    current_position = Position(
                        entry_time=current_time,
                        direction=signal,
                        tp_price=tp_price,
                        sl_price=sl_price,
                        max_position_value=position_value
                    )
                    current_position.add_entry(current_price, quantity)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if signal == "LONG" else "🔴"
                    risk_pct = abs(current_price - sl_price) / current_price * 100
                    reward_pct = abs(tp_price - current_price) / current_price * 100
                    
                    trend_emoji = "🚀" if "strong" in trend else "📈" if "bull" in trend else "📉"
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{signal}] {setup}")
                    print(f"   💰 入场:{current_price:.2f} 仓位:{size_pct*100:.0f}% 分数:{score} 趋势:{trend_emoji}{trend}")
                    print(f"   🎯 止损:{sl_price:.2f}({risk_pct:.2f}%) 止盈:{tp_price:.2f}({reward_pct:.2f}%)")
        
        # 平仓未结束持仓
        if current_position:
            last_price = klines[-1].close
            last_time = datetime.fromtimestamp(klines[-1].timestamp)
            
            trade = Trade(
                entry_time=current_position.entry_time,
                direction=current_position.direction,
                entries=current_position.entries.copy(),
                exit_price=last_price,
                exit_reason="回测结束"
            )
            trade.calculate_pnl()
            
            self.current_capital += trade.pnl_usdt
            result.trades.append(trade)
            
            if trade.pnl_pct > 0:
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
    """打印回测报告"""
    print("\n" + "="*80)
    print("📊 ETHUSDT V6策略回测报告 (专业仓位管理版)")
    print("="*80)
    
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
    print(f"   平均盈利: {result.avg_win_pct:+.2f}% | 平均亏损: {result.avg_loss_pct:+.2f}%")
    print(f"   最大回撤: {result.max_drawdown_pct:.2f}%")
    
    # 统计补仓情况
    add_trades = [t for t in result.trades if len(t.entries) > 1]
    if add_trades:
        print(f"\n📝 补仓统计:")
        print(f"   补仓交易: {len(add_trades)}次")
        add_wins = sum(1 for t in add_trades if t.pnl_pct > 0)
        print(f"   补仓胜率: {add_wins/len(add_trades)*100:.1f}%")
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场':<20} {'出场':<10} {'收益':<8} {'原因':<15}")
        print("-"*80)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            
            # 入场信息
            if len(trade.entries) == 1:
                entry_info = f"{trade.entries[0][0]:.2f}"
            else:
                avg_price = sum(p*q for p,q in trade.entries) / sum(q for _,q in trade.entries)
                entry_info = f"{avg_price:.2f}({len(trade.entries)}次)"
            
            pnl_str = f"{trade.pnl_pct:+.2f}%"
            reason_short = trade.exit_reason[:12]
            
            print(f"{entry_time:<14} {direction:<5} {entry_info:<20} {trade.exit_price:<10.2f} {pnl_str:<8} {reason_short:<15}")
    
    print("="*80)
    
    avg_daily = result.total_trades / days
    weekly_est = result.total_return_pct / days * 7
    
    print("\n🎯 目标达成评估:")
    if 1 <= avg_daily <= 3:
        print(f"   ✅ 频率达标: 日均{avg_daily:.1f}次")
    else:
        print(f"   {'⚠️ 频率偏高' if avg_daily > 3 else '⚠️ 频率偏低'}: 日均{avg_daily:.1f}次")
    
    if weekly_est >= 30:
        print(f"   ✅ 收益达标: 估算周收益{weekly_est:.1f}% 🎉")
    elif weekly_est >= 15:
        print(f"   ⚠️ 收益接近: 估算周收益{weekly_est:.1f}% (目标30%+)")
    else:
        print(f"   ❌ 收益偏低: 估算周收益{weekly_est:.1f}%")
    
    if result.win_rate >= 55:
        print(f"   ✅ 胜率达标: {result.win_rate:.1f}%")
    else:
        print(f"   ⚠️ 胜率偏低: {result.win_rate:.1f}% (目标55%+)")


def main():
    print("🚀 ETHUSDT V6策略回测 - 专业仓位管理版")
    print("="*80)
    print("🎯 核心优化:")
    print("   1️⃣ 分级仓位: 信号强度决定仓位(15%-25%-35%)")
    print("   2️⃣ 智能补仓: 浮亏0.8%后允许补仓(最多2次)")
    print("   3️⃣ 趋势对齐: 只与日线趋势同向交易")
    print("   4️⃣ ATR止损: 动态止损止盈")
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
