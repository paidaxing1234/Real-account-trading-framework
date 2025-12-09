# Real-account-trading-framework
欧意与币安的实盘交易框架

### update log

12.5 
python实盘搭建 常用api接口已接入并测试

12.8 
cpp实盘搭建启动，搭建事件驱动的基本框架
okx api 测试成功（get_account_instruments）本地测试需要添加代理
```bash
export all_proxy="socks5h://127.0.0.1:7890"
export https_proxy="$all_proxy"
export http_proxy="$all_proxy"
```

12.9
todo：
与策略确定整体框架和交互逻辑
