#!/bin/bash
# 兆易创新持仓监控控制脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/.stock_monitor"
PID_FILE="$LOG_DIR/zhaoyi_monitor.pid"
PYTHON_SCRIPT="$SCRIPT_DIR/monitor_zhaoyi.py"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo -e "${YELLOW}⚠️  监控进程已在运行 (PID: $(cat $PID_FILE))${NC}"
            exit 1
        fi
        
        echo -e "${GREEN}🚀 启动兆易创新监控后台进程...${NC}"
        mkdir -p "$LOG_DIR"
        
        # 创建监控循环脚本 (使用绝对路径)
        echo "#!/bin/bash
PYTHON=\"$PYTHON_SCRIPT\"
LOG_DIR=\"$LOG_DIR\"

while true; do
    HOUR=\$(TZ=Asia/Shanghai date +%H)
    MINUTE=\$(TZ=Asia/Shanghai date +%M)
    TIME_VAL=\$((HOUR * 100 + MINUTE))
    WEEKDAY=\$(TZ=Asia/Shanghai date +%w)
    
    if [ \"\$WEEKDAY\" -ge 1 ] && [ \"\$WEEKDAY\" -le 5 ]; then
        if { [ \"\$TIME_VAL\" -ge 930 ] && [ \"\$TIME_VAL\" -le 1130 ]; } || { [ \"\$TIME_VAL\" -ge 1300 ] && [ \"\$TIME_VAL\" -le 1500 ]; }; then
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/zhaoyi.log\" 2>&1
            sleep 300
        elif [ \"\$TIME_VAL\" -gt 1130 ] && [ \"\$TIME_VAL\" -lt 1300 ]; then
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/zhaoyi.log\" 2>&1
            sleep 600
        elif [ \"\$TIME_VAL\" -gt 1500 ] && [ \"\$TIME_VAL\" -le 2359 ]; then
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/zhaoyi.log\" 2>&1
            sleep 1800
        else
            python3 \"\$PYTHON\" >> \"\$LOG_DIR/zhaoyi.log\" 2>&1
            sleep 3600
        fi
    else
        python3 \"\$PYTHON\" >> \"\$LOG_DIR/zhaoyi.log\" 2>&1
        sleep 3600
    fi
done" > "$LOG_DIR/zhaoyi_loop.sh"
        
        chmod +x "$LOG_DIR/zhaoyi_loop.sh"
        
        # 启动后台进程
        nohup bash "$LOG_DIR/zhaoyi_loop.sh" > "$LOG_DIR/zhaoyi_daemon.log" 2>&1 &
        echo $! > "$PID_FILE"
        
        echo -e "${GREEN}✅ 已启动 (PID: $!)${NC}"
        echo -e "📋 日志: $LOG_DIR/zhaoyi.log"
        echo -e "📊 监控: 兆易创新 1100股 | 成本¥298.69"
        echo ""
        echo "预警规则:"
        echo "  • 盈利10%或亏损10%时提醒"
        echo "  • 股价触及¥270(补仓)或¥295(减仓)时提醒"
        echo "  • 日内涨跌超4%时提醒"
        ;;
        
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo -e "${YELLOW}🛑 停止监控进程 (PID: $PID)...${NC}"
                kill "$PID" 2>/dev/null
                pkill -f "zhaoyi_loop.sh" 2>/dev/null
                rm -f "$PID_FILE"
                echo -e "${GREEN}✅ 已停止${NC}"
            else
                echo -e "${YELLOW}⚠️  进程不存在${NC}"
                rm -f "$PID_FILE"
            fi
        else
            echo -e "${YELLOW}⚠️  没有运行中的进程${NC}"
        fi
        ;;
        
    status)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo -e "${GREEN}✅ 监控运行中 (PID: $(cat $PID_FILE))${NC}"
            echo ""
            echo "📊 最近日志:"
            tail -5 "$LOG_DIR/zhaoyi.log" 2>/dev/null | grep -E "(启动|现价|盈亏|预警)" | tail -3 || echo "  暂无最新记录"
        else
            echo -e "${RED}⏹️  监控未运行${NC}"
        fi
        ;;
        
    log)
        if [ -f "$LOG_DIR/zhaoyi.log" ]; then
            tail -f "$LOG_DIR/zhaoyi.log"
        else
            echo -e "${YELLOW}暂无日志文件${NC}"
        fi
        ;;
        
    check)
        echo "🔍 执行一次即时检查..."
        python3 "$PYTHON_SCRIPT"
        ;;
        
    *)
        echo "兆易创新持仓监控控制脚本"
        echo ""
        echo "用法: ./control_zhaoyi.sh [start|stop|status|log|check]"
        echo ""
        echo "  start   - 启动后台监控"
        echo "  stop    - 停止监控"
        echo "  status  - 查看运行状态"
        echo "  log     - 查看实时日志"
        echo "  check   - 执行一次即时检查"
        ;;
esac
