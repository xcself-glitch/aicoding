#!/usr/bin/env python3
"""
ETHUSDT策略回测 V17 - 专业量化版
参考成熟策略:
1. 多时间框架分析 (15m主交易, 5m确认)
2. 3-Stage Entry (首仓30%→回调加仓)
3. EMA+MACD+RSI多指标共振
4. 动态ATR止损
目标: 周收益50%+ | 胜率60%+
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
    highest_price: float = 0.0
    added_positions: int = 0
    atr: float = 0.0
    
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


class V17SignalGenerator:
    """
    V17专业信号生成器
    参考: 多时间框架分析 + EMA+MACD+RSI共振
    """
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_trade_time = 0
        
    def calculate_ema(self, prices, period):
        alpha = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append(alpha * price + (1 - alpha) * ema[-1])
        return np.array(ema)
    
    def calculate_atr(self, highs, lows, closes, period=14):
        """计算ATR (Average True Range)"""
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        atr = np.mean(tr[-period:])
        return atr
    
    def get_trend_direction(self, closes):
        """
        判断趋势方向 - 多EMA系统
        EMA9 > EMA21 > EMA55 = 强多头
        EMA9 < EMA21 < EMA55 = 强空头
        """
        if len(closes) < 55:
            return "neutral"
        
        ema9 = self.calculate_ema(closes, 9)
        ema21 = self.calculate_ema(closes, 21)
        ema55 = self.calculate_ema(closes, 55)
        
        current = closes[-1]
        
        # 强多头
        if current > ema9[-1] > ema21[-1] > ema55[-1]:
            return "strong_bull"
        # 强空头
        elif current < ema9[-1] < ema21[-1] < ema55[-1]:
            return "strong_bear"
        # 多头
        elif ema9[-1] > ema21[-1]:
            return "bull"
        # 空头
        elif ema9[-1] < ema21[-1]:
            return "bear"
        
        return "neutral"
    
    def check_pullback_quality(self, closes, highs, lows, volumes):
        """
        检查回调质量 - 专业策略
        1. 价格在EMA附近缩量回调
        2. 出现十字星或锤子线形态
        3. 成交量萎缩
        """
        ema9 = self.calculate_ema(closes, 9)
        ema21 = self.calculate_ema(closes, 21)
        
        # 当前K线信息
        current_close = closes[-1]
        current_open = closes[-2] if len(closes) > 1 else closes[-1]
        current_high = highs[-1]
        current_low = lows[-1]
        
        # 检查是否靠近EMA9 (回调)
        distance_to_ema9 = abs(current_close - ema9[-1]) / current_close
        
        # 检查K线形态 (十字星: 实体小, 影线长)
        body = abs(current_close - current_open)
        range_k = current_high - current_low
        
        is_doji = body < range_k * 0.3 if range_k > 0 else False
        
        # 检查成交量萎缩
        vol_ma = np.mean(volumes[-10:-1])
        vol_current = volumes[-1]
        is_low_volume = vol_current < vol_ma * 0.8
        
        return {
            'distance': distance_to_ema9,
            'is_doji': is_doji,
            'is_low_volume': is_low_volume,
            'quality_score': (1 if distance_to_ema9 < 0.005 else 0) + 
                           (1 if is_doji else 0) + 
                           (1 if is_low_volume else 0)
        }
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        # 15分钟冷却
        if current_time < self.last_trade_time + 15 * 60:
            return None, None, None, None, None, 0
        
        current_price = closes[-1]
        trend = self.get_trend_direction(closes)
        
        # 只在趋势明确时交易
        if trend == "neutral":
            return None, None, None, None, None, 0
        
        # 计算ATR
        atr = self.calculate_atr(highs, lows, closes)
        
        # 计算指标
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        # 支撑阻力
        support = min(lows[-20:])
        resistance = max(highs[-20:])
        
        signal_type = None
        is_long = True
        setup = ""
        score = 0
        
        # ===== 做多条件 =====
        if trend in ["bull", "strong_bull"]:
            ema9 = self.calculate_ema(closes, 9)
            ema21 = self.calculate_ema(closes, 21)
            
            # 检查回调质量
            pullback = self.check_pullback_quality(closes, highs, lows, volumes)
            
            # **核心策略**: 趋势回调入场
            # 条件1: 价格在EMA9和EMA21之间 (健康回调)
            # 条件2: RSI在40-65之间 (不过买)
            # 条件3: MACD向上或柱状图收窄
            # 条件4: KDJ向上
            
            price_between_emas = ema21[-1] < current_price < ema9[-1]
            rsi_ok = 40 < rsi < 65
            macd_ok = macd_signal.trend == TrendDirection.UP or hist[-1] > hist[-2]
            kdj_ok = k_values[-1] > d_values[-1]
            
            if price_between_emas and rsi_ok and macd_ok and kdj_ok:
                signal_type = SignalType.LONG
                score = 70 + pullback['quality_score'] * 10
                setup = f"趋势回调(质量{pullback['quality_score']}/3)"
            
            # 备选策略: 突破入场 (强势行情)
            elif current_price > ema9[-1] * 1.005 and rsi < 70 and macd_signal.histogram > 0:
                if k_values[-1] > d_values[-1]:
                    signal_type = SignalType.LONG
                    score = 65
                    setup = "趋势突破"
        
        # ===== 做空条件 =====
        elif trend in ["bear", "strong_bear"]:
            ema9 = self.calculate_ema(closes, 9)
            ema21 = self.calculate_ema(closes, 21)
            
            pullback = self.check_pullback_quality(closes, highs, lows, volumes)
            
            price_between_emas = ema9[-1] < current_price < ema21[-1]
            rsi_ok = 35 < rsi < 60
            macd_ok = macd_signal.trend == TrendDirection.DOWN or hist[-1] < hist[-2]
            kdj_ok = k_values[-1] < d_values[-1]
            
            if price_between_emas and rsi_ok and macd_ok and kdj_ok:
                signal_type = SignalType.SHORT
                is_long = False
                score = 70 + pullback['quality_score'] * 10
                setup = f"趋势反弹(质量{pullback['quality_score']}/3)"
            
            elif current_price < ema9[-1] * 0.995 and rsi > 30 and macd_signal.histogram < 0:
                if k_values[-1] < d_values[-1]:
                    signal_type = SignalType.SHORT
                    is_long = False
                    score = 65
                    setup = "趋势跌破"
        
        if signal_type and score >= 65:
            self.last_trade_time = current_time
            return signal_type, setup, is_long, support, resistance, atr
        
        return None, None, None, None, None, 0


class Backtester:
    """
    专业回测引擎
    参考: 3-Stage Entry + ATR动态止损
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
        # === 3-Stage Entry配置 ===
        self.stage_1_pct = 0.30  # 首仓30%
        self.stage_2_pct = 0.30  # 二仓30%
        self.stage_3_pct = 0.20  # 三仓20%
        self.max_total_pct = 0.80
        
        # === 加仓条件 ===
        self.add_2_threshold = -1.5  # 浮亏1.5%加二仓
        self.add_3_threshold = -3.0  # 浮亏3%加三仓
        
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
        generator = V17SignalGenerator()
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
                
                if pnl_pct > position.highest_price:
                    position.highest_price = pnl_pct
                
                # ===== 分批建仓逻辑 (只在趋势延续时加仓) =====
                if position.added_positions == 0 and pnl_pct <= self.add_2_threshold:
                    # 二仓: 浮亏1.5%加仓
                    current_exposure = position.total_invested / self.initial_capital
                    available = self.max_total_pct - current_exposure
                    
                    if available >= self.stage_2_pct:
                        invest = self.initial_capital * self.stage_2_pct
                        qty = round(invest / current_price, 3)
                        position.add_entry(current_price, qty)
                        position.added_positions = 1
                        
                        # 调整止损到新的均价
                        new_sl = position.avg_price - position.atr * 1.5 if position.direction == "LONG" else position.avg_price + position.atr * 1.5
                        position.sl_price = new_sl
                        
                        total_pct = position.total_invested / self.initial_capital * 100
                        print(f"   ➕ 二仓(+30%) 价格:{current_price:.2f} 新均价:{position.avg_price:.2f} 仓位:{total_pct:.0f}%")
                
                elif position.added_positions == 1 and pnl_pct <= self.add_3_threshold:
                    # 三仓: 浮亏3%加仓
                    current_exposure = position.total_invested / self.initial_capital
                    available = self.max_total_pct - current_exposure
                    
                    if available >= self.stage_3_pct:
                        invest = self.initial_capital * self.stage_3_pct
                        qty = round(invest / current_price, 3)
                        position.add_entry(current_price, qty)
                        position.added_positions = 2
                        
                        new_sl = position.avg_price - position.atr * 1.5 if position.direction == "LONG" else position.avg_price + position.atr * 1.5
                        position.sl_price = new_sl
                        
                        total_pct = position.total_invested / self.initial_capital * 100
                        print(f"   ➕ 三仓(+20%) 价格:{current_price:.2f} 新均价:{position.avg_price:.2f} 仓位:{total_pct:.0f}%")
                
                # ===== 动态移动止损 =====
                # 盈利8%启动移动止损
                if pnl_pct > 8 and position.trail_sl == 0:
                    if position.direction == "LONG":
                        position.trail_sl = position.avg_price * 1.04  # 保4%利润
                    else:
                        position.trail_sl = position.avg_price * 0.96
                
                # 盈利15%后跟踪止损 (回撤2%)
                if pnl_pct > 15:
                    if position.direction == "LONG":
                        new_sl = current_price * 0.98
                        if new_sl > position.trail_sl:
                            position.trail_sl = new_sl
                    else:
                        new_sl = current_price * 1.02
                        if new_sl < position.trail_sl or position.trail_sl == 0:
                            position.trail_sl = new_sl
                
                # 盈利25%后紧密跟踪 (回撤1%)
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
                        exit_reason = "移动止盈"
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
                        exit_reason=exit_reason
                    )
                    pnl_pct, pnl_usdt = trade.calc_pnl()
                    self.current_capital += pnl_usdt
                    result.trades.append(trade)
                    
                    if pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    emoji = "✅" if pnl_pct > 0 else "❌"
                    avg_entry = position.avg_price
                    num_entries = len(position.entries)
                    print(f"   {emoji} [{exit_reason}] 收益:{pnl_pct*100:+.1f}% 均价:{avg_entry:.2f} 建仓{num_entries}次")
                    position = None
            
            else:
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
                    
                    # ATR动态止损 - 1.5倍ATR
                    if is_long:
                        sl = current_price - atr * 1.5
                        risk = current_price - sl
                        tp = current_price + risk * 2.5  # 2.5:1盈亏比
                    else:
                        sl = current_price + atr * 1.5
                        risk = sl - current_price
                        tp = current_price - risk * 2.5
                    
                    # 首仓30%
                    invest = self.initial_capital * self.stage_1_pct
                    qty = round(invest / current_price, 3)
                    
                    position = Position(
                        entry_time=current_time,
                        direction=direction,
                        tp_price=tp,
                        sl_price=sl,
                        trail_sl=0,
                        highest_price=0,
                        added_positions=0,
                        atr=atr
                    )
                    position.add_entry(current_price, qty)
                    
                    result.total_trades += 1
                    
                    dir_emoji = "🟢" if direction == "LONG" else "🔴"
                    risk_pct = risk / current_price * 100
                    reward_pct = abs(tp - current_price) / current_price * 100
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')} {dir_emoji}[{direction}] {setup}")
                    print(f"   💰 首仓30% 入场:{current_price:.2f} ATR:{atr:.2f}")
                    print(f"   🎯 止损:{sl:.2f}({risk_pct:.2f}%) 止盈:{tp:.2f}({reward_pct:.2f}%)")
                    print(f"   📈 加仓计划: 浮亏1.5%→+30% | 浮亏3%→+20%")
        
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
    print("📊 ETHUSDT V17策略回测报告 (专业量化版)")
    print("="*80)
    print("🎯 目标: 周收益50%+ | 胜率60%+")
    print("📚 参考策略:")
    print("   • 多时间框架分析 (EMA9/21/55)")
    print("   • 3-Stage Entry (30%+30%+20%)")
    print("   • ATR动态止损 (1.5xATR)")
    print("   • 趋势回调+缩量十字星入场")
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
        print(f"\n📝 分批建仓统计:")
        for t in multi_entry_trades:
            num_entries = len(t.entries)
            pnl, _ = t.calc_pnl()
            entry_prices = [f"{p:.0f}" for p, _ in t.entries]
            print(f"   建仓{num_entries}次 收益:{pnl*100:+.1f}% 价格:{','.join(entry_prices)}")
    
    if result.trades:
        print(f"\n📋 全部交易明细:")
        print("-"*80)
        print(f"{'时间':<14} {'方向':<5} {'入场均价':<12} {'出场':<10} {'收益':<10} {'建仓次数':<10} {'原因':<12}")
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
    print("🚀 ETHUSDT V17策略回测 - 专业量化版")
    print("="*80)
    print("📚 核心改进:")
    print("   1️⃣ EMA9/21/55多周期趋势判断")
    print("   2️⃣ 回调质量评分 (距离+形态+成交量)")
    print("   3️⃣ 3-Stage Entry: 30% → 浮亏1.5%→+30% → 浮亏3%→+20%")
    print("   4️⃣ ATR动态止损 (1.5倍ATR)")
    print("   5️⃣ 分级移动止盈: 8%启动→15%回撤2%→25%回撤1%")
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
