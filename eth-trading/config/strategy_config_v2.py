#!/usr/bin/env python3
"""
ETHUSDT永续合约高频交易策略配置 V2
优化目标：每天1-2次交易，周收益30%+
策略：短线波段 + 多指标共振 + 快速止盈止损
杠杆：10x
时间周期：15分钟K线 + 5分钟确认
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class SignalType(Enum):
    """信号类型"""
    LONG = "做多"
    SHORT = "做空"
    CLOSE_LONG = "平多"
    CLOSE_SHORT = "平空"
    HOLD = "持仓观望"


class TrendStrength(Enum):
    """趋势强度"""
    STRONG = 3
    MODERATE = 2
    WEAK = 1
    NONE = 0


@dataclass
class LeverageConfig:
    """杠杆配置"""
    leverage: int = 10                          # 固定10倍杠杆
    max_position_value: float = 2000.0          # 最大仓位提高到2000 USDT
    margin_ratio_threshold: float = 0.7         # 保证金率阈值降低


@dataclass
class TimeframeConfig:
    """时间周期配置"""
    primary: str = "15m"                        # 主周期：15分钟
    secondary: str = "5m"                       # 辅助周期：5分钟
    daily: str = "1d"
    lookback_periods: int = 96


@dataclass
class RSIConfig:
    """RSI指标配置 - 更敏感的阈值"""
    period: int = 14
    overbought: int = 65                        # 降低超买阈值
    oversold: int = 35                          # 降低超卖阈值
    extreme_overbought: int = 75
    extreme_oversold: int = 25
    divergence_lookback: int = 3                # 缩短背离检测周期


@dataclass
class KDJConfig:
    """KDJ指标配置"""
    k_period: int = 9
    d_period: int = 3
    j_period: int = 3
    overbought: int = 75                        # 降低阈值
    oversold: int = 25                          # 降低阈值
    golden_cross_threshold: int = 60            # 金叉阈值降低
    dead_cross_threshold: int = 40              # 死叉阈值降低


@dataclass
class MACDConfig:
    """MACD指标配置"""
    fast: int = 12
    slow: int = 26
    signal: int = 9
    histogram_threshold: float = 0.3            # 降低柱状图阈值


@dataclass
class BollingerConfig:
    """布林带配置"""
    period: int = 20
    std_dev: float = 2.0
    touch_threshold: float = 0.002              # 触碰阈值放宽到0.2%


@dataclass
class VolumeConfig:
    """成交量配置"""
    ma_period: int = 10                         # 缩短均线周期
    spike_threshold: float = 1.5                # 放量阈值降低
    confirmation_ratio: float = 1.2


@dataclass
class PricePositionConfig:
    """日内价格位置配置 - 放宽区间"""
    high_zone: float = 0.65                     # 高位区间降低
    low_zone: float = 0.35                      # 低位区间提高
    
    profit_targets: Dict[str, Dict] = field(default_factory=lambda: {
        "high_zone_short": {
            "min": 0.012,                       # 1.2%
            "optimal": 0.018,                   # 1.8%
            "leveraged_return": 0.18            # 18%
        },
        "low_zone_long": {
            "min": 0.012,
            "optimal": 0.018,
            "leveraged_return": 0.18
        },
        "mid_zone": {
            "min": 0.008,                       # 0.8%
            "optimal": 0.012,                   # 1.2%
            "leveraged_return": 0.12            # 12%
        }
    })


@dataclass
class RiskConfig:
    """风险控制配置 - 更激进的设置"""
    # 止损设置 - 更紧的止损
    stop_loss_pct: float = 0.005                # 止损0.5%
    max_stop_loss_pct: float = 0.010            # 最大止损1%
    trailing_stop_pct: float = 0.003            # 移动止损0.3%
    
    # 止盈设置 - 盈亏比3:1
    take_profit_ratio: float = 3.0              # 盈亏比3:1
    partial_close_ratio: float = 0.5
    
    # 仓位管理
    max_daily_trades: int = 15                  # 每日最多15次
    max_concurrent_positions: int = 1           # 同时只持1个仓位
    cooldown_minutes: int = 8                   # 冷却8分钟
    
    # 风险限额
    max_daily_loss_pct: float = 0.08            # 日最大亏损8%
    max_drawdown_pct: float = 0.15              # 最大回撤15%


@dataclass
class SignalScoreConfig:
    """信号评分配置 - 大幅降低阈值"""
    weights: Dict[str, float] = field(default_factory=lambda: {
        "rsi": 0.25,                            # RSI权重提高
        "kdj": 0.20,
        "macd": 0.15,
        "bollinger": 0.15,
        "volume": 0.10,
        "price_position": 0.15
    })
    
    # 信号阈值 - 大幅降低
    min_score_to_enter: float = 45.0            # 入场阈值45
    strong_score: float = 70.0                  # 强信号70
    exit_score: float = 25.0                    # 出场25


@dataclass
class TradingConfig:
    """交易配置总类"""
    symbol: str = "ETHUSDT"
    contract_type: str = "PERPETUAL"
    
    leverage: LeverageConfig = field(default_factory=LeverageConfig)
    timeframe: TimeframeConfig = field(default_factory=TimeframeConfig)
    rsi: RSIConfig = field(default_factory=RSIConfig)
    kdj: KDJConfig = field(default_factory=KDJConfig)
    macd: MACDConfig = field(default_factory=MACDConfig)
    bollinger: BollingerConfig = field(default_factory=BollingerConfig)
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    price_position: PricePositionConfig = field(default_factory=PricePositionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    signal_score: SignalScoreConfig = field(default_factory=SignalScoreConfig)
    
    binance_api: Dict = field(default_factory=lambda: {
        "base_url": "https://fapi.binance.com",
        "kline_endpoint": "/fapi/v1/klines",
        "ticker_endpoint": "/fapi/v1/ticker/24hr",
        "funding_rate_endpoint": "/fapi/v1/fundingRate",
        "timeout": 10
    })


# 全局配置实例
CONFIG = TradingConfig()


def get_profit_target(price_position_ratio: float, is_long: bool) -> Dict:
    """根据价格位置获取收益目标"""
    config = CONFIG.price_position
    
    if price_position_ratio >= config.high_zone and not is_long:
        return config.profit_targets["high_zone_short"]
    elif price_position_ratio <= config.low_zone and is_long:
        return config.profit_targets["low_zone_long"]
    else:
        return config.profit_targets["mid_zone"]


def calculate_position_size(available_margin: float, 
                           current_price: float,
                           signal_strength: float) -> float:
    """计算仓位大小"""
    config = CONFIG.leverage
    
    # 激进仓位：最大仓位 * 信号强度权重
    signal_weight = 0.7 + (signal_strength / 300)  # 0.7 - 1.03
    position_value = config.max_position_value * signal_weight
    
    max_value = available_margin * config.leverage
    position_value = min(position_value, max_value * 0.95)
    
    quantity = position_value / current_price
    quantity = round(quantity, 3)
    
    return quantity


if __name__ == "__main__":
    print("ETHUSDT高频策略配置 V2")
    print("=" * 50)
    print(f"杠杆倍数: {CONFIG.leverage.leverage}x")
    print(f"最大仓位: {CONFIG.leverage.max_position_value} USDT")
    print(f"入场阈值: {CONFIG.signal_score.min_score_to_enter}")
    print(f"止损: {CONFIG.risk.stop_loss_pct*100}% | 止盈: {CONFIG.price_position.profit_targets['mid_zone']['optimal']*100}%")
    print(f"冷却时间: {CONFIG.risk.cooldown_minutes}分钟")
    print(f"目标: 每天1-2次，周收益30%+")
