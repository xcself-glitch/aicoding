# 📱 飞书应用机器人配置指南

## 你的情况
✅ 已有飞书应用机器人（没有 Webhook 自定义机器人）

## 如何使用

### 方式一：直接运行（当前会话接收通知）

价格监控脚本会自动在当前会话输出通知：

```bash
python3 scripts/price_monitor_feishu.py --check
```

输出示例：
```
============================================================
📢 🟢 兆易创新 触及买入目标价
============================================================
**兆易创新 (603986)**

当前价格: ¥263.00
目标买入价: ¥265.00
建议: 可考虑逢低加仓

---
⏰ 2026-03-14 10:30:15
============================================================
```

### 方式二：发送到指定飞书群（推荐）

**步骤 1：获取群聊 Chat ID**

方法 A：通过飞书开放平台
1. 登录 [飞书开放平台](https://open.feishu.cn/)
2. 进入你的应用 → 凭证与基础信息
3. 查看 **Chat ID**（格式如 `oc_xxxxxxxx`）

方法 B：通过 OpenClaw 工具
```bash
# 搜索群聊
openclaw tools call feishu_chat --params '{"action":"list"}'
```

**步骤 2：配置 Chat ID**

```bash
export FEISHU_CHAT_ID="oc_xxxxxxxx"
```

**步骤 3：修改通知脚本**

编辑 `scripts/notify_feishu.py`，在 `send_stock_alert` 调用时传入 `chat_id`：

```python
send_stock_alert(
    title="买入提醒",
    content="...",
    chat_id="oc_xxxxxxxx"  # 你的群ID
)
```

### 方式三：在 OpenClaw 中使用

由于价格监控是通过 OpenClaw cron 任务运行的，消息会通过 `feishu_im_user_message` 工具自动发送。

确保 OpenClaw 已登录飞书：
```bash
openclaw auth status
```

## 🎯 通知效果

当达到目标价格时，你会在飞书收到：

```
📊 **🟢 兆易创新 触及买入目标价**

当前价格: ¥263.00
目标买入价: ¥265.00
建议: 可考虑逢低加仓

---
⏰ 2026-03-14 10:30:15
```

## ⚙️ 定时任务已配置

```bash
# 查看任务
cat config/openclaw-cron.json

# 手动测试
openclaw tools call feishu_im_user_message --params '{
  "action": "send",
  "receive_id_type": "chat_id", 
  "receive_id": "你的群ID",
  "msg_type": "text",
  "content": "{\"text\":\"📊 股票监控测试消息\"}"
}'
```

## 🔍 故障排查

| 问题 | 解决 |
|------|------|
| 收不到通知 | 检查 `openclaw auth status` 是否已登录 |
| 群ID无效 | 确认应用已添加到该群聊 |
| 权限不足 | 在飞书开放平台给应用添加 `im:chat:send` 权限 |

## 📋 权限配置

在飞书开放平台 → 你的应用 → 权限管理，添加：
- ✅ `im:chat:send` - 发送消息到群聊
- ✅ `im:message:send` - 发送消息

---

**最简单的方式**：直接在飞书里和 Agent 对话，所有通知会直接显示在聊天记录中！
