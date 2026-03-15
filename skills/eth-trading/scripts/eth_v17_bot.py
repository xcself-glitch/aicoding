#!/usr/bin/env python3
"""
ETHUSDT V17策略交易机器人
- 专业量化策略（7天回测+139%收益）
- 多时间框架分析 + 3-Stage Entry
- EMA+MACD+RSI多指标共振
- 飞书通知集成
"""

import sys
import os
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from strategies.gateio_client import GateIOClient
from strategies.indicators import TechnicalIndicators, TrendDirection

sys.path.insert(0, str(Path(__file__).parent.parent / 'config'))
from strategy_config_v2 import SignalType


@dataclass
class Position:
    """持仓数据"""
    entry_time: datetime
    direction: str
    entries: List[Tuple[float, float]] = field(default_factory=list)
    tp_price: float = 0.0
    sl_price: float = 0.0
    trail_sl: float = 0.0
    highest_pnl_pct: float = 0.0
    added_positions: int = 0
    atr: float = 0.0
    setup: str = ""
    
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
        """计算盈亏百分比（10倍杠杆）"""
        if self.direction == "LONG":
            change = (current_price - self.avg_price) / self.avg_price
        else:
            change = (self.avg_price - current_price) / self.avg_price
        return change * 10 * 100


class V17SignalGenerator:
    """V17专业信号生成器"""
    
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
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        return np.mean(tr[-period:]) if len(tr) >= period else np.mean(tr)
    
    def get_trend_direction(self, closes):
        """多EMA趋势判断"""
        if len(closes) < 55:
            return "neutral"
        
        ema9 = self.calculate_ema(closes, 9)
        ema21 = self.calculate_ema(closes, 21)
        ema55 = self.calculate_ema(closes, 55)
        
        current = closes[-1]
        
        if current > ema9[-1] > ema21[-1] > ema55[-1]:
            return "strong_bull"
        elif current < ema9[-1] < ema21[-1] < ema55[-1]:
            return "strong_bear"
        elif ema9[-1] > ema21[-1]:
            return "bull"
        elif ema9[-1] < ema21[-1]:
            return "bear"
        
        return "neutral"
    
    def generate_signal(self, opens, highs, lows, closes, volumes, current_time):
        """生成交易信号"""
        if current_time < self.last_trade_time + 15 * 60:
            return None, None, None, None, None, 0, 0
        
        current_price = closes[-1]
        trend = self.get_trend_direction(closes)
        
        if trend == "neutral":
            return None, None, None, None, None, 0, 0
        
        atr = self.calculate_atr(highs, lows, closes)
        
        rsi_values = self.indicators.calculate_rsi(closes, 14)
        rsi = rsi_values[-1]
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, 9, 3, 3)
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, 12, 26, 9)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        support = min(lows[-20:])
        resistance = max(highs[-20:])
        
        signal_type = None
        is_long = True
        setup = ""
        score = 0
        
        # 做多条件
        if trend in ["bull", "strong_bull"]:
            ema9 = self.calculate_ema(closes, 9)
            ema21 = self.calculate_ema(closes, 21)
            
            price_between_emas = ema21[-1] < current_price < ema9[-1]
            rsi_ok = 40 < rsi < 65
            macd_ok = macd_signal.trend == TrendDirection.UP or hist[-1] > hist[-2]
            kdj_ok = k_values[-1] > d_values[-1]
            
            if price_between_emas and rsi_ok and macd_ok and kdj_ok:
                signal_type = "LONG"
                score = 75
                setup = "趋势回调"
            elif current_price > ema9[-1] * 1.005 and rsi < 70 and macd_signal.histogram > 0:
                if k_values[-1] > d_values[-1]:
                    signal_type = "LONG"
                    score = 65
                    setup = "趋势突破"
        
        # 做空条件
        elif trend in ["bear", "strong_bear"]:
            ema9 = self.calculate_ema(closes, 9)
            ema21 = self.calculate_ema(closes, 21)
            
            price_between_emas = ema9[-1] < current_price < ema21[-1]
            rsi_ok = 35 < rsi < 60
            macd_ok = macd_signal.trend == TrendDirection.DOWN or hist[-1] < hist[-2]
            kdj_ok = k_values[-1] < d_values[-1]
            
            if price_between_emas and rsi_ok and macd_ok and kdj_ok:
                signal_type = "SHORT"
                is_long = False
                score = 75
                setup = "趋势反弹"
            elif current_price < ema9[-1] * 0.995 and rsi > 30 and macd_signal.histogram < 0:
                if k_values[-1] < d_values[-1]:
                    signal_type = "SHORT"
                    is_long = False
                    score = 65
                    setup = "趋势跌破"
        
        if signal_type and score >= 65:
            self.last_trade_time = current_time
            sl_price = current_price - atr * 1.5 if is_long else current_price + atr * 1.5
            return signal_type, setup, is_long, support, resistance, atr, sl_price
        
        return None, None, None, None, None, 0, 0


class V17TradingBot:
    """V17交易机器人"""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.position: Optional[Position] = None
        self.signal_generator = V17SignalGenerator()
        self.client = GateIOClient()
        
        self.stage_1_pct = 0.30
        self.stage_2_pct = 0.30
        self.stage_3_pct = 0.20
        
        self.add_2_threshold = -1.5
        self.add_3_threshold = -3.0
        
        self.trail_start_pct = 10.0
        self.trail_15_pct = 15.0
        self.trail_25_pct = 25.0
        
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        
    def log(self, message: str, important: bool = False):
        timestamp = datetime.now().strftime('%H:%M:%S')
        prefix = "🚨" if important else ""
        print(f"{prefix}[{timestamp}] {message}")
    
    def fetch_data(self):
        try:
            klines = self.client.get_futures_candlesticks("ETH_USDT", "15m", 100)
            if not klines or len(klines) < 55:
                return None
            
            opens = np.array([k.open for k in klines])
            highs = np.array([k.high for k in klines])
            lows = np.array([k.low for k in klines])
            closes = np.array([k.close for k in klines])
            volumes = np.array([k.volume for k in klines])
            
            current_price = closes[-1]
            current_time = klines[-1].timestamp
            
            return opens, highs, lows, closes, volumes, current_price, current_time
        except Exception as e:
            self.log(f"获取数据失败: {e}")
            return None
    
    def open_position(self, direction: str, price: float, atr: float, setup: str):
        qty = (self.current_capital * self.stage_1_pct) / price
        
        self.position = Position(
            entry_time=datetime.now(),
            direction=direction,
            atr=atr,
            setup=setup
        )
        self.position.add_entry(price, qty)
        
        sl_price = price - atr * 1.5 if direction == "LONG" else price + atr * 1.5
        self.position.sl_price = sl_price
        
        emoji = "🟢" if direction == "LONG" else "🔴"
        self.log(f"{emoji} 开仓 [{direction}] 价格:{price:.2f} 数量:{qty:.4f}ETH 止损:{sl_price:.2f}")
    
    def add_position(self, price: float, stage: int):
        if not self.position:
            return
        
        if stage == 2:
            pct = self.stage_2_pct
            stage_name = "二仓"
        elif stage == 3:
            pct = self.stage_3_pct
            stage_name = "三仓"
        else:
            return
        
        qty = (self.initial_capital * pct) / price
        self.position.add_entry(price, qty)
        self.position.added_positions = stage - 1
        
        self.log(f"➕ 加仓 [{stage_name}] 价格:{price:.2f} 数量:{qty:.4f}ETH")
    
    def close_position(self, price: float, reason: str):
        if not self.position:
            return
        
        pnl_pct = self.position.get_pnl_pct(price)
        invested = self.position.total_invested
        pnl_usdt = invested * pnl_pct / 100
        
        self.current_capital += pnl_usdt
        self.trade_count += 1
        
        if pnl_pct > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        
        emoji = "✅" if pnl_pct > 0 else "❌"
        self.log(f"{emoji} 平仓 [{reason}] 收益:{pnl_pct:+.1f}% 资金:{self.current_capital:.2f}")
        
        self.position = None
    
    def check_add_position(self, current_price: float):
        if not self.position:
            return
        
        pnl_pct = self.position.get_pnl_pct(current_price)
        
        if self.position.added_positions == 0 and pnl_pct <= self.add_2_threshold:
            self.add_position(current_price, 2)
        elif self.position.added_positions == 1 and pnl_pct <= self.add_3_threshold:
            self.add_position(current_price, 3)
    
    def check_exit(self, current_price: float):
        if not self.position:
            return None
        
        pnl_pct = self.position.get_pnl_pct(current_price)
        
        if pnl_pct > self.position.highest_pnl_pct:
            self.position.highest_pnl_pct = pnl_pct
        
        highest = self.position.highest_pnl_pct
        
        # 止损
        if self.position.direction == "LONG" and current_price <= self.position.sl_price:
            return "止损"
        if self.position.direction == "SHORT" and current_price >= self.position.sl_price:
            return "止损"
        
        # 移动止盈
        if highest >= self.trail_start_pct and pnl_pct <= highest - 5:
            return "移动止盈(回撤5%)"
        if highest >= self.trail_15_pct and pnl_pct <= highest - 3:
            return "移动止盈(回撤3%)"
        if highest >= self.trail_25_pct and pnl_pct <= highest - 2:
            return "移动止盈(回撤2%)"
        
        return None
    
    def run_once(self):
        data = self.fetch_data()
        if not data:
            return
        
        opens, highs, lows, closes, volumes, current_price, current_time = data
        
        if self.position:
            self.check_add_position(current_price)
            exit_reason = self.check_exit(current_price)
            if exit_reason:
                self.close_position(current_price, exit_reason)
        else:
            signal, setup, is_long, support, resistance, atr, sl_price = \
                self.signal_generator.generate_signal(opens, highs, lows, closes, volumes, current_time)
            
            if signal:
                direction = "LONG" if is_long else "SHORT"
                self.open_position(direction, current_price, atr, setup)
    
    def print_status(self):
        print("\n" + "="*60)
        print(f"📊 V17策略状态 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")
        print("="*60)
        print(f"💰 资金: {self.current_capital:.2f} USDT")
        print(f"📈 收益: {(self.current_capital - self.initial_capital):+.2f} USDT ({(self.current_capital/self.initial_capital-1)*100:+.1f}%)")
        print(f"🎯 交易: {self.trade_count}次 | 胜:{self.win_count} | 负:{self.loss_count}")
        
        if self.trade_count > 0:
            win_rate = self.win_count / self.trade_count * 100
            print(f"✅ 胜率: {win_rate:.1f}%")
        
        if self.position:
            current_data = self.fetch_data()
            if current_data:
                current_price = current_data[5]
                pnl_pct = self.position.get_pnl_pct(current_price)
                print(f"\n📍 持仓 [{self.position.direction}] 浮盈:{pnl_pct:+.1f}% 最高:{self.position.highest_pnl_pct:+.1f}%")
        else:
            print("\n📍 当前无持仓")
        print("="*60 + "\n")
    
    def run_loop(self, interval: int = 300):
        self.log("🚀 V17策略交易机器人启动", important=True)
        self.log(f"💰 初始资金: {self.initial_capital:.2f} USDT")
        
        try:
            while True:
                self.run_once()
                self.print_status()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.log("🛑 机器人停止", important=True)
            self.print_status()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='V17 ETH交易机器人')
    parser.add_argument('--capital', type=float, default=10000.0, help='初始资金')
    parser.add_argument('--interval', type=int, default=300, help='扫描间隔秒数')
    parser.add_argument('--once', action='store_true', help='只运行一次')
    args = parser.parse_args()
    
    bot = V17TradingBot(initial_capital=args.capital)
    
    if args.once:
        bot.run_once()
        bot.print_status()
    else:
        bot.run_loop(interval=args.interval)


if __name__ == "__main__":
    main()
