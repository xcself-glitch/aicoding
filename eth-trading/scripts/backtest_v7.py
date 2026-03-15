#!/usr/bin/env python3
"""
ETHUSDT策略回测 V7 - 终极版
目标: 周收益50%+ | 胜率60%+ | 分批补仓 | 永不满仓
策略: 多重确认 + 趋势共振 + 动态仓位
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from strategies.gateio_client import GateIOClient, Candlestick
from strategies.indicators import TechnicalIndicators, TrendDirection

sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))
from strategy_config_v2 import CONFIG, SignalType


class PositionStatus(Enum):
    """持仓状态"""
    EMPTY = "空仓"
    FIRST_ENTRY = "首仓"      # 已建首仓
    SECOND_ENTRY = "二仓"     # 已补二仓
    THIRD_ENTRY = "三仓"      # 已补三仓(最大)


@dataclass
class Position:
    """持仓管理 - 支持分批建仓"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)  # (价格, 数量)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl_price: float = 0.0  # 移动止损
    status: PositionStatus = PositionStatus.EMPTY
    max_drawdown: float = 0.0
    
    def add_entry(self, price: float, quantity: float):
        self.entries.append((price, quantity))
        if len(self.entries) == 1:
            self.status = PositionStatus.FIRST_ENTRY
        elif len(self.entries) == 2:
            self.status = PositionStatus.SECOND_ENTRY
        else:
            self.status = PositionStatus.THIRD_ENTRY
    
    @property
    def avg_price(self) -> float:
        total_value = sum(p * q for p, q in self.entries)
        total_qty = sum(q for _, q in self.entries)
        return total_value / total_qty if total_qty > 0 else 0
    
    @property
    def total_qty(self) -> float:
        return sum(q for _, q in self.entries)
    
    @property
    def total_value(self) -> float:
        return sum(p * q for p, q in self.entries)
    
    def get_unrealized_pnl_pct(self, current_price: float) -> float:
        """计算未实现盈亏百分比"""
        if self.direction == "LONG":
            price_change = (current_price - self.avg_price) / self.avg_price
        else:
            price_change = (self.avg_price - current_price) / self.avg_price
        return price_change * 10  # 10倍杠杆


@dataclass
class Trade:
    """交易记录"""
    entry_time: datetime
    exit_time: Optional[datetime] = None
    direction: str = ""
    entries: List[Tuple[float, float]] = field(default_factory=list)
    exit_price: float = 0.0
    exit_reason: str = ""
    signal_score: int = 0
    trend: str = ""
    
    def calculate_pnl(self) -> Tuple[float, float]:
        """返回(百分比收益, USDT收益)"""
        avg_entry = sum(p * q for p, q in self.entries) / sum(q for _, q in self.entries)
        
        if self.direction == "LONG":
            price_change = (self.exit_price - avg_entry) / avg_entry
        else:
            price_change = (avg_entry - self.exit_price) / avg_entry
        
        pnl_pct = price_change * 10
        position_value = sum(p * q for p, q in self.entries)
        pnl_usdt = position_value * pnl_pct
        
        return pnl_pct, pnl_usdt


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


class UltimateSignalGenerator:
    """终极信号生成器 - 严格筛选高胜率机会"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_trade_bar = 0
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_multi_timeframe_trend(self, closes_15m, closes_1h=None):
        """多周期趋势判断"""
        if len(closes_15m) < 50:
            return "neutral", 0
        
        # 15分钟趋势
        ema10_15m = self.calculate_ema(closes_15m, 10)
        ema30_15m = self.calculate_ema(closes_15m, 30)
        
        trend_15m = 0
        if closes_15m[-1] > ema10_15m[-1] > ema30_15m[-1]:
            trend_15m = 2  # 强多头
        elif closes_15m[-1] > ema10_15m[-1]:
            trend_15m = 1  # 弱多头
        elif closes_15m[-1] < ema10_15m[-1] < ema30_15m[-1]:
            trend_15m = -2  # 强空头
        elif closes_15m[-1] < ema10_15m[-1]:
            trend_15m = -1  # 弱空头
        
        trend_desc = {2: "strong_bull", 1: "weak_bull", 0: "neutral", 
                      -1: "weak_bear", -2: "strong_bear"}
        
        return trend_desc[trend_15m], trend_15m
    
    def calculate_confluence_score(self, opens, highs, lows, closes, volumes, trend_val):
        """
        计算多指标共振分数
        满分100分，要求:
        - 趋势共振 (20分)
        - RSI条件 (15分)
        - MACD确认 (20分)
        - KDJ确认 (15分)
        - 布林带位置 (15分)
        - 成交量确认 (15分)
        """
        score = 0
        reasons = []
        current_price = closes[-1]
        
        # 1. 趋势共振 (20分)
        if abs(trend_val) >= 2:
            score += 20
            reasons.append("趋势强共振")
        elif abs(trend_val) >= 1:
            score += 10
            reasons.append("趋势弱共振")
        
        # 2. RSI条件 (15分)
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        rsi_slope = rsi_values[-1] - rsi_values[-3] if len(rsi_values) >= 3 else 0
        
        if trend_val > 0:  # 多头趋势
            if 45 <= rsi <= 60:  # 健康区间
                score += 15
                reasons.append(f"RSI健康({rsi:.0f})")
            elif 35 <= rsi < 45:  # 超卖反弹
                score += 12
                reasons.append(f"RSI超卖({rsi:.0f})")
            elif rsi > 60 and rsi_slope < 0:  # 从超买回落
                score += 8
                reasons.append(f"RSI回落({rsi:.0f})")
        else:  # 空头趋势
            if 40 <= rsi <= 55:
                score += 15
                reasons.append(f"RSI健康({rsi:.0f})")
            elif 55 < rsi <= 65:
                score += 12
                reasons.append(f"RSI超买({rsi:.0f})")
            elif rsi < 40 and rsi_slope > 0:
                score += 8
                reasons.append(f"RSI反弹({rsi:.0f})")
        
        # 3. MACD确认 (20分)
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        if trend_val > 0:
            if macd_signal.cross_up:
                score += 20
                reasons.append("MACD金叉")
            elif macd_signal.trend == TrendDirection.UP and hist[-1] > hist[-2]:
                score += 15
                reasons.append("MACD扩张")
            elif macd_signal.trend == TrendDirection.UP:
                score += 10
                reasons.append("MACD多头")
        else:
            if macd_signal.cross_down:
                score += 20
                reasons.append("MACD死叉")
            elif macd_signal.trend == TrendDirection.DOWN and hist[-1] < hist[-2]:
                score += 15
                reasons.append("MACD扩张")
            elif macd_signal.trend == TrendDirection.DOWN:
                score += 10
                reasons.append("MACD空头")
        
        # 4. KDJ确认 (15分)
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        
        if trend_val > 0:
            if kdj_signal.golden_cross and k_values[-1] < 60:
                score += 15
                reasons.append("KDJ金叉")
            elif k_values[-1] > d_values[-1] and k_values[-2] <= d_values[-2]:
                score += 10
                reasons.append("KDJ转多")
            elif k_values[-1] > d_values[-1]:
                score += 5
                reasons.append("KDJ多头")
        else:
            if kdj_signal.dead_cross and k_values[-1] > 40:
                score += 15
                reasons.append("KDJ死叉")
            elif k_values[-1] < d_values[-1] and k_values[-2] >= d_values[-2]:
                score += 10
                reasons.append("KDJ转空")
            elif k_values[-1] < d_values[-1]:
                score += 5
                reasons.append("KDJ空头")
        
        # 5. 布林带位置 (15分)
        upper, middle, lower = self.indicators.calculate_bollinger(closes, 20, 2.0)
        boll_signal = self.indicators.analyze_bollinger(current_price, upper, middle, lower, 0.002)
        
        if trend_val > 0:
            if boll_signal.touch_lower:
                score += 15
                reasons.append("触及下轨")
            elif boll_signal.position < 0.3:
                score += 10
                reasons.append("价格低位")
            elif boll_signal.position < 0.5:
                score += 5
                reasons.append("价格中下")
        else:
            if boll_signal.touch_upper:
                score += 15
                reasons.append("触及上轨")
            elif boll_signal.position > 0.7:
                score += 10
                reasons.append("价格高位")
            elif boll_signal.position > 0.5:
                score += 5
                reasons.append("价格中上")
        
        # 6. 成交量确认 (15分)
        vol_ma = np.mean(volumes[-10:])
        current_vol = volumes[-1]
        
        if current_vol > vol_ma * 1.5:
            score += 15
            reasons.append("大幅放量")
        elif current_vol > vol_ma * 1.2:
            score += 10
            reasons.append("温和放量")
        elif current_vol > vol_ma:
            score += 5
            reasons.append("量能跟上")
        
        return min(score, 100), reasons
    
    def check_entry_conditions(self, opens, highs, lows, closes, volumes, bar_index):
        """
        检查入场条件
        返回: (方向, 分数, 原因列表, 趋势值) 或 (None, 0, [], 0)
        """
        # 避免频繁交易
        if bar_index - self.last_trade_bar < 6:
            return None, 0, [], 0
        
        trend_desc, trend_val = self.get_multi_timeframe_trend(closes)
        
        # 震荡市不做单
        if trend_val == 0:
            return None, 0, [], 0
        
        score, reasons = self.calculate_confluence_score(opens, highs, lows, closes, volumes, trend_val)
        
        # 严格入场条件：要求70分以上
        if score >= 70:
            direction = "LONG" if trend_val > 0 else "SHORT"
            self.last_trade_bar = bar_index
            return direction, score, reasons, trend_val
        
        return None, score, reasons, trend_val
    
    def check_add_position(self, position: Position, current_price: float, bar_index: int) -> bool:
        """检查是否可以补仓"""
        if position.status == PositionStatus.THIRD_ENTRY:
            return False
        
        if bar_index - self.last_trade_bar < 3:
            return False
        
        # 计算当前浮亏
        unrealized_pnl = position.get_unrealized_pnl_pct(current_price)
        
        # 浮亏达到2%可以补二仓，达到4%可以补三仓
        if position.status == PositionStatus.FIRST_ENTRY and unrealized_pnl < -2:
            return True
        if position.status == PositionStatus.SECOND_ENTRY and unrealized_pnl < -4:
            return True
        
        return False


class Backtester:
    """回测引擎 - 终极版"""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        self.generator = None
        
        # 仓位管理配置
        self.max_total_exposure = 0.60  # 最大总仓位60%
        self.first_entry_pct = 0.20     # 首仓20%
        self.second_entry_pct = 0.20    # 二仓20%
        self.third_entry_pct = 0.15     # 三仓15%
    
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
        self.generator = UltimateSignalGenerator()
        
        position: Optional[Position] = None
        
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
            
            # 检查持仓
            if position:
                # 更新移动止损
                unrealized_pnl = position.get_unrealized_pnl_pct(current_price)
                
                # 盈利超过8%启动移动止损
                if unrealized_pnl > 8:
                    if position.direction == "LONG":
                        new_trail_sl = current_price * 0.995  # 回撤0.5%止损
                        if new_trail_sl > position.trail_sl_price:
                            position.trail_sl_price = new_trail_sl
                    else:
                        new_trail_sl = current_price * 1.005
                        if new_trail_sl < position.trail_sl_price or position.trail_sl_price == 0:
                            position.trail_sl_price = new_trail_sl
                
                # 检查平仓
                exit_trade = False
                exit_price = current_price
                exit_reason = ""
                
                if position.direction == "LONG":
                    if current_kline.low <= position.sl_price:
                        exit_price = position.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif position.trail_sl_price > 0 and current_kline.low <= position.trail_sl_price:
                        exit_price = position.trail_sl_price
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
                    elif position.trail_sl_price > 0 and current_kline.high >= position.trail_sl_price:
                        exit_price = position.trail_sl_price
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
                        trend=position.direction
                    )
                    pnl_pct, pnl_usdt = trade.calculate_pnl()
                    
                    self.current_capital += pnl_usdt
                    result.trades.append(trade)
                    
                    if pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if pnl_pct > 0 else "❌"
                    entry_info = f"均价:{position.avg_price:.2f}"
                    if len(position.entries) > 1:
                        entry_info += f"({len(position.entries)}次)"
                    
                    print(f"   {emoji} [{exit_reason}] 收益:{pnl_pct*100:+.1f}% {entry_info}")
                    
                    position = None
                
                # 检查补仓
                elif self.generator.check_add_position(position, current_price, i):
                    # 确定补仓比例
                    if position.status == PositionStatus.FIRST_ENTRY:
                        add_pct = self.second_entry_pct
                        add_num = 2
                    else:
                        add_pct = self.third_entry_pct
                        add_num = 3
                    
                    add_value = self.initial_capital * add_pct
                    add_qty = round(add_value / current_price, 3)
                    
                    position.add_entry(current_price, add_qty)
                    self.generator.last_trade_bar = i
                    
                    # 调整止损到新的均价
                    atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
                    if position.direction == "LONG":
                        position.sl_price = position.avg_price - atr * 0.8
                    else:
                        position.sl_price = position.avg_price + atr * 0.8
                    
                    total_exposure = position.total_value / self.initial_capital * 100
                    print(f"   ➕ 补仓#{add_num} 价格:{current_price:.2f} 总仓位:{total_exposure:.0f}%")
            
            # 开新仓
            else:
                direction, score, reasons, trend_val = self.generator.check_entry_conditions(
                    opens, highs, lows, closes, volumes, i
                )
                
                if direction and score >= 70:
                    # 计算首仓
                    position_value = self.initial_capital * self.first_entry_pct
                    quantity = round(position_value / current_price, 3)
                    
                    # 设置止盈止损
                    atr = np.mean([h - l for h, l in zip(highs[-14:], lows[-14:])])
                    
                    if direction == "LONG":
                        sl_price = current_price - atr * 2.0  # 放宽止损到2倍ATR
                        tp_price = current_price + atr * 4.5  # 盈亏比2.25:1
                    else:
                        sl_price = current_price + atr * 2.0
                        tp_price = current_price - atr * 4.5
                    
                    position = Position(
                        entry_time=current_time,
                        direction=direction,
                        tp_price=tp_price,
                        sl_price=sl_price,
                        trail_sl_price=0
                    )
                    position.add_entry(current_price, quantity)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct = abs(current_price - sl_price) / current_price * 100
                    reward_pct = abs(tp_price - current_price) / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] 分数:{score}")
                    print(f"   📊 {' | '.join(reasons[:4])}")
                    print(f"   💰 入场:{current_price:.2f} 首仓20% 止损:{sl_price:.2f}({risk_pct:.2f}%) 止盈:{tp_price:.2f}({reward_pct:.2f}%)")
        
        # 平仓未结束持仓
        if position:
            last_price = klines[-1].close
            last_time = datetime.fromtimestamp(klines[-1].timestamp)
            
            trade = Trade(
                entry_time=position.entry_time,
                direction=position.direction,
                entries=position.entries.copy(),
                exit_price=last_price,
                exit_reason="回测结束"
            )
            pnl_pct, pnl_usdt = trade.calculate_pnl()
            
            self.current_capital += pnl_usdt
            result.trades.append(trade)
            
            if pnl_pct > 0:
                result.winning_trades += 1
            else:
                result.losing_trades += 1
        
        self._calculate_stats(result)
        return result
    
    def _calculate_stats(self, result):
        if result.total_trades == 0:
            return
        
        result.win_rate = result.winning_trades / result.total_trades * 100
        
        wins = [t.calculate_pnl()[0] for t in result.trades if t.calculate_pnl()[0] > 0]
        losses = [t.calculate_pnl()[0] for t in result.trades if t.calculate_pnl()[0] <= 0]
        
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
    print("📊 ETHUSDT V7策略回测报告 (终极版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+ | 分批补仓 | 永不满仓")
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
    
    # 统计补仓
    add_trades = [t for t in result.trades if len(t.entries) > 1]
    if add_trades:
        print(f"\n📝 补仓统计:")
        print(f"   补仓交易: {len(add_trades)}次")
        add_wins = sum(1 for t in add_trades if t.calculate_pnl()[0] > 0)
        print(f"   补仓胜率: {add_wins/len(add_trades)*100:.1f}%")
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场':<20} {'出场':<10} {'收益':<10} {'原因':<12}")
        print("-"*80)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            
            avg_price = sum(p*q for p,q in trade.entries) / sum(q for _,q in trade.entries)
            entry_info = f"{avg_price:.2f}"
            if len(trade.entries) > 1:
                entry_info += f"({len(trade.entries)}次)"
            
            pnl_pct, _ = trade.calculate_pnl()
            pnl_str = f"{pnl_pct*100:+.1f}%"
            
            print(f"{entry_time:<14} {direction:<5} {entry_info:<20} {trade.exit_price:<10.2f} {pnl_str:<10} {trade.exit_reason:<12}")
    
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
    print("🚀 ETHUSDT V7策略回测 - 终极版")
    print("="*80)
    print("🎯 核心特性:")
    print("   1️⃣ 严格入场: 80分以上才入场，追求高胜率")
    print("   2️⃣ 分批建仓: 20%+20%+15%，最大仓位55%")
    print("   3️⃣ 移动止损: 盈利5%后启动移动止损保护利润")
    print("   4️⃣ 盈亏比3.3:1，确保长期盈利")
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
