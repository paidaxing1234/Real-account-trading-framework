cmake_minimum_required(VERSION 3.15)
project(RealTradingFramework VERSION 1.0.0 LANGUAGES CXX)

# C++17标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 编译选项
if(MSVC)
    add_compile_options(/W4)
else()
    add_compile_options(-Wall -Wextra -pedantic)
endif()

# 查找依赖
find_package(Threads REQUIRED)

# nlohmann/json (header-only) - 可选
# 核心框架不需要 JSON，只有 OKX 适配器实现需要
find_package(nlohmann_json 3.2.0 QUIET)

if(nlohmann_json_FOUND)
    message(STATUS "Found nlohmann_json: ${nlohmann_json_VERSION}")
    set(HAS_JSON TRUE)
else()
    # 尝试使用手动下载的版本
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/external/include/nlohmann/json.hpp")
        message(STATUS "Using manually downloaded nlohmann_json")
        include_directories(${CMAKE_CURRENT_SOURCE_DIR}/external/include)
        set(HAS_JSON TRUE)
    else()
        message(STATUS "nlohmann_json not found - core framework will work without it")
        message(STATUS "To use OKX adapter, download manually or install: brew install nlohmann-json")
        set(HAS_JSON FALSE)
    endif()
endif()

# 查找 OpenSSL（用于OKX REST API 和 WebSocket）
find_package(OpenSSL QUIET)
if(OPENSSL_FOUND)
    message(STATUS "Found OpenSSL: ${OPENSSL_VERSION}")
endif()

# 包含目录
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${CMAKE_CURRENT_SOURCE_DIR}/adapters
    ${CMAKE_CURRENT_SOURCE_DIR}/strategies
    ${CMAKE_CURRENT_SOURCE_DIR}/utils
)

# 核心库（header-only，不需要编译）
add_library(trading_core INTERFACE)
target_include_directories(trading_core INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/core
)

# 策略库（header-only）
add_library(trading_strategies INTERFACE)
target_include_directories(trading_strategies INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/strategies
)

# 工具库（header-only）
add_library(trading_utils INTERFACE)
target_include_directories(trading_utils INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/utils
)

# ============================================================
# OKX WebSocket 库（可选，需要 websocketpp）
# ============================================================
# 查找 websocketpp（header-only）
find_path(WEBSOCKETPP_INCLUDE_DIR websocketpp/config/asio_client.hpp
    PATHS 
        /usr/local/include 
        /opt/homebrew/include 
        /usr/include
)

# 查找 Boost（websocketpp 依赖）
# CMake 4.0+ 需要使用 CONFIG 模式或设置 CMP0167
if(POLICY CMP0167)
    cmake_policy(SET CMP0167 OLD)
endif()
find_package(Boost COMPONENTS system)

# 查找 standalone ASIO（替代 Boost.ASIO）
find_path(ASIO_INCLUDE_DIR asio.hpp
    PATHS 
        /usr/local/include 
        /opt/homebrew/include 
        /usr/include
)

# 调试输出
message(STATUS "WEBSOCKETPP_INCLUDE_DIR: ${WEBSOCKETPP_INCLUDE_DIR}")
message(STATUS "ASIO_INCLUDE_DIR: ${ASIO_INCLUDE_DIR}")
message(STATUS "Boost_FOUND: ${Boost_FOUND}")
message(STATUS "Boost_LIBRARIES: ${Boost_LIBRARIES}")
message(STATUS "OPENSSL_FOUND: ${OPENSSL_FOUND}")
message(STATUS "HAS_JSON: ${HAS_JSON}")

# 优先使用 standalone ASIO（避免 Boost 版本兼容问题）
if(WEBSOCKETPP_INCLUDE_DIR AND ASIO_INCLUDE_DIR AND OPENSSL_FOUND AND HAS_JSON)
    set(HAS_WEBSOCKETPP TRUE)
    set(USE_STANDALONE_ASIO TRUE)
    message(STATUS "Found websocketpp: ${WEBSOCKETPP_INCLUDE_DIR}")
    message(STATUS "Found standalone ASIO: ${ASIO_INCLUDE_DIR}")
    message(STATUS "Using standalone ASIO (recommended)")
    
    # OKX WebSocket 库（使用 standalone ASIO）
    add_library(okx_websocket
        adapters/okx/okx_websocket.cpp
    )
    target_include_directories(okx_websocket
        PUBLIC ${CMAKE_SOURCE_DIR}
        PUBLIC ${WEBSOCKETPP_INCLUDE_DIR}
        PUBLIC ${ASIO_INCLUDE_DIR}
    )
    target_compile_definitions(okx_websocket PRIVATE 
        USE_WEBSOCKETPP
        ASIO_STANDALONE
        _WEBSOCKETPP_CPP11_STL_
    )
    target_link_libraries(okx_websocket
        PUBLIC trading_core
        PRIVATE OpenSSL::SSL
        PRIVATE OpenSSL::Crypto
        PRIVATE Threads::Threads
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(okx_websocket PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    message(STATUS "  ✓ okx_websocket 库（WebSocket++ + standalone ASIO）")

elseif(WEBSOCKETPP_INCLUDE_DIR AND Boost_FOUND AND OPENSSL_FOUND AND HAS_JSON)
    # 回退到 Boost.ASIO（可能有兼容性问题）
    set(HAS_WEBSOCKETPP TRUE)
    set(USE_STANDALONE_ASIO FALSE)
    message(STATUS "Found websocketpp: ${WEBSOCKETPP_INCLUDE_DIR}")
    message(STATUS "Found Boost: ${Boost_LIBRARIES}")
    message(WARNING "Using Boost.ASIO - may have compatibility issues with Boost 1.74+")
    
    # OKX WebSocket 库
    add_library(okx_websocket
        adapters/okx/okx_websocket.cpp
    )
    target_include_directories(okx_websocket
        PUBLIC ${CMAKE_SOURCE_DIR}
        PUBLIC ${WEBSOCKETPP_INCLUDE_DIR}
        PUBLIC ${Boost_INCLUDE_DIRS}
    )
    target_compile_definitions(okx_websocket PRIVATE 
        USE_WEBSOCKETPP
        BOOST_ASIO_NO_DEPRECATED
        _WEBSOCKETPP_CPP11_STL_
    )
    target_link_libraries(okx_websocket
        PUBLIC trading_core
        PRIVATE OpenSSL::SSL
        PRIVATE OpenSSL::Crypto
        PRIVATE ${Boost_LIBRARIES}
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(okx_websocket PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    message(STATUS "  ✓ okx_websocket 库（WebSocket++ + Boost.ASIO）")
else()
    set(HAS_WEBSOCKETPP FALSE)
    message(STATUS "")
    message(STATUS "WebSocket++ 未找到，使用占位实现")
    message(STATUS "  安装方法:")
    message(STATUS "    macOS: brew install websocketpp boost")
    message(STATUS "    Ubuntu: apt install libwebsocketpp-dev libboost-all-dev")
    
    # 不带 websocketpp 的占位实现
    if(OPENSSL_FOUND AND HAS_JSON)
        add_library(okx_websocket
            adapters/okx/okx_websocket.cpp
        )
        target_include_directories(okx_websocket
            PUBLIC ${CMAKE_SOURCE_DIR}
        )
        target_link_libraries(okx_websocket
            PUBLIC trading_core
            PRIVATE OpenSSL::SSL
            PRIVATE OpenSSL::Crypto
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(okx_websocket PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ okx_websocket 库（占位实现）")
    endif()
endif()

# 示例程序
add_executable(main_example
    examples/main_example.cpp
)
target_link_libraries(main_example
    PRIVATE trading_core
    PRIVATE trading_strategies
    PRIVATE trading_utils
    PRIVATE Threads::Threads
    # PRIVATE okx_adapter  # 需要实现后取消注释
)

if(HAS_JSON AND nlohmann_json_FOUND)
    target_link_libraries(main_example PRIVATE nlohmann_json::nlohmann_json)
endif()

# 测试程序
add_executable(test_core
    examples/test_core.cpp
)
target_link_libraries(test_core
    PRIVATE trading_core
)

if(HAS_JSON AND nlohmann_json_FOUND)
    target_link_libraries(test_core PRIVATE nlohmann_json::nlohmann_json)
endif()

# OKX API 测试程序（需要额外依赖）
find_package(CURL QUIET)
find_package(OpenSSL QUIET)
if(CURL_FOUND AND OPENSSL_FOUND AND HAS_JSON)
    message(STATUS "Building OKX API test")
    add_library(okx_rest_api adapters/okx/okx_rest_api.cpp)
    target_link_libraries(okx_rest_api
        PUBLIC trading_core
        PRIVATE CURL::libcurl
        PRIVATE OpenSSL::SSL
        PRIVATE OpenSSL::Crypto
    )
    
    # 只有使用系统安装的 nlohmann_json 时才链接
    if(nlohmann_json_FOUND)
        target_link_libraries(okx_rest_api PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    add_executable(test_okx_api examples/test_okx_api.cpp)
    target_link_libraries(test_okx_api
        PRIVATE okx_rest_api
    )
    
    # 只有使用系统安装的 nlohmann_json 时才链接
    if(nlohmann_json_FOUND)
        target_link_libraries(test_okx_api PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    # OKX下单API测试（支持止盈止损）
    add_executable(test_okx_order examples/test_okx_order.cpp)
    target_link_libraries(test_okx_order
        PRIVATE okx_rest_api
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(test_okx_order PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    # OKX批量下单API测试
    add_executable(test_okx_batch_orders examples/test_okx_batch_orders.cpp)
    target_link_libraries(test_okx_batch_orders
        PRIVATE okx_rest_api
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(test_okx_batch_orders PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_okx_batch_orders 批量下单测试")
    
    # OKX修改订单API测试
    add_executable(test_okx_amend_order examples/test_okx_amend_order.cpp)
    target_link_libraries(test_okx_amend_order
        PRIVATE okx_rest_api
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(test_okx_amend_order PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_okx_amend_order 修改订单测试")
    
    # OKX批量修改订单API测试
    add_executable(test_okx_amend_batch_orders examples/test_okx_amend_batch_orders.cpp)
    target_link_libraries(test_okx_amend_batch_orders
        PRIVATE okx_rest_api
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(test_okx_amend_batch_orders PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_okx_amend_batch_orders 批量修改订单测试")
    
    # OKX永续合约下单测试
    add_executable(test_okx_swap_orders examples/test_okx_swap_orders.cpp)
    target_link_libraries(test_okx_swap_orders
        PRIVATE okx_rest_api
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(test_okx_swap_orders PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_okx_swap_orders 永续合约下单测试")
    
    # OKX策略委托下单测试
    add_executable(test_okx_algo_order examples/test_okx_algo_order.cpp)
    target_link_libraries(test_okx_algo_order
        PRIVATE okx_rest_api
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(test_okx_algo_order PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_okx_algo_order 策略委托下单测试")
    
    # OKX策略委托订单WebSocket测试
    if(TARGET okx_websocket)
        add_executable(test_okx_algo_ws examples/test_okx_algo_ws.cpp)
        target_include_directories(test_okx_algo_ws PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_algo_ws
            PRIVATE okx_websocket trading_core
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_algo_ws PRIVATE nlohmann_json::nlohmann_json)
        endif()
        message(STATUS "  ✓ test_okx_algo_ws 策略委托订单WebSocket测试")
    endif()
    
    # OKX WebSocket K线测试
    if(TARGET okx_websocket)
        add_executable(test_okx_kline examples/test_okx_kline.cpp)
        target_include_directories(test_okx_kline PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_kline
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_kline PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_kline K线订阅测试")
    endif()
    
    # OKX WebSocket 行情频道测试
    if(TARGET okx_websocket)
        add_executable(test_okx_tickers examples/test_okx_tickers.cpp)
        target_include_directories(test_okx_tickers PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_tickers
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_tickers PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_tickers 行情频道测试")
    endif()
    
    # OKX WebSocket 交易频道测试
    if(TARGET okx_websocket)
        add_executable(test_okx_trades examples/test_okx_trades.cpp)
        target_include_directories(test_okx_trades PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_trades
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_trades PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_trades 交易频道测试")
    endif()
    
    # OKX WebSocket K线测试（多币种）
    if(TARGET okx_websocket)
        add_executable(test_okx_kline_all examples/test_okx_kline_all.cpp)
        target_include_directories(test_okx_kline_all PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_kline_all
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_kline_all PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_kline_all 多币种K线测试")
    endif()
    
    # OKX WebSocket 私有频道测试
    if(TARGET okx_websocket)
        add_executable(test_okx_private examples/test_okx_private.cpp)
        target_include_directories(test_okx_private PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_private
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_private PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_private 私有频道测试")
    endif()
    
    # OKX WebSocket 持仓总量测试
    if(TARGET okx_websocket)
        add_executable(test_okx_open_interest examples/test_okx_open_interest.cpp)
        target_include_directories(test_okx_open_interest PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_open_interest
            PRIVATE okx_websocket
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_open_interest PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_open_interest 持仓总量测试")
    endif()
    
    # OKX WebSocket 标记价格测试
    if(TARGET okx_websocket)
        add_executable(test_okx_mark_price examples/test_okx_mark_price.cpp)
        target_include_directories(test_okx_mark_price PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_mark_price
            PRIVATE okx_websocket
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_mark_price PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_mark_price 标记价格测试")
    endif()
    
    # OKX WebSocket 登录测试
    if(TARGET okx_websocket)
        add_executable(test_okx_login examples/test_okx_login.cpp)
        target_include_directories(test_okx_login PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_login
            PRIVATE okx_websocket
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_login PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_login 登录测试")
    endif()
    
    # OKX WebSocket Spread订单测试
    if(TARGET okx_websocket AND TARGET okx_rest_api)
        add_executable(test_okx_sprd_orders examples/test_okx_sprd_orders.cpp)
        target_include_directories(test_okx_sprd_orders PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_sprd_orders
            PRIVATE okx_websocket
            PRIVATE okx_rest_api
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_sprd_orders PRIVATE nlohmann_json::nlohmann_json)
        endif()
        if(CURL_FOUND)
            target_link_libraries(test_okx_sprd_orders PRIVATE ${CURL_LIBRARIES})
        endif()
        
        message(STATUS "  ✓ test_okx_sprd_orders Spread订单测试")
    endif()
    
    # OKX WebSocket 订单频道调试测试
    if(TARGET okx_websocket)
        add_executable(test_okx_orders_debug examples/test_okx_orders_debug.cpp)
        target_include_directories(test_okx_orders_debug PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_orders_debug
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_orders_debug PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_orders_debug 订单频道调试测试")
    endif()
    
    # OKX WebSocket 账户频道测试
    if(TARGET okx_websocket)
        add_executable(test_okx_account examples/test_okx_account.cpp)
        target_include_directories(test_okx_account PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_account
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_account PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_account 账户频道测试")
    endif()
    
    # OKX WebSocket 账户余额和持仓频道测试
    if(TARGET okx_websocket)
        add_executable(test_okx_balance_and_position examples/test_okx_balance_and_position.cpp)
        target_include_directories(test_okx_balance_and_position PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_balance_and_position
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_balance_and_position PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_balance_and_position 账户余额和持仓频道测试")
    endif()
    
    # OKX WebSocket 下单测试
    if(TARGET okx_websocket)
        add_executable(test_okx_ws_order examples/test_okx_ws_order.cpp)
        target_include_directories(test_okx_ws_order PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_ws_order
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_ws_order PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_ws_order WebSocket下单测试")
    endif()
    
    # OKX WebSocket Spread成交数据测试
    if(TARGET okx_websocket)
        add_executable(test_okx_sprd_trades examples/test_okx_sprd_trades.cpp)
        target_include_directories(test_okx_sprd_trades PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_sprd_trades
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_sprd_trades PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_sprd_trades Spread成交数据测试")
    endif()
    
    # OKX WebSocket 普通订单成交推送测试
    if(TARGET okx_websocket)
        add_executable(test_okx_order_fills examples/test_okx_order_fills.cpp)
        target_include_directories(test_okx_order_fills PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_order_fills
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_order_fills PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_order_fills 普通订单成交推送测试")
    endif()
    
    # OKX WebSocket 持仓频道测试
    if(TARGET okx_websocket)
        add_executable(test_okx_positions examples/test_okx_positions.cpp)
        target_include_directories(test_okx_positions PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_positions
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_positions PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_positions 持仓频道测试")
    endif()
    
    # OKX WebSocket 持仓+账户频道综合测试
    if(TARGET okx_websocket)
        add_executable(test_okx_positions_and_account examples/test_okx_positions_and_account.cpp)
        target_include_directories(test_okx_positions_and_account PRIVATE ${CMAKE_SOURCE_DIR})
        target_link_libraries(test_okx_positions_and_account
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(test_okx_positions_and_account PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        message(STATUS "  ✓ test_okx_positions_and_account 持仓+账户频道综合测试")
    endif()
else()
    message(STATUS "OKX API test skipped - missing dependencies (CURL/OpenSSL/JSON)")
endif()

# Journal测试程序
add_executable(test_journal_latency examples/test_journal_latency.cpp)
target_include_directories(test_journal_latency PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_journal_latency PRIVATE -O3 -march=native)

add_executable(test_journal_benchmark examples/test_journal_benchmark.cpp)
target_include_directories(test_journal_benchmark PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_journal_benchmark PRIVATE -O3 -march=native)

add_executable(test_latency_precise examples/test_latency_precise.cpp)
target_include_directories(test_latency_precise PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_latency_precise PRIVATE -O3 -march=native)

# Disruptor环形总线测试程序
add_executable(test_disruptor_latency examples/test_disruptor_latency.cpp)
target_include_directories(test_disruptor_latency PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_disruptor_latency PRIVATE -O3 -march=native)
target_link_libraries(test_disruptor_latency PRIVATE Threads::Threads)

add_executable(test_disruptor_benchmark examples/test_disruptor_benchmark.cpp)
target_include_directories(test_disruptor_benchmark PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_disruptor_benchmark PRIVATE -O3 -march=native)
target_link_libraries(test_disruptor_benchmark PRIVATE Threads::Threads)

add_executable(test_ringbuffer_simple examples/test_ringbuffer_simple.cpp)
target_include_directories(test_ringbuffer_simple PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_ringbuffer_simple PRIVATE -O3 -march=native)

add_executable(test_disruptor_perf examples/test_disruptor_perf.cpp)
target_include_directories(test_disruptor_perf PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_disruptor_perf PRIVATE -O3 -march=native)
target_link_libraries(test_disruptor_perf PRIVATE Threads::Threads)

# ============================================================
# ZeroMQ 实盘服务器
# ============================================================
# ZeroMQ 用于实盘服务器和策略客户端之间的 IPC 通信
# 延迟约 30-100μs（比 TCP localhost 快 3-5 倍）

# 直接查找 ZeroMQ 库（不用 pkg-config，避免路径问题）
find_library(ZMQ_LIBRARY NAMES zmq libzmq
    PATHS 
        /usr/local/lib 
        /opt/homebrew/lib 
        /usr/lib
        /usr/lib/x86_64-linux-gnu
    NO_DEFAULT_PATH
)

# 如果上面没找到，用默认路径再找一次
if(NOT ZMQ_LIBRARY)
    find_library(ZMQ_LIBRARY NAMES zmq libzmq)
endif()

find_path(ZMQ_INCLUDE_DIR zmq.h 
    PATHS /usr/local/include /opt/homebrew/include /usr/include)

if(ZMQ_LIBRARY AND ZMQ_INCLUDE_DIR)
    set(ZMQ_FOUND TRUE)
    message(STATUS "Found ZeroMQ library: ${ZMQ_LIBRARY}")
    message(STATUS "Found ZeroMQ include: ${ZMQ_INCLUDE_DIR}")
else()
    set(ZMQ_FOUND FALSE)
endif()

# 查找 cppzmq 头文件 (zmq.hpp)
find_path(CPPZMQ_INCLUDE_DIR zmq.hpp
    PATHS 
        /usr/local/include 
        /opt/homebrew/include 
        /usr/include
        ${ZMQ_INCLUDE_DIR}
)
if(CPPZMQ_INCLUDE_DIR)
    set(CPPZMQ_FOUND TRUE)
    message(STATUS "Found cppzmq: ${CPPZMQ_INCLUDE_DIR}")
else()
    set(CPPZMQ_FOUND FALSE)
    message(STATUS "cppzmq not found - install with: brew install cppzmq")
endif()

if(ZMQ_FOUND AND CPPZMQ_FOUND AND CURL_FOUND AND OPENSSL_FOUND AND HAS_JSON)
    message(STATUS "")
    message(STATUS "========================================")
    message(STATUS "  Building ZeroMQ Trading Server")
    message(STATUS "========================================")
    message(STATUS "  ZeroMQ: ${ZMQ_LIBRARY}")
    message(STATUS "  cppzmq: ${CPPZMQ_INCLUDE_DIR}")
    
    # ZeroMQ 服务端库
    add_library(zmq_server
        server/zmq_server.cpp
    )
    target_include_directories(zmq_server 
        PUBLIC ${CMAKE_SOURCE_DIR}
        PUBLIC ${ZMQ_INCLUDE_DIR}
        PUBLIC ${CPPZMQ_INCLUDE_DIR}
    )
    target_link_libraries(zmq_server
        PUBLIC ${ZMQ_LIBRARY}
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(zmq_server PUBLIC nlohmann_json::nlohmann_json)
    endif()
    
    # 实盘交易服务器
    add_executable(trading_server
        server/trading_server.cpp
    )
    target_include_directories(trading_server PRIVATE ${CMAKE_SOURCE_DIR})
    target_compile_options(trading_server PRIVATE -O3 -march=native)
    target_link_libraries(trading_server
        PRIVATE zmq_server
        PRIVATE okx_rest_api
        PRIVATE Threads::Threads
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(trading_server PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    message(STATUS "  ✓ trading_server 可执行文件")
    
    # 实盘交易服务器（实时行情版，连接OKX WebSocket）
    if(TARGET okx_websocket)
        add_executable(trading_server_live
            server/trading_server_live.cpp
        )
        target_include_directories(trading_server_live PRIVATE ${CMAKE_SOURCE_DIR})
        target_compile_options(trading_server_live PRIVATE -O3 -march=native)
        target_link_libraries(trading_server_live
            PRIVATE zmq_server
            PRIVATE okx_rest_api
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(trading_server_live PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        # Linux: 链接 libnuma 用于 NUMA 亲和性
        if(UNIX AND NOT APPLE)
            find_library(NUMA_LIBRARY numa)
            if(NUMA_LIBRARY)
                target_link_libraries(trading_server_live PRIVATE ${NUMA_LIBRARY})
                message(STATUS "  ✓ libnuma found: ${NUMA_LIBRARY}")
            else()
                message(WARNING "  ⚠ libnuma not found, NUMA binding disabled")
            endif()
        endif()
        
        message(STATUS "  ✓ trading_server_live 实时行情版（OKX WebSocket + ZeroMQ）")
    endif()
    
    # 完整版实盘交易服务器（支持所有OKX接口）
    if(TARGET okx_websocket)
        add_executable(trading_server_full
            server/trading_server_full.cpp
        )
        target_include_directories(trading_server_full PRIVATE ${CMAKE_SOURCE_DIR})
        target_compile_options(trading_server_full PRIVATE -O3 -march=native)
        target_link_libraries(trading_server_full
            PRIVATE zmq_server
            PRIVATE okx_rest_api
            PRIVATE okx_websocket
            PRIVATE trading_core
            PRIVATE Threads::Threads
        )
        if(nlohmann_json_FOUND)
            target_link_libraries(trading_server_full PRIVATE nlohmann_json::nlohmann_json)
        endif()
        
        # Linux: 链接 libnuma 用于 NUMA 亲和性
        if(UNIX AND NOT APPLE)
            find_library(NUMA_LIBRARY numa)
            if(NUMA_LIBRARY)
                target_link_libraries(trading_server_full PRIVATE ${NUMA_LIBRARY})
            endif()
        endif()
        
        message(STATUS "  ✓ trading_server_full 完整版（支持所有OKX接口）")
    endif()
    
    # 实盘交易服务器（异步版，带WebSocket行情）
    # TODO: 实现 trading_server_async.cpp 后取消注释
    # if(TARGET okx_websocket AND EXISTS "${CMAKE_SOURCE_DIR}/server/trading_server_async.cpp")
    #     add_executable(trading_server_async
    #         server/trading_server_async.cpp
    #     )
    #     target_include_directories(trading_server_async PRIVATE ${CMAKE_SOURCE_DIR})
    #     target_compile_options(trading_server_async PRIVATE -O3 -march=native)
    #     target_link_libraries(trading_server_async
    #         PRIVATE zmq_server
    #         PRIVATE okx_rest_api
    #         PRIVATE okx_websocket
    #         PRIVATE Threads::Threads
    #     )
    #     if(nlohmann_json_FOUND)
    #         target_link_libraries(trading_server_async PRIVATE nlohmann_json::nlohmann_json)
    #     endif()
    #     
    #     message(STATUS "  ✓ trading_server_async 可执行文件（含WebSocket行情）")
    # endif()
    
    message(STATUS "")
    
else()
    message(STATUS "")
    message(STATUS "========================================")
    message(STATUS "  ZeroMQ Trading Server 跳过")
    message(STATUS "========================================")
    if(NOT ZMQ_FOUND)
        message(STATUS "  缺少 ZeroMQ (libzmq):")
        message(STATUS "    macOS: brew install zeromq")
        message(STATUS "    Ubuntu: apt install libzmq3-dev")
    endif()
    if(NOT CPPZMQ_FOUND)
        message(STATUS "  缺少 cppzmq (C++ 绑定):")
        message(STATUS "    macOS: brew install cppzmq")
        message(STATUS "    Ubuntu: apt install libzmq3-dev 或手动安装 cppzmq")
    endif()
    if(NOT CURL_FOUND)
        message(STATUS "  缺少 CURL")
    endif()
    if(NOT OPENSSL_FOUND)
        message(STATUS "  缺少 OpenSSL")
    endif()
    if(NOT HAS_JSON)
        message(STATUS "  缺少 nlohmann_json")
    endif()
    message(STATUS "")
endif()

# ============================================================
# 数据记录器 (DataRecorder)
# ============================================================
# 将实盘行情数据存入 Redis，用于历史数据备份
# 依赖: ZeroMQ + hiredis

find_library(HIREDIS_LIBRARY NAMES hiredis
    PATHS 
        /usr/local/lib 
        /opt/homebrew/lib 
        /usr/lib
        /usr/lib/x86_64-linux-gnu
)
find_path(HIREDIS_INCLUDE_DIR hiredis/hiredis.h
    PATHS /usr/local/include /opt/homebrew/include /usr/include
)

if(HIREDIS_LIBRARY AND HIREDIS_INCLUDE_DIR)
    set(HIREDIS_FOUND TRUE)
    message(STATUS "Found hiredis: ${HIREDIS_LIBRARY}")
    message(STATUS "Found hiredis include: ${HIREDIS_INCLUDE_DIR}")
else()
    set(HIREDIS_FOUND FALSE)
    message(STATUS "hiredis not found - data_recorder will not be built")
    message(STATUS "  安装方法:")
    message(STATUS "    macOS: brew install hiredis")
    message(STATUS "    Ubuntu: apt install libhiredis-dev")
endif()

if(HIREDIS_FOUND AND ZMQ_FOUND AND CPPZMQ_FOUND AND HAS_JSON)
    message(STATUS "")
    message(STATUS "========================================")
    message(STATUS "  Building Data Recorder")
    message(STATUS "========================================")
    
    add_executable(data_recorder
        server/data_recorder.cpp
    )
    target_include_directories(data_recorder 
        PRIVATE ${CMAKE_SOURCE_DIR}
        PRIVATE ${ZMQ_INCLUDE_DIR}
        PRIVATE ${CPPZMQ_INCLUDE_DIR}
        PRIVATE ${HIREDIS_INCLUDE_DIR}
    )
    target_compile_options(data_recorder PRIVATE -O3 -march=native)
    target_link_libraries(data_recorder
        PRIVATE ${ZMQ_LIBRARY}
        PRIVATE ${HIREDIS_LIBRARY}
        PRIVATE Threads::Threads
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(data_recorder PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    message(STATUS "  ✓ data_recorder 数据记录器（实盘行情 -> Redis）")
    message(STATUS "")
endif()

# ============================================================
# 安装规则
# ============================================================
install(TARGETS main_example test_core DESTINATION bin)
install(DIRECTORY core/ DESTINATION include/trading/core FILES_MATCHING PATTERN "*.h")
install(DIRECTORY strategies/ DESTINATION include/trading/strategies FILES_MATCHING PATTERN "*.h")
install(DIRECTORY utils/ DESTINATION include/trading/utils FILES_MATCHING PATTERN "*.h")
install(DIRECTORY adapters/ DESTINATION include/trading/adapters FILES_MATCHING PATTERN "*.h")
install(DIRECTORY server/ DESTINATION include/trading/server FILES_MATCHING PATTERN "*.h")

# ============================================================
# 打印配置信息
# ============================================================
message(STATUS "")
message(STATUS "========================================")
message(STATUS "  配置摘要")
message(STATUS "========================================")
message(STATUS "  CMake 版本: ${CMAKE_VERSION}")
message(STATUS "  C++ 编译器: ${CMAKE_CXX_COMPILER}")
message(STATUS "  C++ 标准: C++${CMAKE_CXX_STANDARD}")
message(STATUS "  构建类型: ${CMAKE_BUILD_TYPE}")
message(STATUS "  JSON: ${HAS_JSON}")
message(STATUS "  ZeroMQ: ${ZMQ_FOUND}")
message(STATUS "  cppzmq: ${CPPZMQ_FOUND}")
message(STATUS "  CURL: ${CURL_FOUND}")
message(STATUS "  OpenSSL: ${OPENSSL_FOUND}")
message(STATUS "  WebSocket++: ${HAS_WEBSOCKETPP}")
message(STATUS "  Boost: ${Boost_FOUND}")
message(STATUS "========================================")

