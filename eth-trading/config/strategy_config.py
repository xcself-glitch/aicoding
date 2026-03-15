#!/usr/bin/env python3
"""
ETHUSDT永续合约高频交易策略配置
策略：日内反转捕捉 + 多指标共振
杠杆：10x
时间周期：15分钟K线
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
    STRONG = 3      # 强趋势
    MODERATE = 2    # 中等趋势
    WEAK = 1        # 弱趋势
    NONE = 0        # 无趋势


@dataclass
class LeverageConfig:
    """杠杆配置"""
    leverage: int = 10                          # 固定10倍杠杆
    max_position_value: float = 1000.0          # 最大仓位价值(USDT)
    margin_ratio_threshold: float = 0.8         # 保证金率阈值，低于此值减仓


@dataclass
class TimeframeConfig:
    """时间周期配置"""
    primary: str = "15m"                        # 主周期：15分钟
    secondary: str = "5m"                       # 辅助周期：5分钟
    daily: str = "1d"                           # 日线：判断日内位置
    lookback_periods: int = 96                  # 回看周期数(15m * 96 = 24小时)


@dataclass
class RSIConfig:
    """RSI指标配置"""
    period: int = 14
    overbought: int = 70                        # 超买阈值
    oversold: int = 30                          # 超卖阈值
    extreme_overbought: int = 80                # 极超买
    extreme_oversold: int = 20                  # 极超卖
    divergence_lookback: int = 5                # 背离检测回看周期


@dataclass
class KDJConfig:
    """KDJ指标配置"""
    k_period: int = 9
    d_period: int = 3
    j_period: int = 3
    overbought: int = 80
    oversold: int = 20
    golden_cross_threshold: int = 50            # 金叉有效性阈值
    dead_cross_threshold: int = 50              # 死叉有效性阈值


@dataclass
class MACDConfig:
    """MACD指标配置"""
    fast: int = 12
    slow: int = 26
    signal: int = 9
    histogram_threshold: float = 0.5            # 柱状图变化阈值


@dataclass
class BollingerConfig:
    """布林带配置"""
    period: int = 20
    std_dev: float = 2.0
    touch_threshold: float = 0.001              # 触碰轨道阈值(0.1%)


@dataclass
class VolumeConfig:
    """成交量配置"""
    ma_period: int = 20                         # 成交量均线周期
    spike_threshold: float = 2.0                # 放量阈值(2倍均量)
    confirmation_ratio: float = 1.5             # 确认放量比例


@dataclass
class PricePositionConfig:
    """日内价格位置配置"""
    # 价格区间划分
    high_zone: float = 0.75                     # 高位区间(日高-日低)
    low_zone: float = 0.25                      # 低位区间
    
    # 收益目标与价格位置的关系
    # 高位做空、低位做多的收益目标更高
    profit_targets: Dict[str, Dict] = field(default_factory=lambda: {
        "high_zone_short": {                    # 高位做空
            "min": 0.015,                       # 1.5%
            "optimal": 0.025,                   # 2.5%
            "leveraged_return": 0.15            # 15%杠杆收益
        },
        "low_zone_long": {                      # 低位做多
            "min": 0.015,
            "optimal": 0.025,
            "leveraged_return": 0.15
        },
        "mid_zone": {                           # 中间区域
            "min": 0.005,                       # 0.5%
            "optimal": 0.015,                   # 1.5%
            "leveraged_return": 0.08            # 8%杠杆收益
        }
    })


@dataclass
class RiskConfig:
    """风险控制配置"""
    # 止损设置
    stop_loss_pct: float = 0.008                # 基础止损0.8%
    max_stop_loss_pct: float = 0.015            # 最大止损1.5%
    trailing_stop_pct: float = 0.005            # 移动止损0.5%
    
    # 止盈设置
    take_profit_ratio: float = 2.0              # 盈亏比2:1
    partial_close_ratio: float = 0.5            # 部分止盈比例
    
    # 仓位管理
    max_daily_trades: int = 10                  # 每日最大交易次数
    max_concurrent_positions: int = 2           # 最大同时持仓数
    cooldown_minutes: int = 15                  # 交易冷却时间(分钟)
    
    # 风险限额
    max_daily_loss_pct: float = 0.05            # 日最大亏损5%
    max_drawdown_pct: float = 0.10              # 最大回撤10%


@dataclass
class SignalScoreConfig:
    """信号评分配置"""
    # 各指标权重
    weights: Dict[str, float] = field(default_factory=lambda: {
        "rsi": 0.20,
        "kdj": 0.20,
        "macd": 0.15,
        "bollinger": 0.15,
        "volume": 0.15,
        "price_position": 0.15
    })
    
    # 信号阈值
    min_score_to_enter: float = 70.0            # 最低入场分数
    strong_score: float = 85.0                  # 强信号分数
    exit_score: float = 30.0                    # 出场分数


@dataclass
class TradingConfig:
    """交易配置总类"""
    symbol: str = "ETHUSDT"
    contract_type: str = "PERPETUAL"            # 永续合约
    
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
    
    # API配置
    binance_api: Dict = field(default_factory=lambda: {
        "base_url": "https://fapi.binance.com",      # 合约API
        "kline_endpoint": "/fapi/v1/klines",
        "ticker_endpoint": "/fapi/v1/ticker/24hr",
        "funding_rate_endpoint": "/fapi/v1/fundingRate",
        "timeout": 10
    })


# 全局配置实例
CONFIG = TradingConfig()


def get_profit_target(price_position_ratio: float, is_long: bool) -> Dict:
    """
    根据价格位置获取收益目标
    
    Args:
        price_position_ratio: 价格在日内的位置(0-1)
        is_long: 是否做多
    
    Returns:
        收益目标配置
    """
    config = CONFIG.price_position
    
    # 高位区域且做空，或低位区域且做多 -> 高收益目标
    if price_position_ratio >= config.high_zone and not is_long:
        return config.profit_targets["high_zone_short"]
    elif price_position_ratio <= config.low_zone and is_long:
        return config.profit_targets["low_zone_long"]
    else:
        return config.profit_targets["mid_zone"]


def calculate_position_size(available_margin: float, 
                           current_price: float,
                           signal_strength: float) -> float:
    """
    计算仓位大小
    
    Args:
        available_margin: 可用保证金(USDT)
        current_price: 当前价格
        signal_strength: 信号强度(0-100)
    
    Returns:
        合约数量
    """
    config = CONFIG.leverage
    risk_config = CONFIG.risk
    
    # 基础仓位 = 最大仓位 * 信号强度权重
    signal_weight = 0.5 + (signal_strength / 200)  # 0.5 - 1.0
    position_value = config.max_position_value * signal_weight
    
    # 限制不超过可用保证金
    max_value = available_margin * config.leverage
    position_value = min(position_value, max_value * 0.9)  # 留10%缓冲
    
    # 计算合约数量
    quantity = position_value / current_price
    
    # 调整为合适的精度(ETH合约通常为0.001)
    quantity = round(quantity, 3)
    
    return quantity


if __name__ == "__main__":
    # 测试配置
    print("ETHUSDT永续合约策略配置")
    print("=" * 50)
    print(f"杠杆倍数: {CONFIG.leverage.leverage}x")
    print(f"时间周期: {CONFIG.timeframe.primary}")
    print(f"最大仓位: {CONFIG.leverage.max_position_value} USDT")
    print(f"基础止损: {CONFIG.risk.stop_loss_pct * 100}%")
    print()
    
    # 测试收益目标
    print("收益目标测试:")
    targets = [
        (0.9, False, "高位做空"),
        (0.1, True, "低位做多"),
        (0.5, True, "中间做多")
    ]
    for pos, is_long, desc in targets:
        target = get_profit_target(pos, is_long)
        print(f"  {desc}: 目标{target['optimal']*100}%, 杠杆收益{target['leveraged_return']*100}%")
