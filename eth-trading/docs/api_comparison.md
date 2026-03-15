# 加密货币API对比分析

## 测试结果总结

| 交易所/API | 可用性 | 频率限制 | 备注 |
|-----------|--------|----------|------|
| **Gate.io** | ✅ 可用 | IP限制 | **推荐使用** |
| **CryptoCompare** | ✅ 可用 | 未知 | 仅价格数据 |
| **CoinGecko** | ❌ 受限 | 30次/分钟 | 当前环境访问受限 |
| **OKX** | ❌ 受限 | 公开 | 当前环境访问受限 |
| **MEXC** | ❌ 受限 | 公开 | 当前环境访问受限 |
| **Bybit** | ❌ 受限 | 公开 | 当前环境访问受限 |
| **CoinPaprika** | ❌ 受限 | 无限制 | 当前环境访问受限 |
| **币安** | ❌ 受限 | 1200次/分钟 | 当前环境访问受限 |

## 最终选择：Gate.io API

### 为什么选择 Gate.io？

1. **可用性**：在当前网络环境下完全可用
2. **数据完整**：
   - ✅ 永续合约行情（包含资金费率）
   - ✅ K线数据（支持多时间周期）
   - ✅ 24小时统计数据
3. **免费**：无需API Key即可访问公开数据
4. **频率限制**：
   - 公开API：按IP限制，足够个人使用
   - WebSocket：每个IP最多300个连接
5. **低延迟**：服务器响应快速

### Gate.io API 限制详情

| 接口类型 | 限制方式 | 限制详情 |
|---------|---------|---------|
| 公开REST API | IP级别 | 根据IP进行限流，一般足够 |
| WebSocket | IP级别 | 每IP最大300个连接 |
| 私有API | UID级别 | 根据VIP等级不同 |

### 推荐的请求频率

对于15分钟周期的监控任务：
- 每次运行约3-4个API请求
- 15分钟内最多4次请求
- 远低于限制，安全可用

## 备选方案

如果 Gate.io 不可用，可考虑：

1. **CryptoCompare** - 仅基础价格数据
2. **自建代理** - 通过海外服务器转发币安/OKX请求

## 实现代码

已创建适配器：`strategies/gateio_client.py`

```python
from strategies.gateio_client import GateIOClient, GateIOAdapter

# 使用示例
client = GateIOClient()
data = client.get_realtime_data_for_strategy(use_futures=True)

# 数据包含：
# - current_price: 标记价格
# - ticker_24h: 24小时行情
# - klines_15m: 15分钟K线（100根）
# - funding_rate: 资金费率
```

## API 对比详情

### 1. Gate.io API v4

```
基础URL: https://api.gateio.ws/api/v4

端点：
- 合约行情: /futures/usdt/tickers?contract=ETH_USDT
- 合约K线: /futures/usdt/candlesticks?contract=ETH_USDT&interval=15m
- 现货行情: /spot/tickers?currency_pair=ETH_USDT
- 现货K线: /spot/candlesticks?currency_pair=ETH_USDT&interval=15m
```

**优点**:
- 当前环境可访问
- 提供合约资金费率
- 数据质量高
- 无需认证

**缺点**:
- 知名度不如币安
- 流动性相对较低

### 2. CryptoCompare

```
基础URL: https://min-api.cryptocompare.com

端点：
- 价格: /data/price?fsym=ETH&tsyms=USDT
```

**优点**:
- 聚合多交易所数据
- 当前环境可访问

**缺点**:
- 数据较简单，无K线
- 无合约数据

### 3. CoinGecko

```
基础URL: https://api.coingecko.com/api/v3

免费版限制：
- 30次/分钟
- 10,000次/月
```

**优点**:
- 数据全面
- 免费版够用

**缺点**:
- 当前环境访问受限
- 更新频率较低

## 监控任务配置

当前已配置定时任务：

| 任务名 | ID | 周期 | 数据源 |
|--------|-----|------|--------|
| eth-trading-live | a0b4b536... | 每15分钟 | Gate.io |
| eth-trading-test | c51ebea3... | 每5分钟 | Gate.io |

```bash
# 查看任务
openclaw cron list

# 手动运行
openclaw cron run a0b4b536-6571-4abf-8af8-3e03f245fbc0
```
