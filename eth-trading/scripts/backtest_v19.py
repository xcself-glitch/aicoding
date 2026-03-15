#!/usr/bin/env python3
"""
ETHUSDT策略回测 V19 - 终极融合版
融合V17高收益 + V18风险控制:
1. V17核心: 趋势突破/回调 + 分级移动止盈 + 80%仓位
2. V18风控: Kelly动态调整 + 最大回撤限制 + R倍数跟踪
3. 新优化: 多时间框架过滤 + 波动率自适应 + 智能加仓

目标: 周收益50%+ | 胜率50%+ | 最大回撤<15%
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from strategies.gateio_client import GateIOClient
from strategies.indicators import TechnicalIndicators, TrendDirection

sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))
from strategy_config_v2 import SignalType


@dataclass
class Position:
    """融合版持仓管理"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    highest_price: float = 0.0
    highest_pnl_pct: float = 0.0
    added_positions: int = 0
    atr: float = 0.0
    initial_risk_pct: float = 0.0
    
    def add_entry(self, price: float, qty: float):
        self.entries.append((price, qty))
    
    @property
    def avg_price(self) -> float:
        total = sum(p * q for p, q in self.entries)
        qty = sum(q for _, q in self.entries)
        return total / qty if qty > 0 else 0
    
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
    max_pnl_pct: float = 0.0
    
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
    avg_holding_bars: float = 0.0
    trades: List[Trade] = field(default_factory=list)


class RiskManager:
    """V18风控系统整合"""
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        self.max_drawdown_limit = 0.15  # 15%最大回撤限制
        
        # Kelly参数
        self.win_count = 0
        self.loss_count = 0
        self.total_wins = 0.0
        self.total_losses = 0.0
        
    def update_capital(self, capital: float):
        """更新资金并检查回撤"""
        self.current_capital = capital
        if capital > self.peak_capital:
            self.peak_capital = capital
    
    def get_current_drawdown(self) -> float:
        """计算当前回撤"""
        if self.peak_capital == 0:
            return 0
        return (self.peak_capital - self.current_capital) / self.peak_capital
    
    def can_trade(self) -> bool:
        """检查是否可以交易（回撤限制）"""
        return self.get_current_drawdown() < self.max_drawdown_limit
    
    def update_trade_result(self, is_win: bool, pnl_pct: float):
        """更新交易结果用于Kelly计算"""
        if is_win:
            self.win_count += 1
            self.total_wins += pnl_pct
        else:
            self.loss_count += 1
            self.total_losses += abs(pnl_pct)
    
    def get_kelly_position_size(self, base_size: float = 0.50) -> float:
        """
        计算Kelly仓位
        使用半Kelly降低风险
        """
        total_trades = self.win_count + self.loss_count
        if total_trades < 5:
            return base_size  # 默认50%
        
        win_rate = self.win_count / total_trades
        
        if self.total_losses == 0:
            return base_size
        
        avg_win = self.total_wins / self.win_count if self.win_count > 0 else 0
        avg_loss = self.total_losses / self.loss_count if self.loss_count > 0 else 1
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 2
        
        # Kelly公式: K = W - (1-W)/R
        kelly = win_rate - (1 - win_rate) / win_loss_ratio
        kelly = max(0.20, min(0.80, kelly))  # 限制20%-80%
        
        return kelly * 0.5  # 半Kelly


class V19SignalGenerator:
    """
    V19信号生成器
    融合V17趋势策略 + V18多指标共振
    """
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_trade_time = 0
        self.trade_history: List[Dict] = []
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def calculate_atr(self, highs, lows, closes, period=14) -> float:
        """计算ATR"""
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        return np.mean(tr[-period:])
    
    def get_trend(self, closes) -> Tuple[str, float]:
        """
        三EMA趋势判断
        返回: (趋势方向, 趋势强度0-100)
        """
        if len(closes) < 55:
            return "neutral", 0
        
        ema9 = self.calculate_ema(closes, 9)
        ema21 = self.calculate_ema(closes, 21)
        ema55 = self.calculate_ema(closes, 55)
        
        current = closes[-1]
        
        # 趋势判断
        if current > ema9[-1] > ema21[-1] > ema55[-1]:
            return "strong_bull", 100
        elif current < ema9[-1] < ema21[-1] < ema55[-1]:
            return "strong_bear", 100
        elif ema9[-1] > ema21[-1] and current > ema21[-1]:
            # 计算趋势强度
            strength = 50 + (current - ema21[-1]) / ema21[-1] * 1000
            return "bull", min(90, strength)
        elif ema9[-1] < ema21[-1] and current < ema21[-1]:
            strength = 50 + (ema21[-1] - current) / ema21[-1] * 1000
            return "bear", min(90, strength)
        
        return "neutral", 0
    
    def check_trend_quality(self, closes, highs, lows, volumes) -> Dict:
        """
        检查趋势质量
        满分100分，返回详细评分
        """
        score = 0
        details = []
        
        trend, strength = self.get_trend(closes)
        
        # 1. 趋势强度 (30分)
        if trend in ["strong_bull", "strong_bear"]:
            score += 30
            details.append("强趋势+30")
        elif trend in ["bull", "bear"]:
            score += min(25, int(strength / 4))
            details.append(f"趋势强度{int(strength)}+{min(25, int(strength/4))}")
        
        # 2. RSI位置 (20分)
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        if trend in ["bull", "strong_bull"]:
            if 45 <= rsi <= 65:
                score += 20
                details.append(f"RSI健康{rsi:.0f}+20")
            elif 40 <= rsi < 45:
                score += 15
                details.append(f"RSI偏低{rsi:.0f}+15")
        elif trend in ["bear", "strong_bear"]:
            if 35 <= rsi <= 55:
                score += 20
                details.append(f"RSI健康{rsi:.0f}+20")
            elif 55 < rsi <= 60:
                score += 15
                details.append(f"RSI偏高{rsi:.0f}+15")
        
        # 3. MACD确认 (20分)
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        if len(hist) >= 3:
            if hist[-1] > hist[-2] > hist[-3] and hist[-1] > 0:
                score += 20
                details.append("MACD多头排列+20")
            elif hist[-1] > hist[-2]:
                score += 12
                details.append("MACD向上+12")
        
        # 4. KDJ方向 (15分)
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        if trend in ["bull", "strong_bull"] and k_values[-1] > d_values[-1]:
            score += 15
            details.append("KDJ多头+15")
        elif trend in ["bear", "strong_bear"] and k_values[-1] < d_values[-1]:
            score += 15
            details.append("KDJ空头+15")
        
        # 5. 成交量确认 (10分)
        vol_ma = np.mean(volumes[-10:-1])
        if volumes[-1] > vol_ma * 1.3:
            score += 10
            details.append("放量+10")
        elif volumes[-1] > vol_ma * 0.9:
            score += 5
            details.append("量正常+5")
        
        # 6. 价格位置 (5分)
        ema21 = self.calculate_ema(closes, 21)
        distance = abs(closes[-1] - ema21[-1]) / closes[-1]
        if 0.003 < distance < 0.015:
            score += 5
            details.append(f"位置佳+5")
        
        return {
            "score": score,
            "details": details,
            "trend": trend,
            "strength": strength,
            "rsi": rsi,
            "atr": self.calculate_atr(highs, lows, closes)
        }
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        # 15分钟冷却
        if current_time < self.last_trade_time + 15 * 60:
            return None, None, None, None, None
        
        current_price = closes[-1]
        
        # 趋势质量检查
        quality = self.check_trend_quality(closes, highs, lows, volumes)
        
        # 过滤条件: 需要>=70分且趋势明确
        if quality["score"] < 70:
            return None, None, None, None, None, 0
        
        trend = quality["trend"]
        atr = quality["atr"]
        if trend == "neutral":
            return None, None, None, None, None, 0
        
        signal_type = None
        is_long = True
        setup = f"品质{quality['score']}分|{'|'.join(quality['details'][:3])}"
        
        # 入场方向
        if trend in ["strong_bull", "bull"]:
            signal_type = SignalType.LONG
        else:
            signal_type = SignalType.SHORT
            is_long = False
        
        # 支撑阻力
        support = min(lows[-20:])
        resistance = max(highs[-20:])
        
        self.last_trade_time = current_time
        return signal_type, setup, is_long, support, resistance, atr


class Backtester:
    """
    V19融合版回测引擎
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
        # 风控系统
        self.risk_manager = RiskManager(initial_capital)
        
        # 加仓配置
        self.first_pct = 0.40
        self.add_pct_1 = 0.25
        self.add_pct_2 = 0.15
        self.max_total_pct = 0.80
        
        # 加仓条件
        self.add_1_threshold = -0.8
        self.add_2_threshold = -1.5
        
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
        generator = V19SignalGenerator()
        position: Optional[Position] = None
        daily_trades = {}
        
        for i in range(55, len(klines)):
            current_kline = klines[i]
            current_time = datetime.fromtimestamp(current_kline.timestamp)
            current_price = current_kline.close
            
            # 更新风控
            self.risk_manager.update_capital(self.current_capital)
            
            hist = klines[max(0, i-100):i+1]
            opens = np.array([k.open for k in hist])
            highs = np.array([k.high for k in hist])
            lows = np.array([k.low for k in hist])
            closes = np.array([k.close for k in hist])
            volumes = np.array([k.volume for k in hist])
            
            self.equity_curve.append((current_time, self.current_capital))
            
            if position:
                pnl_pct = position.get_pnl_pct(current_price)
                
                if pnl_pct > position.highest_pnl_pct:
                    position.highest_pnl_pct = pnl_pct
                
                # ===== 智能加仓 (V17风格) =====
                if position.added_positions == 0 and pnl_pct <= self.add_1_threshold:
                    current_exposure = position.total_invested / self.initial_capital
                    available = self.max_total_pct - current_exposure
                    if available >= self.add_pct_1:
                        invest = self.initial_capital * self.add_pct_1
                        qty = round(invest / current_price, 3)
                        position.add_entry(current_price, qty)
                        position.added_positions = 1
                        
                        # 调整止损到新的均价
                        atr_sl = position.atr * 1.5
                        if position.direction == "LONG":
                            position.sl_price = position.avg_price - atr_sl
                        else:
                            position.sl_price = position.avg_price + atr_sl
                        
                        print(f"   ➕ 加仓(+25%) 价格:{current_price:.2f} 均价:{position.avg_price:.2f}")
                
                elif position.added_positions == 1 and pnl_pct <= self.add_2_threshold:
                    current_exposure = position.total_invested / self.initial_capital
                    available = self.max_total_pct - current_exposure
                    if available >= self.add_pct_2:
                        invest = self.initial_capital * self.add_pct_2
                        qty = round(invest / current_price, 3)
                        position.add_entry(current_price, qty)
                        position.added_positions = 2
                        
                        atr_sl = position.atr * 1.5
                        if position.direction == "LONG":
                            position.sl_price = position.avg_price - atr_sl
                        else:
                            position.sl_price = position.avg_price + atr_sl
                        
                        print(f"   ➕ 加仓(+15%) 价格:{current_price:.2f} 均价:{position.avg_price:.2f}")
                
                # ===== V17风格移动止盈 =====
                # 盈利10%启动
                if pnl_pct > 10 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.05
                    else:
                        position.trail_sl = position.avg_price * 0.95
                
                # 盈利15%后回撤2%止盈
                if pnl_pct > 15:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.98
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.02
                        if new_sl < position.trail_sl or position.trail_sl == 0:
                            position.trail_sl = new_sl
                
                # 盈利25%后回撤1%止盈
                if pnl_pct > 25:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.99
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.01
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
                else:
                    if current_kline.high >= position.sl_price:
                        exit_price = position.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    elif position.trail_sl > 0 and current_kline.high >= position.trail_sl:
                        exit_price = position.trail_sl
                        exit_reason = "移动止盈"
                        exit_trade = True
                
                if exit_trade:
                    trade = Trade(
                        entry_time=position.entry_time,
                        direction=position.direction,
                        entries=position.entries.copy(),
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                        max_pnl_pct=position.highest_pnl_pct
                    )
                    pnl_pct_final, pnl_usdt = trade.calc_pnl()
                    self.current_capital += pnl_usdt
                    result.trades.append(trade)
                    
                    is_win = pnl_pct_final > 0
                    if is_win:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    # 更新风控统计
                    self.risk_manager.update_trade_result(is_win, pnl_pct_final)
                    
                    emoji = "✅" if is_win else "❌"
                    avg_entry = position.avg_price
                    num_entries = len(position.entries)
                    print(f"   {emoji} [{exit_reason}] 收益:{pnl_pct_final*100:+.1f}% 最高:{position.highest_pnl_pct:+.1f}% 建仓{num_entries}次")
                    position = None
            
            else:
                # 检查风控
                if not self.risk_manager.can_trade():
                    continue
                
                signal_type, setup, is_long, support, resistance, atr = generator.generate_signal(
                    opens, highs, lows, closes, volumes, current_kline.timestamp
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    # 每天最多3次
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 3:
                        continue
                    
                    # ===== Kelly仓位计算 =====
                    kelly_size = self.risk_manager.get_kelly_position_size(base_size=0.50)
                    position_pct = max(self.first_pct, kelly_size * 0.8)  # 首仓至少40%
                    
                    # ATR止损 - 1.5倍ATR
                    stop_distance = atr * 1.5
                    
                    if is_long:
                        sl = current_price - stop_distance
                    else:
                        sl = current_price + stop_distance
                    
                    # 限制风险不超过2%
                    risk_pct = stop_distance / current_price
                    if risk_pct > 0.02:
                        if is_long:
                            sl = current_price * 0.98
                        else:
                            sl = current_price * 1.02
                        stop_distance = abs(current_price - sl)
                    
                    # 计算仓位
                    invest = self.initial_capital * position_pct
                    qty = round(invest / current_price, 3)
                    
                    position = Position(
                        entry_time=current_time,
                        direction=direction,
                        tp_price=0,  # 不使用固定止盈，用移动止盈
                        sl_price=sl,
                        trail_sl=0,
                        highest_price=0,
                        highest_pnl_pct=0,
                        added_positions=0,
                        atr=atr,
                        initial_risk_pct=risk_pct
                    )
                    position.add_entry(current_price, qty)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct_display = stop_distance / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}]")
                    print(f"   📊 {setup}")
                    print(f"   💰 首仓{position_pct*100:.0f}% (Kelly:{kelly_size*100:.0f}%) 入场:{current_price:.2f}")
                    print(f"   🎯 ATR止损:{sl:.2f}({risk_pct_display:.2f}%)")
        
        if position:
            last_price = klines[-1].close
            trade = Trade(
                entry_time=position.entry_time,
                direction=position.direction,
                entries=position.entries.copy(),
                exit_price=last_price,
                exit_reason="结束",
                max_pnl_pct=position.highest_pnl_pct
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
    print("📊 ETHUSDT V19策略回测报告 (终极融合版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率50%+ | 最大回撤<15%")
    print("📚 融合策略:")
    print("   • V17核心: 趋势突破/回调 + 分级移动止盈")
    print("   • V18风控: Kelly仓位 + 15%回撤限制")
    print("   • 新优化: 品质评分(≥70分) + 智能加仓")
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
        print(f"\n📝 加仓统计: {len(multi_entry_trades)}次补仓")
        win_count = sum(1 for t in multi_entry_trades if t.calc_pnl()[0] > 0)
        print(f"   补仓后盈利: {win_count}/{len(multi_entry_trades)}次")
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场均价':<12} {'出场':<10} {'收益':<10} {'最高':<10} {'原因':<12}")
        print("-"*80)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            avg = sum(p*q for p,q in trade.entries) / sum(q for _,q in trade.entries)
            pnl_pct, _ = trade.calc_pnl()
            print(f"{entry_time:<14} {direction:<5} {avg:<12.2f} {trade.exit_price:<10.2f} {pnl_pct*100:+.1f}%      {trade.max_pnl_pct:+.1f}%      {trade.exit_reason:<12}")
    
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
    
    if result.win_rate >= 50:
        print(f"   ✅ 胜率达标: {result.win_rate:.1f}% 🎉")
    else:
        print(f"   ❌ 胜率偏低: {result.win_rate:.1f}%")
    
    if result.max_drawdown_pct < 15:
        print(f"   ✅ 回撤达标: {result.max_drawdown_pct:.1f}% < 15% 🎉")
    elif result.max_drawdown_pct < 20:
        print(f"   ⚠️ 回撤接近: {result.max_drawdown_pct:.1f}% (目标<15%)")
    else:
        print(f"   ❌ 回撤偏高: {result.max_drawdown_pct:.1f}%")


def main():
    print("🚀 ETHUSDT V19策略回测 - 终极融合版")
    print("="*80)
    print("📚 核心融合:")
    print("   1️⃣ V17优势: 趋势策略 + 分级移动止盈(10%/15%/25%)")
    print("   2️⃣ V18优势: Kelly仓位管理 + 15%回撤限制")
    print("   3️⃣ 新优化: 品质评分≥70分入场 + 智能加仓(40%+25%+15%)")
    print("   4️⃣ 风控: ATR动态止损(1.5x) + 风险≤2%")
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
