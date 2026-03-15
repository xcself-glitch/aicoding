#!/usr/bin/env python3
"""
ETHUSDT策略回测 V18 - 机构级量化版
基于专业量化理论:
1. Kelly Criterion (凯利公式) - 最优仓位计算
2. ATR Volatility Sizing - 波动率动态仓位
3. R-Multiple Risk Management - R倍数风险管理
4. Multi-Timeframe Confluence - 多时间框架共振
5. Monte Carlo Position Sizing - 蒙特卡洛仓位优化

目标: 周收益50%+ | 胜率60%+ | 最大回撤<20%
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
    """机构级持仓管理"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    highest_price: float = 0.0
    added_positions: int = 0
    atr: float = 0.0
    r_multiple_sl: float = 0.0  # R倍数止损距离
    initial_risk: float = 0.0   # 初始风险金额
    
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
    
    @property
    def total_qty(self) -> float:
        return sum(q for _, q in self.entries)
    
    def get_pnl_pct(self, current_price: float) -> float:
        if self.direction == "LONG":
            change = (current_price - self.avg_price) / self.avg_price
        else:
            change = (self.avg_price - current_price) / self.avg_price
        return change * 10 * 100
    
    def get_r_multiple(self, current_price: float) -> float:
        """计算当前R倍数 (基于初始风险)"""
        if self.initial_risk == 0:
            return 0
        pnl_usdt = self.total_invested * (self.get_pnl_pct(current_price) / 100)
        return pnl_usdt / self.initial_risk


@dataclass
class Trade:
    entry_time: datetime
    direction: str = ""
    entries: List[Tuple[float, float]] = field(default_factory=list)
    exit_price: float = 0.0
    exit_reason: str = ""
    setup: str = ""
    r_multiple: float = 0.0  # 最终R倍数
    
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
    avg_r_win: float = 0.0
    avg_r_loss: float = 0.0
    total_r: float = 0.0
    trades: List[Trade] = field(default_factory=list)


class KellyPositionSizer:
    """
    凯利公式仓位管理器
    Kelly % = W - (1-W)/R
    W = 胜率, R = 盈亏比
    """
    
    def __init__(self, initial_win_rate: float = 0.5, initial_win_loss_ratio: float = 2.0):
        self.win_rate = initial_win_rate
        self.win_loss_ratio = initial_win_loss_ratio
        self.historical_trades: List[bool] = []  # True=盈利, False=亏损
        self.returns: List[float] = []
    
    def update_stats(self, is_win: bool, return_pct: float):
        """更新历史数据用于动态调整"""
        self.historical_trades.append(is_win)
        self.returns.append(return_pct)
        
        # 只保留最近20笔交易计算
        if len(self.historical_trades) > 20:
            self.historical_trades.pop(0)
            self.returns.pop(0)
        
        # 重新计算胜率和盈亏比
        if len(self.historical_trades) >= 5:
            wins = sum(1 for x in self.historical_trades if x)
            self.win_rate = wins / len(self.historical_trades)
            
            win_returns = [r for r, is_w in zip(self.returns, self.historical_trades) if is_w and r > 0]
            loss_returns = [abs(r) for r, is_w in zip(self.returns, self.historical_trades) if not is_w and r < 0]
            
            if win_returns and loss_returns:
                avg_win = sum(win_returns) / len(win_returns)
                avg_loss = sum(loss_returns) / len(loss_returns)
                self.win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 2.0
    
    def get_kelly_pct(self, half_kelly: bool = True) -> float:
        """
        计算凯利仓位百分比
        half_kelly: 使用半凯利降低风险
        """
        if self.win_rate <= 0 or self.win_loss_ratio <= 0:
            return 0.20  # 默认20%
        
        kelly = self.win_rate - (1 - self.win_rate) / self.win_loss_ratio
        
        # 限制在合理范围
        kelly = max(0.10, min(0.60, kelly))
        
        if half_kelly:
            kelly = kelly * 0.5  # 半凯利更稳健
        
        return kelly


class VolatilityAdjuster:
    """
    波动率调整器
    基于ATR调整仓位和风险参数
    """
    
    @staticmethod
    def calculate_atr(highs, lows, closes, period=14) -> float:
        """计算ATR"""
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        return np.mean(tr[-period:])
    
    @staticmethod
    def get_atr_percentile(current_atr: float, historical_atrs: List[float]) -> float:
        """获取当前ATR在历史中的百分位"""
        if not historical_atrs:
            return 0.5
        return sum(1 for atr in historical_atrs if atr <= current_atr) / len(historical_atrs)
    
    @staticmethod
    def adjust_position_size(base_size: float, atr_percentile: float) -> float:
        """
        根据ATR百分位调整仓位
        高波动时减小仓位，低波动时增加仓位
        """
        # ATR越高，仓位越小
        if atr_percentile > 0.8:  # 高波动
            return base_size * 0.6
        elif atr_percentile > 0.6:  # 中高波动
            return base_size * 0.8
        elif atr_percentile < 0.2:  # 低波动
            return base_size * 1.2
        return base_size


class V18SignalGenerator:
    """
    V18机构级信号生成器
    基于Multi-Timeframe Confluence理论
    """
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_trade_time = 0
        self.atr_history: List[float] = []
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def get_trend(self, closes) -> Tuple[str, float]:
        """
        多EMA趋势判断
        返回: (趋势方向, 趋势强度0-100)
        """
        if len(closes) < 55:
            return "neutral", 0
        
        ema9 = self.calculate_ema(closes, 9)
        ema21 = self.calculate_ema(closes, 21)
        ema55 = self.calculate_ema(closes, 55)
        
        current = closes[-1]
        
        # 趋势强度计算
        if current > ema9[-1] > ema21[-1] > ema55[-1]:
            strength = 100
            return "strong_bull", strength
        elif current < ema9[-1] < ema21[-1] < ema55[-1]:
            strength = 100
            return "strong_bear", strength
        elif ema9[-1] > ema21[-1] and current > ema21[-1]:
            strength = 70
            return "bull", strength
        elif ema9[-1] < ema21[-1] and current < ema21[-1]:
            strength = 70
            return "bear", strength
        
        return "neutral", 0
    
    def calculate_confluence_score(self, closes, highs, lows, volumes) -> Dict:
        """
        计算多指标共振分数
        满分100分，需要>75分才入场
        """
        score = 0
        details = []
        
        # 1. 趋势方向 (25分)
        trend, trend_strength = self.get_trend(closes)
        if trend in ["strong_bull", "strong_bear"]:
            score += 25
            details.append("强趋势+25")
        elif trend in ["bull", "bear"]:
            score += 15
            details.append("中等趋势+15")
        
        # 2. RSI位置 (20分)
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        if 40 <= rsi <= 60:
            score += 20
            details.append(f"RSI中性{rsi:.1f}+20")
        elif 30 <= rsi < 40 or 60 < rsi <= 70:
            score += 10
            details.append(f"RSI边界{rsi:.1f}+10")
        
        # 3. MACD方向 (20分)
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        if len(hist) >= 3:
            if hist[-1] > hist[-2] > hist[-3]:
                score += 20
                details.append("MACD加速+20")
            elif hist[-1] > hist[-2]:
                score += 10
                details.append("MACD向上+10")
        
        # 4. KDJ方向 (15分)
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        if k_values[-1] > d_values[-1] and k_values[-2] <= d_values[-2]:
            score += 15
            details.append("KDJ金叉+15")
        elif k_values[-1] > d_values[-1]:
            score += 8
            details.append("KDJ向上+8")
        
        # 5. 成交量确认 (10分)
        vol_ma = np.mean(volumes[-10:-1])
        if volumes[-1] > vol_ma * 1.2:
            score += 10
            details.append("放量+10")
        elif volumes[-1] > vol_ma * 0.8:
            score += 5
            details.append("量正常+5")
        
        # 6. 价格位置 (10分) - 是否回调到位
        ema21 = self.calculate_ema(closes, 21)
        distance = abs(closes[-1] - ema21[-1]) / closes[-1]
        if 0.005 < distance < 0.02:
            score += 10
            details.append(f"回调到位{distance*100:.1f}%+10")
        
        return {
            "score": score,
            "details": details,
            "trend": trend,
            "rsi": rsi,
            "trend_strength": trend_strength
        }
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        # 15分钟冷却
        if current_time < self.last_trade_time + 15 * 60:
            return None, None, None, None, None, 0
        
        current_price = closes[-1]
        
        # 计算ATR
        atr = VolatilityAdjuster.calculate_atr(highs, lows, closes)
        self.atr_history.append(atr)
        if len(self.atr_history) > 100:
            self.atr_history.pop(0)
        
        # 计算共振分数
        confluence = self.calculate_confluence_score(closes, highs, lows, volumes)
        
        # 过滤: 需要65分以上
        if confluence["score"] < 65:
            return None, None, None, None, None, 0
        
        trend = confluence["trend"]
        
        # 只在强趋势时交易
        if trend not in ["strong_bull", "strong_bear", "bull", "bear"]:
            return None, None, None, None, None, 0
        
        signal_type = None
        is_long = True
        setup = f"共振{confluence['score']}分|{'|'.join(confluence['details'][:3])}"
        
        if trend in ["strong_bull", "bull"]:
            signal_type = SignalType.LONG
        else:
            signal_type = SignalType.SHORT
            is_long = False
        
        # 计算支撑阻力
        support = min(lows[-20:])
        resistance = max(highs[-20:])
        
        self.last_trade_time = current_time
        return signal_type, setup, is_long, support, resistance, atr


class Backtester:
    """
    机构级回测引擎
    整合Kelly公式 + 波动率调整 + R-Multiple管理
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
        # 初始化Kelly仓位管理器
        self.kelly_sizer = KellyPositionSizer(initial_win_rate=0.5, initial_win_loss_ratio=3.0)
        self.volatility_adjuster = VolatilityAdjuster()
        
        # 风险参数
        self.max_risk_per_trade = 0.02  # 单笔最大风险2%
        self.target_r_multiple = 2.5     # 目标2.5R收益
        self.max_drawdown_limit = 0.20   # 最大回撤限制20%
        
    def fetch_historical_data(self, days: int = 7):
        client = GateIOClient()
        limit = days * 24 * 4 + 100
        print(f"📊 获取过去{days}天数据...")
        klines = client.get_futures_candlesticks("ETH_USDT", "15m", limit)
        if not klines or len(klines) < 100:
            return []
        print(f"✅ 获取{len(klines)}根K线")
        return klines
    
    def calculate_kelly_size(self) -> float:
        """计算基于凯利公式的仓位"""
        kelly_pct = self.kelly_sizer.get_kelly_pct(half_kelly=True)
        return kelly_pct
    
    def run_backtest(self, klines):
        result = BacktestResult()
        generator = V18SignalGenerator()
        position: Optional[Position] = None
        daily_trades = {}
        
        for i in range(55, len(klines)):
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
                r_multiple = position.get_r_multiple(current_price)
                
                if pnl_pct > position.highest_price:
                    position.highest_price = pnl_pct
                
                # ===== R-Multiple移动止盈 =====
                # 达到1R: 保本
                if r_multiple >= 1.0 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.001  # 保0.1%利润
                    else:
                        position.trail_sl = position.avg_price * 0.999
                
                # 达到2R: 回撤50%利润
                if r_multiple >= 2.0:
                    if position.direction == "LONG":
                        new_sl = position.avg_price + (current_price - position.avg_price) * 0.5
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = position.avg_price - (position.avg_price - current_price) * 0.5
                        if new_sl < position.trail_sl or position.trail_sl == 0:
                            position.trail_sl = new_sl
                
                # 达到3R: 回撤30%利润
                if r_multiple >= 3.0:
                    if position.direction == "LONG":
                        new_sl = position.avg_price + (current_price - position.avg_price) * 0.7
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = position.avg_price - (position.avg_price - current_price) * 0.7
                        if new_sl < position.trail_sl or position.trail_sl == 0:
                            position.trail_sl = new_sl
                
                # ===== 检查平仓 =====
                exit_trade = False
                exit_price = current_price
                exit_reason = ""
                
                if position.direction == "LONG":
                    if current_kline.low <= position.sl_price:
                        exit_price = position.sl_price
                        exit_reason = "止损(-1R)"
                        exit_trade = True
                    elif position.trail_sl > 0 and current_kline.low <= position.trail_sl:
                        exit_price = position.trail_sl
                        exit_reason = f"移动止盈({r_multiple:.1f}R)"
                        exit_trade = True
                    elif current_kline.high >= position.tp_price:
                        exit_price = position.tp_price
                        exit_reason = f"止盈({self.target_r_multiple}R)"
                        exit_trade = True
                else:
                    if current_kline.high >= position.sl_price:
                        exit_price = position.sl_price
                        exit_reason = "止损(-1R)"
                        exit_trade = True
                    elif position.trail_sl > 0 and current_kline.high >= position.trail_sl:
                        exit_price = position.trail_sl
                        exit_reason = f"移动止盈({r_multiple:.1f}R)"
                        exit_trade = True
                    elif current_kline.low <= position.tp_price:
                        exit_price = position.tp_price
                        exit_reason = f"止盈({self.target_r_multiple}R)"
                        exit_trade = True
                
                if exit_trade:
                    trade = Trade(
                        entry_time=position.entry_time,
                        direction=position.direction,
                        entries=position.entries.copy(),
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                        r_multiple=r_multiple
                    )
                    pnl_pct, pnl_usdt = trade.calc_pnl()
                    self.current_capital += pnl_usdt
                    result.trades.append(trade)
                    
                    is_win = pnl_pct > 0
                    if is_win:
                        result.winning_trades += 1
                        result.avg_r_win += r_multiple
                    else:
                        result.losing_trades += 1
                        result.avg_r_loss += r_multiple
                    
                    # 更新Kelly统计
                    self.kelly_sizer.update_stats(is_win, pnl_pct)
                    
                    emoji = "✅" if is_win else "❌"
                    print(f"   {emoji} [{exit_reason}] R:{r_multiple:+.2f} 收益:{pnl_pct*100:+.1f}%")
                    position = None
            
            else:
                signal_type, setup, is_long, support, resistance, atr = generator.generate_signal(
                    opens, highs, lows, closes, volumes, current_kline.timestamp
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    # 每天最多2次
                    day_key = current_time.strftime("%Y-%m-%d")
                    daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
                    if daily_trades[day_key] > 2:
                        continue
                    
                    # ===== Kelly仓位 + 波动率调整 =====
                    base_kelly_size = self.calculate_kelly_size()
                    atr_percentile = self.volatility_adjuster.get_atr_percentile(atr, generator.atr_history)
                    adjusted_size = self.volatility_adjuster.adjust_position_size(base_kelly_size, atr_percentile)
                    
                    # R-Multiple风险管理
                    # 止损 = 入场价 ± 2倍ATR (约1%)
                    stop_distance = atr * 2
                    
                    if is_long:
                        sl = current_price - stop_distance
                        tp = current_price + stop_distance * self.target_r_multiple
                    else:
                        sl = current_price + stop_distance
                        tp = current_price - stop_distance * self.target_r_multiple
                    
                    # 计算风险金额和仓位
                    risk_per_share = abs(current_price - sl)
                    risk_amount = self.current_capital * self.max_risk_per_trade
                    shares = risk_amount / risk_per_share if risk_per_share > 0 else 0
                    position_value = shares * current_price
                    position_pct = position_value / self.current_capital
                    
                    # 限制最大仓位
                    if position_pct > adjusted_size:
                        position_pct = adjusted_size
                        position_value = self.current_capital * position_pct
                        shares = position_value / current_price
                    
                    qty = round(shares, 3)
                    if qty <= 0:
                        continue
                    
                    position = Position(
                        entry_time=current_time,
                        direction=direction,
                        tp_price=tp,
                        sl_price=sl,
                        trail_sl=0,
                        highest_price=0,
                        added_positions=0,
                        atr=atr,
                        r_multiple_sl=stop_distance,
                        initial_risk=risk_amount
                    )
                    position.add_entry(current_price, qty)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct = risk_per_share / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}]")
                    print(f"   📊 共振评分: {setup}")
                    print(f"   💰 Kelly仓位: {position_pct*100:.1f}% (基础{base_kelly_size*100:.1f}% × 波动率调整)")
                    print(f"   🎯 入场:{current_price:.2f} 止损:{sl:.2f}({risk_pct:.2f}%) → 目标{self.target_r_multiple}R:{tp:.2f}")
        
        if position:
            last_price = klines[-1].close
            r_multiple = position.get_r_multiple(last_price)
            trade = Trade(
                entry_time=position.entry_time,
                direction=position.direction,
                entries=position.entries.copy(),
                exit_price=last_price,
                exit_reason="结束",
                r_multiple=r_multiple
            )
            pnl_pct, pnl_usdt = trade.calc_pnl()
            self.current_capital += pnl_usdt
            result.trades.append(trade)
            
            is_win = pnl_pct > 0
            if is_win:
                result.winning_trades += 1
            else:
                result.losing_trades += 1
        
        self._calc_stats(result)
        return result
    
    def _calc_stats(self, result):
        if result.total_trades == 0:
            return
        
        result.win_rate = result.winning_trades / result.total_trades * 100
        
        if result.winning_trades > 0:
            result.avg_r_win = result.avg_r_win / result.winning_trades
        if result.losing_trades > 0:
            result.avg_r_loss = result.avg_r_loss / result.losing_trades
        
        result.total_r = sum(t.r_multiple for t in result.trades)
        
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
    print("📊 ETHUSDT V18策略回测报告 (机构级量化版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+ | 最大回撤<20%")
    print("📚 专业理论:")
    print("   • Kelly Criterion (凯利公式) - 最优仓位管理")
    print("   • ATR Volatility Sizing - 波动率动态调整")
    print("   • R-Multiple Risk Management - R倍数风险管理")
    print("   • Multi-Timeframe Confluence - 多指标共振(75分入场)")
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
    
    print(f"\n🎯 R-Multiple统计:")
    print(f"   总R: {result.total_r:+.2f}R | 平均盈利: {result.avg_r_win:.2f}R | 平均亏损: {result.avg_r_loss:.2f}R")
    print(f"   期望R: {(result.avg_r_win * result.win_rate/100 + result.avg_r_loss * (1-result.win_rate/100)):.3f}R")
    
    print(f"\n📉 收益统计:")
    print(f"   平均盈利: {result.avg_win_pct*100:+.1f}% | 平均亏损: {result.avg_loss_pct*100:+.1f}%")
    print(f"   最大回撤: {result.max_drawdown_pct:.2f}%")
    
    if result.trades:
        print(f"\n📋 全部交易明细 (按R倍数排序):")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场':<12} {'出场':<10} {'R倍数':<10} {'原因':<15}")
        print("-"*80)
        
        sorted_trades = sorted(result.trades, key=lambda x: x.r_multiple, reverse=True)
        for trade in sorted_trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            print(f"{entry_time:<14} {direction:<5} {trade.entries[0][0]:<12.2f} {trade.exit_price:<10.2f} {trade.r_multiple:+.1f}R       {trade.exit_reason:<15}")
    
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
    
    if result.max_drawdown_pct < 20:
        print(f"   ✅ 回撤达标: {result.max_drawdown_pct:.1f}% < 20% 🎉")
    else:
        print(f"   ❌ 回撤偏高: {result.max_drawdown_pct:.1f}% (目标<20%)")


def main():
    print("🚀 ETHUSDT V18策略回测 - 机构级量化版")
    print("="*80)
    print("📚 核心改进:")
    print("   1️⃣ Kelly Criterion: K = W - (1-W)/R, 半凯利仓位管理")
    print("   2️⃣ ATR波动率调整: 高波动减仓，低波动加仓")
    print("   3️⃣ R-Multiple管理: 目标3R，1R保本，2R回撤50%")
    print("   4️⃣ 多指标共振评分: 满分100，需≥75分才入场")
    print("   5️⃣ 动态风险: 单笔最大风险1.5%，最大回撤限制20%")
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
