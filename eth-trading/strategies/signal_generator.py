#!/usr/bin/env python3
"""
ETHUSDT交易策略信号生成器
多指标共振 + 价格位置分析
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from strategies.indicators import (
    TechnicalIndicators, TrendDirection,
    RSISignal, KDJSignal, MACDSignal, BollingerSignal, VolumeSignal
)
from config.strategy_config import (
    CONFIG, SignalType, TrendStrength, get_profit_target
)


@dataclass
class TradingSignal:
    """交易信号"""
    type: SignalType
    strength: float                     # 信号强度 0-100
    price: float
    timestamp: datetime
    reason: str
    targets: Dict[str, float]           # 止盈止损目标
    position_size: float                # 建议仓位
    
    def __str__(self):
        emoji = {
            SignalType.LONG: "🟢",
            SignalType.SHORT: "🔴",
            SignalType.CLOSE_LONG: "📗",
            SignalType.CLOSE_SHORT: "📕",
            SignalType.HOLD: "⏸️"
        }.get(self.type, "⚪")
        
        return f"{emoji} {self.type.value} | 强度:{self.strength:.0f} | 价格:{self.price:.2f} | {self.reason}"


@dataclass
class MarketContext:
    """市场环境"""
    trend: TrendDirection
    trend_strength: TrendStrength
    volatility: float                   # 波动率
    price_position: float               # 日内价格位置 0-1
    is_ranging: bool                    # 是否震荡市


class SignalGenerator:
    """信号生成器"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_signal_time = None
        self.daily_high = None
        self.daily_low = None
        self.daily_open = None
    
    def calculate_all_indicators(self, 
                                  opens: List[float],
                                  highs: List[float], 
                                  lows: List[float],
                                  closes: List[float],
                                  volumes: List[float]) -> Dict:
        """计算所有技术指标"""
        
        # RSI
        rsi_values = self.indicators.calculate_rsi(closes, CONFIG.rsi.period)
        rsi_signal = self.indicators.analyze_rsi(
            closes, rsi_values, 
            CONFIG.rsi.overbought, CONFIG.rsi.oversold
        )
        
        # KDJ
        k, d, j = self.indicators.calculate_kdj(
            highs, lows, closes,
            CONFIG.kdj.k_period, CONFIG.kdj.d_period, CONFIG.kdj.j_period
        )
        kdj_signal = self.indicators.analyze_kdj(k, d, j)
        
        # MACD
        macd, signal, hist = self.indicators.calculate_macd(
            closes, CONFIG.macd.fast, CONFIG.macd.slow, CONFIG.macd.signal
        )
        macd_signal = self.indicators.analyze_macd(macd, signal, hist)
        
        # 布林带
        upper, middle, lower = self.indicators.calculate_bollinger(
            closes, CONFIG.bollinger.period, CONFIG.bollinger.std_dev
        )
        boll_signal = self.indicators.analyze_bollinger(
            closes[-1], upper, middle, lower, CONFIG.bollinger.touch_threshold
        )
        
        # 成交量
        vol_signal = self.indicators.analyze_volume(
            volumes[-1], volumes, CONFIG.volume.ma_period, CONFIG.volume.spike_threshold
        )
        
        return {
            'rsi': rsi_signal,
            'kdj': kdj_signal,
            'macd': macd_signal,
            'bollinger': boll_signal,
            'volume': vol_signal,
            'closes': closes,
            'highs': highs,
            'lows': lows,
            'volumes': volumes
        }
    
    def analyze_market_context(self, indicators: Dict) -> MarketContext:
        """分析市场环境"""
        closes = indicators['closes']
        
        # 计算波动率（20周期标准差/均值）
        if len(closes) >= 20:
            recent = closes[-20:]
            volatility = (max(recent) - min(recent)) / sum(recent) * len(recent)
        else:
            volatility = 0.02
        
        # 判断趋势强度
        macd = indicators['macd']
        rsi = indicators['rsi']
        
        trend_strength = TrendStrength.NONE
        if macd.trend == rsi.trend and macd.trend != TrendDirection.NEUTRAL:
            if abs(macd.histogram) > 0.5 and abs(rsi.value - 50) > 20:
                trend_strength = TrendStrength.STRONG
            elif abs(macd.histogram) > 0.2 and abs(rsi.value - 50) > 10:
                trend_strength = TrendStrength.MODERATE
            else:
                trend_strength = TrendStrength.WEAK
        
        # 判断趋势方向
        trend = macd.trend
        if trend == TrendDirection.NEUTRAL:
            trend = rsi.trend
        
        # 判断是否震荡市
        is_ranging = trend_strength == TrendStrength.NONE or trend_strength == TrendStrength.WEAK
        
        # 计算日内价格位置
        if self.daily_high and self.daily_low:
            price_position = (closes[-1] - self.daily_low) / (self.daily_high - self.daily_low)
        else:
            price_position = 0.5
        
        return MarketContext(
            trend=trend,
            trend_strength=trend_strength,
            volatility=volatility,
            price_position=price_position,
            is_ranging=is_ranging
        )
    
    def calculate_signal_score(self, 
                               indicators: Dict,
                               context: MarketContext,
                               is_long: bool) -> Tuple[float, str]:
        """
        计算信号评分
        
        Returns:
            (分数, 理由)
        """
        score = 0.0
        reasons = []
        weights = CONFIG.signal_score.weights
        
        rsi = indicators['rsi']
        kdj = indicators['kdj']
        macd = indicators['macd']
        boll = indicators['bollinger']
        vol = indicators['volume']
        
        # 1. RSI评分 (0-100)
        rsi_score = 0
        if is_long:
            if rsi.is_oversold:
                rsi_score = 100 if rsi.divergence == "bullish" else 80
                reasons.append(f"RSI超卖({rsi.value:.1f})")
            elif rsi.value < 40:
                rsi_score = 60
            elif rsi.trend == TrendDirection.UP:
                rsi_score = 40
        else:  # 做空
            if rsi.is_overbought:
                rsi_score = 100 if rsi.divergence == "bearish" else 80
                reasons.append(f"RSI超买({rsi.value:.1f})")
            elif rsi.value > 60:
                rsi_score = 60
            elif rsi.trend == TrendDirection.DOWN:
                rsi_score = 40
        
        if rsi.divergence:
            rsi_score += 10
            reasons.append(f"RSI{'底' if rsi.divergence == 'bullish' else '顶'}背离")
        
        score += rsi_score * weights['rsi']
        
        # 2. KDJ评分
        kdj_score = 0
        if is_long:
            if kdj.golden_cross and kdj.k < 50:
                kdj_score = 100
                reasons.append("KDJ低位金叉")
            elif kdj.is_oversold:
                kdj_score = 70
                reasons.append(f"KDJ超卖(J={kdj.j:.1f})")
            elif kdj.j > kdj.k > kdj.d:
                kdj_score = 50
        else:
            if kdj.dead_cross and kdj.k > 50:
                kdj_score = 100
                reasons.append("KDJ高位死叉")
            elif kdj.is_overbought:
                kdj_score = 70
                reasons.append(f"KDJ超买(J={kdj.j:.1f})")
            elif kdj.j < kdj.k < kdj.d:
                kdj_score = 50
        
        score += kdj_score * weights['kdj']
        
        # 3. MACD评分
        macd_score = 0
        if is_long:
            if macd.cross_up:
                macd_score = 100
                reasons.append("MACD金叉")
            elif macd.trend == TrendDirection.UP and macd.histogram_expanding:
                macd_score = 70
                reasons.append("MACD红柱扩大")
            elif macd.histogram > 0:
                macd_score = 50
        else:
            if macd.cross_down:
                macd_score = 100
                reasons.append("MACD死叉")
            elif macd.trend == TrendDirection.DOWN and macd.histogram_expanding:
                macd_score = 70
                reasons.append("MACD绿柱扩大")
            elif macd.histogram < 0:
                macd_score = 50
        
        score += macd_score * weights['macd']
        
        # 4. 布林带评分
        boll_score = 0
        if is_long:
            if boll.touch_lower:
                boll_score = 100
                reasons.append("触碰布林带下轨")
            elif boll.position < 0.2:
                boll_score = 70
                reasons.append("价格接近下轨")
        else:
            if boll.touch_upper:
                boll_score = 100
                reasons.append("触碰布林带上轨")
            elif boll.position > 0.8:
                boll_score = 70
                reasons.append("价格接近上轨")
        
        score += boll_score * weights['bollinger']
        
        # 5. 成交量评分
        vol_score = 0
        if vol.is_spike:
            vol_score = 100
            reasons.append("成交量放量")
        elif vol.trend_confirmation:
            vol_score = 60
        
        score += vol_score * weights['volume']
        
        # 6. 价格位置评分
        position_score = 0
        if is_long and context.price_position <= CONFIG.price_position.low_zone:
            position_score = 100
            reasons.append(f"价格低位({context.price_position:.1%})")
        elif not is_long and context.price_position >= CONFIG.price_position.high_zone:
            position_score = 100
            reasons.append(f"价格高位({context.price_position:.1%})")
        elif context.price_position < 0.5 and is_long:
            position_score = 50
        elif context.price_position > 0.5 and not is_long:
            position_score = 50
        
        score += position_score * weights['price_position']
        
        # 环境修正
        if context.is_ranging:
            score *= 1.2  # 震荡市更适合反转策略
            reasons.append("震荡市加成")
        
        return min(score, 100), " | ".join(reasons)
    
    def generate_signal(self, 
                       opens: List[float],
                       highs: List[float],
                       lows: List[float],
                       closes: List[float],
                       volumes: List[float],
                       current_position: Optional[str] = None) -> TradingSignal:
        """
        生成交易信号
        
        Args:
            opens, highs, lows, closes, volumes: K线数据
            current_position: 当前持仓状态 ("long", "short", None)
        
        Returns:
            TradingSignal
        """
        current_price = closes[-1]
        now = datetime.now()
        
        # 计算所有指标
        indicators = self.calculate_all_indicators(opens, highs, lows, closes, volumes)
        
        # 分析市场环境
        context = self.analyze_market_context(indicators)
        
        # 更新日内高低点
        if self.daily_high is None or max(highs) > self.daily_high:
            self.daily_high = max(highs)
        if self.daily_low is None or min(lows) < self.daily_low:
            self.daily_low = min(lows)
        
        # 检查冷却时间
        if self.last_signal_time:
            minutes_since_last = (now - self.last_signal_time).total_seconds() / 60
            if minutes_since_last < CONFIG.risk.cooldown_minutes:
                return TradingSignal(
                    type=SignalType.HOLD,
                    strength=0,
                    price=current_price,
                    timestamp=now,
                    reason=f"冷却中 ({CONFIG.risk.cooldown_minutes - minutes_since_last:.0f}分钟)",
                    targets={},
                    position_size=0
                )
        
        # 计算做多和做空信号分数
        long_score, long_reason = self.calculate_signal_score(indicators, context, is_long=True)
        short_score, short_reason = self.calculate_signal_score(indicators, context, is_long=False)
        
        # 决策逻辑
        signal_type = SignalType.HOLD
        strength = 0
        reason = ""
        is_long = None
        
        # 做多条件
        if long_score >= CONFIG.signal_score.min_score_to_enter:
            if current_position == "short":
                signal_type = SignalType.CLOSE_SHORT
                strength = long_score
                reason = f"平空做多信号 | {long_reason}"
                is_long = True
            elif current_position is None:
                signal_type = SignalType.LONG
                strength = long_score
                reason = f"做多信号 | {long_reason}"
                is_long = True
        
        # 做空条件
        elif short_score >= CONFIG.signal_score.min_score_to_enter:
            if current_position == "long":
                signal_type = SignalType.CLOSE_LONG
                strength = short_score
                reason = f"平多做空信号 | {short_reason}"
                is_long = False
            elif current_position is None:
                signal_type = SignalType.SHORT
                strength = short_score
                reason = f"做空信号 | {short_reason}"
                is_long = False
        
        # 如果已经在持仓中，检查是否需要平仓
        else:
            if current_position == "long":
                if short_score > long_score + 20:  # 做空信号明显强于做多
                    signal_type = SignalType.CLOSE_LONG
                    strength = short_score
                    reason = f"平多信号(反手做空) | {short_reason}"
                else:
                    reason = f"持仓观望 | 多:{long_score:.0f} 空:{short_score:.0f}"
            elif current_position == "short":
                if long_score > short_score + 20:
                    signal_type = SignalType.CLOSE_SHORT
                    strength = long_score
                    reason = f"平空信号(反手做多) | {long_reason}"
                else:
                    reason = f"持仓观望 | 多:{long_score:.0f} 空:{short_score:.0f}"
            else:
                reason = f"观望 | 多:{long_score:.0f} 空:{short_score:.0f}"
        
        # 计算目标价格
        targets = {}
        if is_long is not None:
            profit_config = get_profit_target(context.price_position, is_long)
            
            if is_long:
                targets['take_profit'] = current_price * (1 + profit_config['optimal'])
                targets['stop_loss'] = current_price * (1 - CONFIG.risk.stop_loss_pct)
            else:
                targets['take_profit'] = current_price * (1 - profit_config['optimal'])
                targets['stop_loss'] = current_price * (1 + CONFIG.risk.stop_loss_pct)
            
            targets['leveraged_return'] = profit_config['leveraged_return']
        
        # 计算仓位大小
        position_size = 0
        if signal_type in [SignalType.LONG, SignalType.SHORT]:
            # 简化计算：使用信号强度调整仓位
            position_value = CONFIG.leverage.max_position_value * (strength / 100)
            position_size = position_value / current_price
        
        # 记录信号时间
        if signal_type not in [SignalType.HOLD]:
            self.last_signal_time = now
        
        return TradingSignal(
            type=signal_type,
            strength=strength,
            price=current_price,
            timestamp=now,
            reason=reason,
            targets=targets,
            position_size=round(position_size, 4)
        )
    
    def get_market_summary(self, indicators: Dict, context: MarketContext) -> str:
        """获取市场摘要"""
        rsi = indicators['rsi']
        kdj = indicators['kdj']
        macd = indicators['macd']
        boll = indicators['bollinger']
        
        lines = [
            f"📊 市场环境: {context.trend.value} | 强度: {context.trend_strength.name}",
            f"📍 价格位置: {context.price_position:.1%} | 波动率: {context.volatility:.2%}",
            f"📈 RSI: {rsi.value:.1f} ({'超买' if rsi.is_overbought else '超卖' if rsi.is_oversold else '正常'})",
            f"📈 KDJ: K={kdj.k:.1f} D={kdj.d:.1f} J={kdj.j:.1f}",
            f"📈 MACD: {macd.macd:.4f} | 柱状图: {macd.histogram:.4f}",
            f"📈 布林带: {boll.position:.1%} 位置 | {'触碰上轨' if boll.touch_upper else '触碰下轨' if boll.touch_lower else '中轨附近'}",
        ]
        
        return "\n".join(lines)


if __name__ == "__main__":
    # 测试信号生成
    import numpy as np
    
    print("ETHUSDT 交易信号生成测试")
    print("=" * 60)
    
    # 生成模拟数据 - 模拟高位回调场景
    np.random.seed(42)
    n = 100
    base_price = 3500
    
    # 先上涨到高位
    closes = []
    for i in range(n):
        if i < 70:
            price = base_price + i * 5 + np.random.randn() * 10  # 上涨
        else:
            price = base_price + 350 - (i-70) * 3 + np.random.randn() * 15  # 回调
        closes.append(price)
    
    highs = [c + abs(np.random.randn() * 8) for c in closes]
    lows = [c - abs(np.random.randn() * 8) for c in closes]
    opens = [closes[i-1] if i > 0 else c for i, c in enumerate(closes)]
    volumes = [10000 + np.random.randn() * 2000 for _ in range(n)]
    
    # 创建信号生成器
    generator = SignalGenerator()
    
    # 模拟日内数据
    generator.daily_high = max(highs[-20:])
    generator.daily_low = min(lows[-20:])
    
    # 生成信号
    signal = generator.generate_signal(opens, highs, lows, closes, volumes)
    
    print(f"\n当前价格: {closes[-1]:.2f}")
    print(f"日内高点: {generator.daily_high:.2f}")
    print(f"日内低点: {generator.daily_low:.2f}")
    print(f"\n{signal}")
    
    if signal.targets:
        print(f"\n🎯 目标设置:")
        for key, value in signal.targets.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
    
    # 计算指标
    indicators = generator.calculate_all_indicators(opens, highs, lows, closes, volumes)
    context = generator.analyze_market_context(indicators)
    
    print(f"\n{generator.get_market_summary(indicators, context)}")
