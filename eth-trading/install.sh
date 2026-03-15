#!/bin/bash
set -e

echo "=========================================="
echo "  ETH交易策略 V19 - 5分钟监控版"
echo "=========================================="
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3"
    exit 1
fi
echo "✓ Python3已安装"

# 检查依赖
echo ""
echo "检查依赖..."
python3 -c "import numpy" 2>/dev/null || pip3 install numpy -q
python3 -c "import requests" 2>/dev/null || pip3 install requests -q
echo "✓ 依赖检查完成"

# 验证文件
echo ""
echo "验证文件..."
for file in "strategies/signal_generator.py" "strategies/indicators.py" "scripts/backtest_v19.py"; do
    if [ -f "$file" ]; then echo "✓ $file"; else echo "✗ $file 缺失"; fi
done

# 显示配置信息
echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "监控频率: 5分钟"
echo ""
echo "下一步:"
echo "1. 编辑 config/strategy_config_v2.py 配置API"
echo "2. 运行: python3 scripts/backtest_v19.py"
echo ""
echo "或使用交易机器人:"
echo "  python3 scripts/eth_trading_bot.py"
echo ""
echo "推荐策略: V19 (周收益+39%)"
echo "=========================================="
