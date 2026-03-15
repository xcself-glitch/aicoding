#!/usr/bin/env python3
"""
币安合约API客户端
获取ETHUSDT永续合约K线数据
"""

import requests
import json
import time
import hmac
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class KlineData:
    """K线数据"""
    timestamp: int          # 开盘时间
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    trades: int
    taker_buy_base: float
    taker_buy_quote: float
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'trades': self.trades
        }


@dataclass
class Ticker24h:
    """24小时行情数据"""
    symbol: str
    price_change: float
    price_change_percent: float
    weighted_avg_price: float
    last_price: float
    last_qty: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float
    open_time: int
    close_time: int
    first_id: int
    last_id: int
    count: int


class BinanceFuturesClient:
    """币安合约API客户端"""
    
    def __init__(self):
        self.base_url = "https://fapi.binance.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.last_request_time = 0
        self.rate_limit_delay = 0.1  # 请求间隔(秒)
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """
        发送API请求
        
        Args:
            endpoint: API端点
            params: 请求参数
        
        Returns:
            响应数据或None
        """
        # 简单的速率限制
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            self.last_request_time = time.time()
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print(f"⚠️ 请求过于频繁，等待60秒...")
                time.sleep(60)
                return self._make_request(endpoint, params)
            else:
                print(f"❌ API请求失败: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"❌ 请求超时: {endpoint}")
            return None
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            return None
    
    def get_klines(self, 
                   symbol: str = "ETHUSDT",
                   interval: str = "15m",
                   limit: int = 100,
                   start_time: int = None,
                   end_time: int = None) -> List[KlineData]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对
            interval: 时间间隔 (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            limit: 返回条数 (最大1500)
            start_time: 开始时间戳(ms)
            end_time: 结束时间戳(ms)
        
        Returns:
            K线数据列表
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        data = self._make_request("/fapi/v1/klines", params)
        
        if not data:
            return []
        
        klines = []
        for item in data:
            # 币安返回格式:
            # [开盘时间, 开盘价, 最高价, 最低价, 收盘价, 成交量, 收盘时间, 
            #  成交额, 成交笔数, 主动买入成交量, 主动买入成交额, 忽略]
            klines.append(KlineData(
                timestamp=int(item[0]),
                open_time=datetime.fromtimestamp(int(item[0]) / 1000),
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=float(item[5]),
                close_time=int(item[6]),
                quote_volume=float(item[7]),
                trades=int(item[8]),
                taker_buy_base=float(item[9]),
                taker_buy_quote=float(item[10])
            ))
        
        return klines
    
    def get_ticker_24h(self, symbol: str = "ETHUSDT") -> Optional[Ticker24h]:
        """获取24小时行情统计"""
        params = {'symbol': symbol}
        data = self._make_request("/fapi/v1/ticker/24hr", params)
        
        if not data:
            return None
        
        return Ticker24h(
            symbol=data['symbol'],
            price_change=float(data['priceChange']),
            price_change_percent=float(data['priceChangePercent']),
            weighted_avg_price=float(data['weightedAvgPrice']),
            last_price=float(data['lastPrice']),
            last_qty=float(data['lastQty']),
            open_price=float(data['openPrice']),
            high_price=float(data['highPrice']),
            low_price=float(data['lowPrice']),
            volume=float(data['volume']),
            quote_volume=float(data['quoteVolume']),
            open_time=int(data['openTime']),
            close_time=int(data['closeTime']),
            first_id=int(data['firstId']),
            last_id=int(data['lastId']),
            count=int(data['count'])
        )
    
    def get_funding_rate(self, symbol: str = "ETHUSDT", limit: int = 1) -> List[Dict]:
        """获取资金费率"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return self._make_request("/fapi/v1/fundingRate", params) or []
    
    def get_latest_price(self, symbol: str = "ETHUSDT") -> Optional[float]:
        """获取最新价格"""
        params = {'symbol': symbol}
        data = self._make_request("/fapi/v1/ticker/price", params)
        
        if data and 'price' in data:
            return float(data['price'])
        return None
    
    def get_orderbook(self, symbol: str = "ETHUSDT", limit: int = 5) -> Optional[Dict]:
        """获取订单簿"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return self._make_request("/fapi/v1/depth", params)
    
    def get_multi_timeframe_data(self, 
                                  symbol: str = "ETHUSDT",
                                  timeframes: List[str] = None) -> Dict[str, List[KlineData]]:
        """
        获取多周期K线数据
        
        Args:
            symbol: 交易对
            timeframes: 时间周期列表
        
        Returns:
            {周期: K线数据列表}
        """
        if timeframes is None:
            timeframes = ['15m', '5m', '1h', '4h', '1d']
        
        result = {}
        for tf in timeframes:
            # 根据周期调整获取数量
            if tf in ['1m', '3m', '5m']:
                limit = 200
            elif tf in ['15m', '30m', '1h']:
                limit = 100
            else:
                limit = 50
            
            klines = self.get_klines(symbol, tf, limit)
            result[tf] = klines
            
            print(f"✅ 获取 {tf} 数据: {len(klines)} 条")
            time.sleep(0.2)  # 避免请求过快
        
        return result
    
    def get_realtime_data_for_strategy(self, symbol: str = "ETHUSDT") -> Optional[Dict]:
        """
        获取策略所需的实时数据
        
        Returns:
            {
                'klines_15m': List[KlineData],
                'klines_5m': List[KlineData],
                'ticker_24h': Ticker24h,
                'funding_rate': float,
                'current_price': float
            }
        """
        print("📊 获取ETHUSDT实时数据...")
        
        # 获取15分钟K线 (主周期)
        klines_15m = self.get_klines(symbol, "15m", limit=100)
        if not klines_15m:
            print("❌ 无法获取15分钟K线数据")
            return None
        
        # 获取5分钟K线 (辅助周期)
        klines_5m = self.get_klines(symbol, "5m", limit=100)
        
        # 获取24小时行情
        ticker = self.get_ticker_24h(symbol)
        
        # 获取最新价格
        current_price = self.get_latest_price(symbol)
        
        # 获取资金费率
        funding = self.get_funding_rate(symbol, limit=1)
        funding_rate = funding[0]['fundingRate'] if funding else 0
        
        print(f"✅ 当前价格: {current_price:.2f} USDT")
        print(f"✅ 24h涨跌: {ticker.price_change_percent:.2f}%")
        print(f"✅ 资金费率: {funding_rate:.4%}")
        
        return {
            'klines_15m': klines_15m,
            'klines_5m': klines_5m,
            'ticker_24h': ticker,
            'funding_rate': funding_rate,
            'current_price': current_price
        }


def klines_to_arrays(klines: List[KlineData]) -> Tuple[List[float], ...]:
    """
    将K线数据转换为数组格式
    
    Returns:
        (opens, highs, lows, closes, volumes)
    """
    opens = [k.open for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]
    volumes = [k.volume for k in klines]
    
    return opens, highs, lows, closes, volumes


if __name__ == "__main__":
    print("币安合约API测试")
    print("=" * 60)
    
    client = BinanceFuturesClient()
    
    # 测试获取K线数据
    print("\n1. 测试获取15分钟K线...")
    klines = client.get_klines("ETHUSDT", "15m", limit=20)
    
    if klines:
        print(f"✅ 成功获取 {len(klines)} 条K线")
        print(f"\n最近5条K线:")
        for k in klines[-5:]:
            print(f"  {k.open_time.strftime('%m-%d %H:%M')}: "
                  f"开{k.open:.2f} 高{k.high:.2f} 低{k.low:.2f} 收{k.close:.2f} "
                  f"量{k.volume:.2f}")
    
    # 测试获取24小时行情
    print("\n2. 测试获取24小时行情...")
    ticker = client.get_ticker_24h("ETHUSDT")
    if ticker:
        print(f"✅ 24h数据:")
        print(f"  当前价格: {ticker.last_price:.2f}")
        print(f"  24h涨跌: {ticker.price_change:+.2f} ({ticker.price_change_percent:+.2f}%)")
        print(f"  24h最高: {ticker.high_price:.2f}")
        print(f"  24h最低: {ticker.low_price:.2f}")
        print(f"  24h成交量: {ticker.volume:.4f} ETH")
    
    # 测试获取资金费率
    print("\n3. 测试获取资金费率...")
    funding = client.get_funding_rate("ETHUSDT", limit=3)
    if funding:
        print(f"✅ 最近资金费率:")
        for f in funding:
            time_str = datetime.fromtimestamp(f['fundingTime']/1000).strftime('%m-%d %H:%M')
            print(f"  {time_str}: {float(f['fundingRate']):.4%}")
    
    # 测试获取策略所需全部数据
    print("\n4. 测试获取策略数据...")
    strategy_data = client.get_realtime_data_for_strategy("ETHUSDT")
    if strategy_data:
        print("✅ 策略数据准备完成!")
