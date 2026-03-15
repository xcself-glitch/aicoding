#!/usr/bin/env python3
"""
ETHUSDT策略回测 - 过去7天
模拟交易并统计收益情况
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from strategies.gateio_client import GateIOClient, Candlestick
from strategies.indicators import TechnicalIndicators, TrendDirection
from config.strategy_config import CONFIG, SignalType, get_profit_target


@dataclass
class Trade:
    """交易记录"""
    entry_time: datetime
    exit_time: Optional[datetime] = None
    direction: str = ""  # LONG or SHORT
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    leverage: int = 10
    
    # 目标价
    tp_price: float = 0.0
    sl_price: float = 0.0
    
    # 结果
    pnl_pct: float = 0.0  # 收益率(杠杆后)
    pnl_usdt: float = 0.0
    exit_reason: str = ""
    
    def calculate_pnl(self):
        """计算盈亏"""
        if self.direction == "LONG":
            price_change = (self.exit_price - self.entry_price) / self.entry_price
        else:
            price_change = (self.entry_price - self.exit_price) / self.entry_price
        
        self.pnl_pct = price_change * self.leverage
        position_value = self.quantity * self.entry_price
        self.pnl_usdt = position_value * self.pnl_pct


@dataclass
class BacktestResult:
    """回测结果"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    total_return_pct: float = 0.0
    total_return_usdt: float = 0.0
    
    max_drawdown_pct: float = 0.0
    max_consecutive_losses: int = 0
    
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    
    win_rate: float = 0.0
    profit_factor: float = 0.0
    
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[tuple] = field(default_factory=list)


class SimpleSignalGenerator:
    """简化版信号生成器（用于回测）"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.daily_high = None
        self.daily_low = None
        
    def generate_signal(self, opens, highs, lows, closes, volumes):
        """生成信号 - 返回 (signal_type, score, reason, is_long)"""
        
        # 计算指标
        rsi_values = self.indicators.calculate_rsi(closes, CONFIG.rsi.period)
        rsi_signal = self.indicators.analyze_rsi(closes, rsi_values, CONFIG.rsi.overbought, CONFIG.rsi.oversold)
        
        k_values, d_values, j_values = self.indicators.calculate_kdj(highs, lows, closes, CONFIG.kdj.k_period, CONFIG.kdj.d_period, CONFIG.kdj.j_period)
        kdj_signal = self.indicators.analyze_kdj(k_values, d_values, j_values)
        k, d, j = k_values[-1], d_values[-1], j_values[-1]  # 获取最新值用于后续判断
        
        macd_line, signal_line, hist = self.indicators.calculate_macd(closes, CONFIG.macd.fast, CONFIG.macd.slow, CONFIG.macd.signal)
        macd_signal = self.indicators.analyze_macd(macd_line, signal_line, hist)
        
        upper, middle, lower = self.indicators.calculate_bollinger(closes, CONFIG.bollinger.period, CONFIG.bollinger.std_dev)
        boll_signal = self.indicators.analyze_bollinger(closes[-1], upper, middle, lower, CONFIG.bollinger.touch_threshold)
        
        vol_signal = self.indicators.analyze_volume(volumes[-1], volumes, CONFIG.volume.ma_period, CONFIG.volume.spike_threshold)
        
        current_price = closes[-1]
        
        # 计算日内价格位置
        if self.daily_high and self.daily_low:
            price_pos = (current_price - self.daily_low) / (self.daily_high - self.daily_low)
        else:
            price_pos = 0.5
        
        # 计算做多分数
        long_score = 0
        long_reasons = []
        
        if rsi_signal.is_oversold:
            long_score += 25
            long_reasons.append(f"RSI超卖({rsi_signal.value:.1f})")
        if rsi_signal.divergence == "bullish":
            long_score += 15
            long_reasons.append("RSI底背离")
        if kdj_signal.golden_cross and k_values[-1] < 50:
            long_score += 20
            long_reasons.append("KDJ金叉")
        if macd_signal.cross_up:
            long_score += 15
            long_reasons.append("MACD金叉")
        if boll_signal.touch_lower:
            long_score += 15
            long_reasons.append("触及布林带下轨")
        if price_pos <= 0.3:
            long_score += 10
            long_reasons.append(f"价格低位({price_pos:.1%})")
        if vol_signal.is_spike:
            long_score += 10
            long_reasons.append("放量")
            
        # 计算做空分数
        short_score = 0
        short_reasons = []
        
        if rsi_signal.is_overbought:
            short_score += 25
            short_reasons.append(f"RSI超买({rsi_signal.value:.1f})")
        if rsi_signal.divergence == "bearish":
            short_score += 15
            short_reasons.append("RSI顶背离")
        if kdj_signal.dead_cross and k_values[-1] > 50:
            short_score += 20
            short_reasons.append("KDJ死叉")
        if macd_signal.cross_down:
            short_score += 15
            short_reasons.append("MACD死叉")
        if boll_signal.touch_upper:
            short_score += 15
            short_reasons.append("触及布林带上轨")
        if price_pos >= 0.7:
            short_score += 10
            short_reasons.append(f"价格高位({price_pos:.1%})")
        if vol_signal.is_spike:
            short_score += 10
            short_reasons.append("放量")
        
        # 判断信号 - 回测使用较低阈值以观察更多信号
        min_score = 55  # 降低阈值到55
        
        if long_score >= min_score and long_score > short_score + 5:
            return SignalType.LONG, long_score, " | ".join(long_reasons), True
        elif short_score >= min_score and short_score > long_score + 5:
            return SignalType.SHORT, short_score, " | ".join(short_reasons), False
        else:
            reason = f"多:{long_score:.0f} 空:{short_score:.0f}"
            if long_reasons:
                reason += f" | 多信号: {long_reasons[0]}"
            elif short_reasons:
                reason += f" | 空信号: {short_reasons[0]}"
            return SignalType.HOLD, max(long_score, short_score), reason, None


class Backtester:
    """回测引擎"""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.equity_curve = []
        
    def fetch_historical_data(self, days: int = 7) -> List[Candlestick]:
        """获取历史K线数据"""
        client = GateIOClient()
        
        # 计算需要的K线数量 (15分钟K线, 7天 = 7 * 24 * 4 = 672根)
        limit = days * 24 * 4 + 100  # 多加100根用于指标计算
        
        print(f"📊 获取过去{days}天的15分钟K线数据 (约{limit}根)...")
        klines = client.get_futures_candlesticks("ETH_USDT", "15m", limit)
        
        if not klines or len(klines) < 100:
            print(f"❌ 数据获取失败，只获取到{len(klines)}根K线")
            return []
        
        print(f"✅ 成功获取{len(klines)}根K线")
        print(f"   时间范围: {datetime.fromtimestamp(klines[0].timestamp)} ~ {datetime.fromtimestamp(klines[-1].timestamp)}")
        
        return klines
    
    def run_backtest(self, klines: List[Candlestick]) -> BacktestResult:
        """运行回测"""
        result = BacktestResult()
        generator = SimpleSignalGenerator()
        
        # 记录当前持仓
        current_trade: Optional[Trade] = None
        last_trade_time = 0  # 上次交易时间戳
        cooldown_seconds = CONFIG.risk.cooldown_minutes * 60  # 冷却时间(秒)
        
        # 遍历K线 (从第50根开始，确保有足够数据计算指标)
        for i in range(50, len(klines)):
            current_kline = klines[i]
            current_time = datetime.fromtimestamp(current_kline.timestamp)
            current_price = current_kline.close
            
            # 准备历史数据
            hist_klines = klines[max(0, i-100):i+1]
            opens = np.array([k.open for k in hist_klines])
            highs = np.array([k.high for k in hist_klines])
            lows = np.array([k.low for k in hist_klines])
            closes = np.array([k.close for k in hist_klines])
            volumes = np.array([k.volume for k in hist_klines])
            
            # 计算日内高低点 (过去24小时 = 96根15分钟K线)
            day_lookback = min(96, len(hist_klines))
            day_high = max([k.high for k in hist_klines[-day_lookback:]])
            day_low = min([k.low for k in hist_klines[-day_lookback:]])
            generator.daily_high = day_high
            generator.daily_low = day_low
            
            # 记录权益曲线
            self.equity_curve.append((current_time, self.current_capital))
            
            # 检查是否有持仓需要平仓
            if current_trade:
                exit_trade = False
                exit_price = current_price
                exit_reason = ""
                
                # 检查止损
                if current_trade.direction == "LONG":
                    if current_kline.low <= current_trade.sl_price:
                        exit_price = current_trade.sl_price
                        exit_reason = "止损"
                        exit_trade = True
                    # 检查止盈
                    elif current_kline.high >= current_trade.tp_price:
                        exit_price = current_trade.tp_price
                        exit_reason = "止盈"
                        exit_trade = True
                else:  # SHORT
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
                    
                    # 更新资金
                    self.current_capital += current_trade.pnl_usdt
                    
                    result.trades.append(current_trade)
                    if current_trade.pnl_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    
                    print(f"   📤 平仓 [{exit_reason}] 收益: {current_trade.pnl_pct:+.2f}% ({current_trade.pnl_usdt:+.2f} USDT)")
                    
                    # 设置冷却时间
                    last_trade_time = current_kline.timestamp
                    
                    current_trade = None
            
            # 如果没有持仓且不在冷却期，检查开仓信号
            elif current_kline.timestamp >= last_trade_time + cooldown_seconds:
                signal_type, score, reason, is_long = generator.generate_signal(
                    opens, highs, lows, closes, volumes
                )
                
                if signal_type in [SignalType.LONG, SignalType.SHORT]:
                    direction = "LONG" if is_long else "SHORT"
                    
                    # 计算价格位置
                    price_pos = (current_price - day_low) / (day_high - day_low) if day_high != day_low else 0.5
                    profit_cfg = get_profit_target(price_pos, is_long)
                    
                    # 计算止盈止损价
                    if is_long:
                        tp = current_price * (1 + profit_cfg['optimal'])
                        sl = current_price * (1 - CONFIG.risk.stop_loss_pct)
                    else:
                        tp = current_price * (1 - profit_cfg['optimal'])
                        sl = current_price * (1 + CONFIG.risk.stop_loss_pct)
                    
                    # 计算仓位
                    position_value = min(
                        CONFIG.leverage.max_position_value,
                        self.current_capital * CONFIG.leverage.leverage * 0.5
                    )
                    quantity = position_value / current_price
                    quantity = round(quantity, 3)
                    
                    # 创建交易
                    trade = Trade(
                        entry_time=current_time,
                        direction=direction,
                        entry_price=current_price,
                        quantity=quantity,
                        leverage=CONFIG.leverage.leverage,
                        tp_price=tp,
                        sl_price=sl
                    )
                    
                    current_trade = trade
                    result.total_trades += 1
                    
                    print(f"\n📅 {current_time.strftime('%m-%d %H:%M')}")
                    print(f"   📥 开仓 [{direction}] 价格: {current_price:.2f}")
                    print(f"   📊 信号强度: {score:.0f} | {reason}")
                    print(f"   🎯 止盈: {tp:.2f} | 止损: {sl:.2f}")
        
        # 如果有未平仓的交易，按最后价格平仓
        if current_trade:
            last_price = klines[-1].close
            last_time = datetime.fromtimestamp(klines[-1].timestamp)
            current_trade.exit_time = last_time
            current_trade.exit_price = last_price
            current_trade.exit_reason = "回测结束"
            current_trade.calculate_pnl()
            self.current_capital += current_trade.pnl_usdt
            result.trades.append(current_trade)
            
            if current_trade.pnl_pct > 0:
                result.winning_trades += 1
            else:
                result.losing_trades += 1
        
        # 计算统计指标
        self._calculate_statistics(result)
        
        return result
    
    def _calculate_statistics(self, result: BacktestResult):
        """计算统计指标"""
        if result.total_trades == 0:
            return
        
        # 胜率
        result.win_rate = result.winning_trades / result.total_trades * 100
        
        # 收益统计
        wins = [t.pnl_pct for t in result.trades if t.pnl_pct > 0]
        losses = [t.pnl_pct for t in result.trades if t.pnl_pct <= 0]
        
        if wins:
            result.avg_win_pct = sum(wins) / len(wins)
        if losses:
            result.avg_loss_pct = sum(losses) / len(losses)
        
        # 总收益
        result.total_return_usdt = self.current_capital - self.initial_capital
        result.total_return_pct = result.total_return_usdt / self.initial_capital * 100
        
        # 盈亏比
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0.001
        result.profit_factor = total_wins / total_losses
        
        # 最大回撤
        peak = self.initial_capital
        max_dd = 0
        for _, capital in self.equity_curve:
            if capital > peak:
                peak = capital
            dd = (peak - capital) / peak
            max_dd = max(max_dd, dd)
        result.max_drawdown_pct = max_dd * 100
        
        result.equity_curve = self.equity_curve


def print_backtest_report(result: BacktestResult, initial_capital: float):
    """打印回测报告"""
    print("\n" + "="*70)
    print("📊 ETHUSDT 策略回测报告")
    print("="*70)
    
    print(f"\n💰 资金情况:")
    print(f"   初始资金: {initial_capital:.2f} USDT")
    print(f"   最终资金: {initial_capital + result.total_return_usdt:.2f} USDT")
    print(f"   总收益: {result.total_return_usdt:+.2f} USDT ({result.total_return_pct:+.2f}%)")
    
    print(f"\n📈 交易统计:")
    print(f"   总交易次数: {result.total_trades}")
    print(f"   盈利次数: {result.winning_trades}")
    print(f"   亏损次数: {result.losing_trades}")
    print(f"   胜率: {result.win_rate:.1f}%")
    print(f"   盈亏比: {result.profit_factor:.2f}")
    
    print(f"\n📉 收益统计:")
    print(f"   平均盈利: {result.avg_win_pct:+.2f}%")
    print(f"   平均亏损: {result.avg_loss_pct:+.2f}%")
    print(f"   最大回撤: {result.max_drawdown_pct:.2f}%")
    
    if result.trades:
        print(f"\n📋 详细交易记录:")
        print("-"*70)
        print(f"{'时间':<18} {'方向':<6} {'入场':<10} {'出场':<10} {'收益':<10} {'原因':<15}")
        print("-"*70)
        
        for trade in result.trades:
            entry_time = trade.entry_time.strftime("%m-%d %H:%M")
            direction = "多" if trade.direction == "LONG" else "空"
            pnl_str = f"{trade.pnl_pct:+.2f}%"
            exit_reason = trade.exit_reason[:12]
            print(f"{entry_time:<18} {direction:<6} {trade.entry_price:<10.2f} {trade.exit_price:<10.2f} {pnl_str:<10} {exit_reason:<15}")
    
    print("="*70)


def main():
    print("🚀 ETHUSDT 策略回测 - 过去7天")
    print("="*70)
    
    # 初始化回测引擎
    initial_capital = 10000.0
    backtester = Backtester(initial_capital)
    
    # 获取历史数据
    klines = backtester.fetch_historical_data(days=7)
    
    if not klines:
        print("❌ 无法获取历史数据")
        return
    
    # 运行回测
    print("\n🔄 开始回测...")
    result = backtester.run_backtest(klines)
    
    # 打印报告
    print_backtest_report(result, initial_capital)


if __name__ == "__main__":
    main()
