#!/bin/bash
# 测试网测试 - 快速开始脚本

echo "============================================================"
echo "  策略配置系统 - 测试网测试快速开始"
echo "============================================================"
echo ""

# 检查是否在正确的目录
if [ ! -f "test_strategy_config.py" ]; then
    echo "✗ 错误: 请在 test 目录下运行此脚本"
    echo "  cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/test"
    exit 1
fi

echo "选择测试模式："
echo "  1. MOCK 模式（推荐）- 不需要API密钥，最安全"
echo "  2. TESTNET 模式 - 需要测试网API密钥，使用虚拟资金"
echo "  3. 查看帮助"
echo "  4. 退出"
echo ""

read -p "请选择 (1/2/3/4): " choice

case $choice in
    1)
        echo ""
        echo "============================================================"
        echo "  运行 MOCK 模式测试"
        echo "============================================================"
        echo ""
        python3 test_strategy_config.py --mode mock
        ;;
    2)
        echo ""
        echo "============================================================"
        echo "  运行 TESTNET 模式测试"
        echo "============================================================"
        echo ""
        python3 run_testnet_test.py
        ;;
    3)
        echo ""
        echo "============================================================"
        echo "  帮助信息"
        echo "============================================================"
        echo ""
        echo "测试模式说明："
        echo ""
        echo "1. MOCK 模式"
        echo "   - 最安全，不会产生任何真实交易"
        echo "   - 无需API密钥"
        echo "   - 适合开发和功能测试"
        echo "   - 运行命令: python3 test_strategy_config.py --mode mock"
        echo ""
        echo "2. TESTNET 模式"
        echo "   - 使用虚拟资金，无真实资金风险"
        echo "   - 需要OKX测试网API密钥"
        echo "   - 测试真实的API连接和交易流程"
        echo "   - 运行命令: python3 run_testnet_test.py"
        echo ""
        echo "详细文档："
        echo "   - 测试网指南: cat TESTNET_GUIDE.md"
        echo "   - 测试说明: cat README.md"
        echo "   - 完整报告: cat TESTNET_SETUP_COMPLETE.md"
        echo ""
        ;;
    4)
        echo "已退出"
        exit 0
        ;;
    *)
        echo "✗ 无效选择"
        exit 1
        ;;
esac
