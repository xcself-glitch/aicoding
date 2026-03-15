#!/bin/bash
# 兆易创新持仓监控 - 一键设置脚本

echo "════════════════════════════════════════════════════════════"
echo "  🔍 兆易创新持仓监控设置"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📊 持仓信息:"
echo "  • 股票: 兆易创新 (603986)"
echo "  • 数量: 1100股"
echo "  • 成本: ¥298.69"
echo "  • 现价: ¥278.33"
echo "  • 浮亏: -6.82% (-¥22,396)"
echo ""
echo "🎯 预警规则:"
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │ 📈 盈利预警    │ 盈利达10% (¥328.56)          │ 减仓  │"
echo "  │ 📉 亏损预警    │ 亏损扩大至10% (¥268.82)      │ 止损  │"
echo "  │ 🛒 补仓点      │ 股价跌至¥270 (支撑位)        │ 补仓  │"
echo "  │ 💰 减仓点      │ 股价涨至¥295 (接近成本)      │ 减仓  │"
echo "  │ 🚨 止损点      │ 股价跌破¥265                 │ 清仓  │"
echo "  │ ⚡ 异动预警    │ 日内涨跌超±4%                │ 关注  │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""
echo "⏰ 监控频率:"
echo "  • 交易时间 (9:30-15:00): 每5分钟"
echo "  • 午休时间 (11:30-13:00): 每10分钟"
echo "  • 收盘后 (15:00-24:00): 每30分钟"
echo "  • 凌晨 (0:00-9:30): 每小时"
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 检查依赖
echo "🔧 检查依赖..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装"
    exit 1
fi

if ! python3 -c "import requests" 2>/dev/null; then
    echo "📦 安装 requests..."
    pip3 install requests -q
fi

echo "✅ 依赖检查完成"
echo ""

# 添加执行权限
echo "🔧 设置执行权限..."
chmod +x "$SCRIPT_DIR/scripts/monitor_zhaoyi.py"
chmod +x "$SCRIPT_DIR/scripts/control_zhaoyi.sh"
echo "✅ 权限设置完成"
echo ""

# 创建日志目录
mkdir -p "$HOME/.stock_monitor"

echo "════════════════════════════════════════════════════════════"
echo "✅ 设置完成！"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "🚀 使用方法:"
echo ""
echo "  1. 启动监控:"
echo "     cd skills/stock-monitor-pro/scripts"
echo "     ./control_zhaoyi.sh start"
echo ""
echo "  2. 查看状态:"
echo "     ./control_zhaoyi.sh status"
echo ""
echo "  3. 查看日志:"
echo "     ./control_zhaoyi.sh log"
echo ""
echo "  4. 即时检查:"
echo "     ./control_zhaoyi.sh check"
echo ""
echo "  5. 停止监控:"
echo "     ./control_zhaoyi.sh stop"
echo ""
echo "════════════════════════════════════════════════════════════"
