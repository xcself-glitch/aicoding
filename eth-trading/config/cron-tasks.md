# ETHUSDT 交易提醒定时任务

## 已配置任务

### 1. eth-trading-monitor (正式监控)
- **ID**: `cb63db15-3b9b-40f5-81cc-dc496b4a63f8`
- **周期**: 每5分钟
- **时区**: Asia/Shanghai
- **命令**: `cd skills/eth-trading && python3 scripts/eth_cron_job.py`
- **状态**: ✅ 已启用

### 2. eth-trading-test (测试任务)
- **ID**: `30a5e8ae-3634-4ea9-b856-c95cde80e696`
- **周期**: 每5分钟
- **时区**: Asia/Shanghai
- **命令**: `cd skills/eth-trading && python3 scripts/eth_cron_job.py`
- **状态**: ✅ 已启用（测试完成后可禁用）

## 管理命令

```bash
# 查看任务列表
openclaw cron list

# 查看任务状态
openclaw cron status

# 手动运行任务
openclaw cron run cb63db15-3b9b-40f5-81cc-dc496b4a63f8

# 禁用测试任务
openclaw cron disable 30a5e8ae-3634-4ea9-b856-c95cde80e696

# 启用测试任务
openclaw cron enable 30a5e8ae-3634-4ea9-b856-c95cde80e696

# 删除任务
openclaw cron rm 30a5e8ae-3634-4ea9-b856-c95cde80e696
```

## 任务执行时间

| 任务 | 执行频率 | 下次执行 |
|------|----------|----------|
| eth-trading-monitor | 每15分钟 | 自动计算 |
| eth-trading-test | 每5分钟 | 自动计算 |

## 飞书通知

当检测到交易信号时（做多/做空），任务输出会自动发送到飞书会话。

通知内容包括：
- 当前ETH价格
- 信号类型（做多/做空）
- 信号强度（0-100）
- 价格位置（日内区间）
- 交易目标（止盈/止损）
- 预期收益

## 风险提示

⚠️ **重要提示**:
- 本策略使用10倍杠杆，风险极高
- 所有信号仅供参考，不构成投资建议
- 请根据自身风险承受能力决策
- 建议先用模拟盘测试至少2周
