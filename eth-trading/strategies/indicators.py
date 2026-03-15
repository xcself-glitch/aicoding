#!/usr/bin/env python3
"""
技术指标计算模块
包含：RSI、KDJ、MACD、布林带、成交量分析
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class TrendDirection(Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


@dataclass
class RSISignal:
    """RSI信号"""
    value: float
    trend: TrendDirection
    divergence: Optional[str] = None  # "bullish", "bearish", None
    is_overbought: bool = False
    is_oversold: bool = False


@dataclass
class KDJSignal:
    """KDJ信号"""
    k: float
    d: float
    j: float
    golden_cross: bool = False      # 金叉
    dead_cross: bool = False        # 死叉
    is_overbought: bool = False
    is_oversold: bool = False


@dataclass
class MACDSignal:
    """MACD信号"""
    macd: float
    signal: float
    histogram: float
    trend: TrendDirection
    cross_up: bool = False
    cross_down: bool = False
    histogram_expanding: bool = False


@dataclass
class BollingerSignal:
    """布林带信号"""
    upper: float
    middle: float
    lower: float
    bandwidth: float
    position: float                 # 价格在布林带中的位置(0-1)
    touch_upper: bool = False
    touch_lower: bool = False
    squeeze: bool = False           # 布林带收缩


@dataclass
class VolumeSignal:
    """成交量信号"""
    current: float
    ma: float
    ratio: float                    # 当前/均线
    is_spike: bool = False          # 放量
    is_shrink: bool = False         # 缩量
    trend_confirmation: bool = False  # 趋势确认


class TechnicalIndicators:
    """技术指标计算器"""
    
    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> List[float]:
        """
        计算RSI指标
        
        Args:
            closes: 收盘价列表
            period: 周期
        
        Returns:
            RSI值列表
        """
        if len(closes) < period + 1:
            return [50.0] * len(closes)
        
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # 使用Wilder平滑
        avg_gain = np.convolve(gains, np.ones(period)/period, mode='valid')[0]
        avg_loss = np.convolve(losses, np.ones(period)/period, mode='valid')[0]
        
        rsi_values = []
        for i in range(period):
            rsi_values.append(50.0)  # 填充初始值
        
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))
        
        # 计算后续RSI
        for i in range(period + 1, len(closes)):
            delta = closes[i] - closes[i-1]
            gain = delta if delta > 0 else 0
            loss = -delta if delta < 0 else 0
            
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
            
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))
        
        return rsi_values
    
    @staticmethod
    def calculate_kdj(highs: List[float], 
                      lows: List[float], 
                      closes: List[float],
                      k_period: int = 9,
                      d_period: int = 3,
                      j_period: int = 3) -> Tuple[List[float], List[float], List[float]]:
        """
        计算KDJ指标
        
        Args:
            highs: 最高价列表
            lows: 最低价列表
            closes: 收盘价列表
            k_period, d_period, j_period: KDJ参数
        
        Returns:
            (K值列表, D值列表, J值列表)
        """
        if len(closes) < k_period:
            return [50.0] * len(closes), [50.0] * len(closes), [50.0] * len(closes)
        
        k_values = []
        d_values = []
        j_values = []
        
        # 初始化
        prev_k = 50.0
        prev_d = 50.0
        
        for i in range(len(closes)):
            if i < k_period - 1:
                k_values.append(50.0)
                d_values.append(50.0)
                j_values.append(50.0)
                continue
            
            # 计算RSV
            period_high = max(highs[i-k_period+1:i+1])
            period_low = min(lows[i-k_period+1:i+1])
            
            if period_high == period_low:
                rsv = 50.0
            else:
                rsv = (closes[i] - period_low) / (period_high - period_low) * 100
            
            # 计算K、D、J
            k = (2 * prev_k + rsv) / 3
            d = (2 * prev_d + k) / 3
            j = 3 * k - 2 * d
            
            k_values.append(k)
            d_values.append(d)
            j_values.append(j)
            
            prev_k = k
            prev_d = d
        
        return k_values, d_values, j_values
    
    @staticmethod
    def calculate_macd(closes: List[float],
                       fast: int = 12,
                       slow: int = 26,
                       signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
        """
        计算MACD指标
        
        Returns:
            (MACD线, 信号线, 柱状图)
        """
        if len(closes) < slow:
            zeros = [0.0] * len(closes)
            return zeros, zeros, zeros
        
        # 计算EMA
        def ema(data: List[float], period: int) -> List[float]:
            multiplier = 2 / (period + 1)
            ema_values = [data[0]]
            for price in data[1:]:
                ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
            return ema_values
        
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        
        # MACD线 = 快线EMA - 慢线EMA
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        
        # 信号线 = MACD的EMA
        signal_line = ema(macd_line, signal)
        
        # 柱状图 = MACD线 - 信号线
        histogram = [m - s for m, s in zip(macd_line, signal_line)]
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_bollinger(closes: List[float],
                           period: int = 20,
                           std_dev: float = 2.0) -> Tuple[List[float], List[float], List[float]]:
        """
        计算布林带
        
        Returns:
            (上轨, 中轨, 下轨)
        """
        if len(closes) < period:
            zeros = [closes[-1]] * len(closes) if closes else [0.0]
            return zeros, zeros, zeros
        
        upper_band = []
        middle_band = []
        lower_band = []
        
        for i in range(len(closes)):
            if i < period - 1:
                upper_band.append(closes[i])
                middle_band.append(closes[i])
                lower_band.append(closes[i])
            else:
                period_closes = closes[i-period+1:i+1]
                middle = np.mean(period_closes)
                std = np.std(period_closes)
                
                upper_band.append(middle + std_dev * std)
                middle_band.append(middle)
                lower_band.append(middle - std_dev * std)
        
        return upper_band, middle_band, lower_band
    
    @staticmethod
    def calculate_volume_ma(volumes: List[float], period: int = 20) -> List[float]:
        """计算成交量均线"""
        if len(volumes) < period:
            return volumes.copy()
        
        ma = []
        for i in range(len(volumes)):
            if i < period - 1:
                ma.append(np.mean(volumes[:i+1]))
            else:
                ma.append(np.mean(volumes[i-period+1:i+1]))
        return ma
    
    @staticmethod
    def detect_rsi_divergence(closes: List[float], 
                              rsi_values: List[float],
                              lookback: int = 5) -> Optional[str]:
        """
        检测RSI背离
        
        Returns:
            "bullish" - 底背离
            "bearish" - 顶背离
            None - 无背离
        """
        if len(closes) < lookback * 2 or len(rsi_values) < lookback * 2:
            return None
        
        # 最近的价格极值
        recent_closes = closes[-lookback:]
        recent_rsi = rsi_values[-lookback:]
        
        prev_closes = closes[-lookback*2:-lookback]
        prev_rsi = rsi_values[-lookback*2:-lookback]
        
        # 底背离：价格创新低，RSI未创新低
        if min(recent_closes) < min(prev_closes) and min(recent_rsi) > min(prev_rsi):
            return "bullish"
        
        # 顶背离：价格创新高，RSI未创新高
        if max(recent_closes) > max(prev_closes) and max(recent_rsi) < max(prev_rsi):
            return "bearish"
        
        return None
    
    @staticmethod
    def get_daily_price_position(current_price: float,
                                  daily_high: float,
                                  daily_low: float) -> float:
        """
        获取当前价格在日内的位置
        
        Returns:
            0-1之间的值，0表示最低，1表示最高
        """
        if daily_high == daily_low:
            return 0.5
        return (current_price - daily_low) / (daily_high - daily_low)
    
    @staticmethod
    def analyze_rsi(closes: List[float], 
                   rsi_values: List[float],
                   overbought: int = 70,
                   oversold: int = 30) -> RSISignal:
        """分析RSI信号"""
        if not rsi_values:
            return RSISignal(50.0, TrendDirection.NEUTRAL)
        
        current_rsi = rsi_values[-1]
        
        # 判断趋势
        if len(rsi_values) >= 3:
            if rsi_values[-1] > rsi_values[-2] > rsi_values[-3]:
                trend = TrendDirection.UP
            elif rsi_values[-1] < rsi_values[-2] < rsi_values[-3]:
                trend = TrendDirection.DOWN
            else:
                trend = TrendDirection.NEUTRAL
        else:
            trend = TrendDirection.NEUTRAL
        
        # 检测背离
        divergence = TechnicalIndicators.detect_rsi_divergence(closes, rsi_values)
        
        return RSISignal(
            value=current_rsi,
            trend=trend,
            divergence=divergence,
            is_overbought=current_rsi > overbought,
            is_oversold=current_rsi < oversold
        )
    
    @staticmethod
    def analyze_kdj(k_values: List[float],
                   d_values: List[float],
                   j_values: List[float],
                   overbought: int = 80,
                   oversold: int = 20) -> KDJSignal:
        """分析KDJ信号"""
        if not k_values or not d_values or not j_values:
            return KDJSignal(50.0, 50.0, 50.0)
        
        k, d, j = k_values[-1], d_values[-1], j_values[-1]
        
        # 检测金叉/死叉
        golden_cross = False
        dead_cross = False
        
        if len(k_values) >= 2 and len(d_values) >= 2:
            # 金叉：K上穿D
            if k_values[-2] < d_values[-2] and k > d:
                golden_cross = True
            # 死叉：K下穿D
            if k_values[-2] > d_values[-2] and k < d:
                dead_cross = True
        
        return KDJSignal(
            k=k, d=d, j=j,
            golden_cross=golden_cross,
            dead_cross=dead_cross,
            is_overbought=j > overbought,
            is_oversold=j < oversold
        )
    
    @staticmethod
    def analyze_macd(macd_line: List[float],
                    signal_line: List[float],
                    histogram: List[float]) -> MACDSignal:
        """分析MACD信号"""
        if not macd_line or not signal_line or not histogram:
            return MACDSignal(0.0, 0.0, 0.0, TrendDirection.NEUTRAL)
        
        macd, signal, hist = macd_line[-1], signal_line[-1], histogram[-1]
        
        # 判断趋势
        if len(histogram) >= 2:
            if histogram[-1] > histogram[-2] > 0:
                trend = TrendDirection.UP
            elif histogram[-1] < histogram[-2] < 0:
                trend = TrendDirection.DOWN
            else:
                trend = TrendDirection.NEUTRAL
            
            histogram_expanding = abs(histogram[-1]) > abs(histogram[-2])
        else:
            trend = TrendDirection.NEUTRAL
            histogram_expanding = False
        
        # 检测金叉/死叉
        cross_up = len(macd_line) >= 2 and macd_line[-2] < signal_line[-2] and macd > signal
        cross_down = len(macd_line) >= 2 and macd_line[-2] > signal_line[-2] and macd < signal
        
        return MACDSignal(
            macd=macd, signal=signal, histogram=hist,
            trend=trend,
            cross_up=cross_up,
            cross_down=cross_down,
            histogram_expanding=histogram_expanding
        )
    
    @staticmethod
    def analyze_bollinger(current_price: float,
                         upper: List[float],
                         middle: List[float],
                         lower: List[float],
                         touch_threshold: float = 0.001) -> BollingerSignal:
        """分析布林带信号"""
        if not upper or not middle or not lower:
            return BollingerSignal(current_price, current_price, current_price, 0, 0.5)
        
        up, mid, low = upper[-1], middle[-1], lower[-1]
        bandwidth = (up - low) / mid if mid > 0 else 0
        
        # 计算价格在布林带中的位置
        if up == low:
            position = 0.5
        else:
            position = (current_price - low) / (up - low)
        
        # 检测触碰轨道
        touch_upper = abs(current_price - up) / up < touch_threshold
        touch_lower = abs(current_price - low) / low < touch_threshold
        
        # 检测布林带收缩（可能预示大行情）
        squeeze = False
        if len(upper) >= 20:
            recent_bandwidth = [(upper[i] - lower[i]) / middle[i] 
                               for i in range(-20, 0) if middle[i] > 0]
            if recent_bandwidth:
                avg_bandwidth = np.mean(recent_bandwidth)
                squeeze = bandwidth < avg_bandwidth * 0.6
        
        return BollingerSignal(
            upper=up, middle=mid, lower=low,
            bandwidth=bandwidth,
            position=position,
            touch_upper=touch_upper,
            touch_lower=touch_lower,
            squeeze=squeeze
        )
    
    @staticmethod
    def analyze_volume(current_volume: float,
                      volumes: List[float],
                      period: int = 20,
                      spike_threshold: float = 2.0) -> VolumeSignal:
        """分析成交量信号"""
        if volumes is None or len(volumes) == 0:
            return VolumeSignal(current_volume, current_volume, 1.0)
        
        volume_ma = TechnicalIndicators.calculate_volume_ma(volumes, period)
        ma = volume_ma[-1] if volume_ma else current_volume
        
        ratio = current_volume / ma if ma > 0 else 1.0
        
        return VolumeSignal(
            current=current_volume,
            ma=ma,
            ratio=ratio,
            is_spike=ratio > spike_threshold,
            is_shrink=ratio < 0.5,
            trend_confirmation=ratio > 1.5
        )


if __name__ == "__main__":
    # 测试指标计算
    import random
    
    # 生成测试数据
    np.random.seed(42)
    n = 100
    closes = [100 + np.random.randn() * 2 + i * 0.1 for i in range(n)]
    highs = [c + abs(np.random.randn()) for c in closes]
    lows = [c - abs(np.random.randn()) for c in closes]
    volumes = [1000 + np.random.randn() * 200 for _ in range(n)]
    
    print("技术指标测试")
    print("=" * 50)
    
    # RSI
    rsi_values = TechnicalIndicators.calculate_rsi(closes)
    rsi_signal = TechnicalIndicators.analyze_rsi(closes, rsi_values)
    print(f"RSI: {rsi_signal.value:.2f}, 趋势: {rsi_signal.trend.value}")
    if rsi_signal.divergence:
        print(f"  背离: {rsi_signal.divergence}")
    
    # KDJ
    k, d, j = TechnicalIndicators.calculate_kdj(highs, lows, closes)
    kdj_signal = TechnicalIndicators.analyze_kdj(k, d, j)
    print(f"KDJ: K={kdj_signal.k:.2f}, D={kdj_signal.d:.2f}, J={kdj_signal.j:.2f}")
    if kdj_signal.golden_cross:
        print("  金叉信号!")
    if kdj_signal.dead_cross:
        print("  死叉信号!")
    
    # MACD
    macd, signal, hist = TechnicalIndicators.calculate_macd(closes)
    macd_signal = TechnicalIndicators.analyze_macd(macd, signal, hist)
    print(f"MACD: {macd_signal.macd:.4f}, 信号线: {macd_signal.signal:.4f}")
    print(f"  趋势: {macd_signal.trend.value}")
    
    # 布林带
    up, mid, low = TechnicalIndicators.calculate_bollinger(closes)
    boll_signal = TechnicalIndicators.analyze_bollinger(closes[-1], up, mid, low)
    print(f"布林带: 上={boll_signal.upper:.2f}, 中={boll_signal.middle:.2f}, 下={boll_signal.lower:.2f}")
    print(f"  带宽: {boll_signal.bandwidth:.4f}, 位置: {boll_signal.position:.2%}")
