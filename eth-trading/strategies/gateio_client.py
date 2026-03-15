#!/usr/bin/env python3
"""
Gate.io API 客户端
支持现货和合约数据获取
"""

import requests
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime
import time


@dataclass
class Candlestick:
    """K线数据"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    
    @classmethod
    def from_gateio_futures(cls, data: Dict) -> "Candlestick":
        """从Gate.io合约数据解析"""
        return cls(
            timestamp=int(data.get('t', 0)),
            open=float(data.get('o', 0)),
            high=float(data.get('h', 0)),
            low=float(data.get('l', 0)),
            close=float(data.get('c', 0)),
            volume=float(data.get('v', 0)),
            amount=float(data.get('sum', 0))
        )
    
    @classmethod
    def from_gateio_spot(cls, data: List) -> "Candlestick":
        """从Gate.io现货数据解析 [timestamp, volume, close, high, low, open]"""
        return cls(
            timestamp=int(data[0]),
            volume=float(data[1]),
            close=float(data[2]),
            high=float(data[3]),
            low=float(data[4]),
            open=float(data[5]),
            amount=float(data[1]) * float(data[5]) if len(data) > 5 else 0
        )


@dataclass
class FuturesTicker:
    """合约行情数据"""
    last_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_percentage: float
    change_price: float
    funding_rate: float
    mark_price: float
    index_price: float
    volume_24h_base: float
    volume_24h_quote: float


@dataclass
class SpotTicker:
    """现货行情数据"""
    last_price: float
    high_24h: float
    low_24h: float
    base_volume: float
    quote_volume: float
    change_percentage: float
    highest_bid: float
    lowest_ask: float


class GateIOClient:
    """Gate.io API 客户端"""
    
    BASE_URL = "https://api.gateio.ws/api/v4"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        self.last_request_time = 0
        self.min_interval = 0.1  # 100ms between requests
    
    def _rate_limit(self):
        """简单的速率限制"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()
    
    def _get(self, endpoint: str, params: Dict = None) -> Optional[Any]:
        """发送GET请求"""
        self._rate_limit()
        try:
            url = f"{self.BASE_URL}{endpoint}"
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"API错误: {resp.status_code} - {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"请求异常: {e}")
            return None
    
    def get_futures_ticker(self, contract: str = "ETH_USDT") -> Optional[FuturesTicker]:
        """获取合约行情"""
        data = self._get("/futures/usdt/tickers", {"contract": contract})
        if data and len(data) > 0:
            ticker = data[0]
            return FuturesTicker(
                last_price=float(ticker.get('last', 0)),
                high_24h=float(ticker.get('high_24h', 0)),
                low_24h=float(ticker.get('low_24h', 0)),
                volume_24h=float(ticker.get('volume_24h', 0)),
                change_percentage=float(ticker.get('change_percentage', 0)),
                change_price=float(ticker.get('change_price', 0)),
                funding_rate=float(ticker.get('funding_rate', 0)),
                mark_price=float(ticker.get('mark_price', 0)),
                index_price=float(ticker.get('index_price', 0)),
                volume_24h_base=float(ticker.get('volume_24h_base', 0)),
                volume_24h_quote=float(ticker.get('volume_24h_quote', 0))
            )
        return None
    
    def get_futures_candlesticks(
        self, 
        contract: str = "ETH_USDT",
        interval: str = "15m",
        limit: int = 100
    ) -> List[Candlestick]:
        """获取合约K线数据"""
        params = {
            "contract": contract,
            "interval": interval,
            "limit": limit
        }
        data = self._get("/futures/usdt/candlesticks", params)
        if data:
            return [Candlestick.from_gateio_futures(c) for c in data]
        return []
    
    def get_spot_ticker(self, currency_pair: str = "ETH_USDT") -> Optional[SpotTicker]:
        """获取现货行情"""
        data = self._get("/spot/tickers", {"currency_pair": currency_pair})
        if data and len(data) > 0:
            ticker = data[0]
            return SpotTicker(
                last_price=float(ticker.get('last', 0)),
                high_24h=float(ticker.get('high_24h', 0)),
                low_24h=float(ticker.get('low_24h', 0)),
                base_volume=float(ticker.get('base_volume', 0)),
                quote_volume=float(ticker.get('quote_volume', 0)),
                change_percentage=float(ticker.get('change_percentage', 0)),
                highest_bid=float(ticker.get('highest_bid', 0)),
                lowest_ask=float(ticker.get('lowest_ask', 0))
            )
        return None
    
    def get_spot_candlesticks(
        self,
        currency_pair: str = "ETH_USDT",
        interval: str = "15m",
        limit: int = 100
    ) -> List[Candlestick]:
        """获取现货K线数据"""
        params = {
            "currency_pair": currency_pair,
            "interval": interval,
            "limit": limit
        }
        data = self._get("/spot/candlesticks", params)
        if data:
            return [Candlestick.from_gateio_spot(c) for c in data]
        return []
    
    def get_realtime_data_for_strategy(self, use_futures: bool = True) -> Optional[Dict]:
        """获取策略所需的完整实时数据"""
        try:
            if use_futures:
                # 获取合约数据
                ticker = self.get_futures_ticker("ETH_USDT")
                klines = self.get_futures_candlesticks("ETH_USDT", "15m", 100)
                
                if not ticker or not klines:
                    return None
                
                return {
                    'current_price': ticker.mark_price,
                    'ticker_24h': ticker,
                    'klines_15m': klines,
                    'funding_rate': ticker.funding_rate,
                    'source': 'gateio_futures'
                }
            else:
                # 获取现货数据
                ticker = self.get_spot_ticker("ETH_USDT")
                klines = self.get_spot_candlesticks("ETH_USDT", "15m", 100)
                
                if not ticker or not klines:
                    return None
                
                return {
                    'current_price': ticker.last_price,
                    'ticker_24h': ticker,
                    'klines_15m': klines,
                    'funding_rate': 0,
                    'source': 'gateio_spot'
                }
        except Exception as e:
            print(f"获取数据异常: {e}")
            return None


def klines_to_arrays(klines: List[Candlestick]) -> tuple:
    """将K线列表转换为numpy数组格式"""
    import numpy as np
    
    opens = np.array([k.open for k in klines])
    highs = np.array([k.high for k in klines])
    lows = np.array([k.low for k in klines])
    closes = np.array([k.close for k in klines])
    volumes = np.array([k.volume for k in klines])
    
    return opens, highs, lows, closes, volumes


# 兼容层：提供与BinanceClient相同的接口
class GateIOAdapter:
    """Gate.io 适配器，兼容 BinanceClient 接口"""
    
    def __init__(self):
        self.client = GateIOClient()
    
    def get_realtime_data_for_strategy(self, symbol: str = "ETHUSDT") -> Optional[Dict]:
        """兼容接口"""
        # 将 ETHUSDT 转换为 ETH_USDT
        contract = symbol.replace("USDT", "_USDT")
        return self.client.get_realtime_data_for_strategy(use_futures=True)


if __name__ == "__main__":
    # 测试
    print("="*60)
    print("Gate.io API 测试")
    print("="*60)
    
    client = GateIOClient()
    
    # 测试合约行情
    print("\n1. 合约行情:")
    ticker = client.get_futures_ticker()
    if ticker:
        print(f"   标记价格: {ticker.mark_price}")
        print(f"   最新价格: {ticker.last_price}")
        print(f"   24h涨跌: {ticker.change_percentage}%")
        print(f"   24h区间: {ticker.low_24h} - {ticker.high_24h}")
        print(f"   资金费率: {ticker.funding_rate}")
    
    # 测试合约K线
    print("\n2. 合约K线 (最新5根):")
    klines = client.get_futures_candlesticks(limit=5)
    for i, k in enumerate(klines[-5:]):
        print(f"   [{i+1}] {datetime.fromtimestamp(k.timestamp)} O:{k.open:.2f} H:{k.high:.2f} L:{k.low:.2f} C:{k.close:.2f}")
    
    # 测试完整数据
    print("\n3. 策略数据:")
    data = client.get_realtime_data_for_strategy()
    if data:
        print(f"   数据源: {data['source']}")
        print(f"   当前价格: {data['current_price']}")
        print(f"   K线数量: {len(data['klines_15m'])}")
    
    print("\n" + "="*60)
