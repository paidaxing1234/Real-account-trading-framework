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

# nlohmann/json (header-only)
find_package(nlohmann_json 3.2.0 QUIET)
if(nlohmann_json_FOUND)
    message(STATUS "Found nlohmann_json: ${nlohmann_json_VERSION}")
    set(HAS_JSON TRUE)
else()
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/external/include/nlohmann/json.hpp")
        message(STATUS "Using manually downloaded nlohmann_json")
        include_directories(${CMAKE_CURRENT_SOURCE_DIR}/external/include)
        set(HAS_JSON TRUE)
    else()
        message(FATAL_ERROR "nlohmann_json not found. Install with: brew install nlohmann-json")
    endif()
endif()

# 查找 OpenSSL
find_package(OpenSSL REQUIRED)
message(STATUS "Found OpenSSL: ${OPENSSL_VERSION}")

# 查找 CURL
find_package(CURL REQUIRED)
message(STATUS "Found CURL")

# 包含目录
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${CMAKE_CURRENT_SOURCE_DIR}/adapters
    ${CMAKE_CURRENT_SOURCE_DIR}/strategies
    ${CMAKE_CURRENT_SOURCE_DIR}/utils
    ${CMAKE_CURRENT_SOURCE_DIR}/papertrading
    ${CMAKE_CURRENT_SOURCE_DIR}/server
)

# 核心库（header-only）
add_library(trading_core INTERFACE)
target_include_directories(trading_core INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/core)

# ============================================================
# OKX WebSocket 库
# ============================================================
find_path(WEBSOCKETPP_INCLUDE_DIR websocketpp/config/asio_client.hpp
    PATHS /usr/local/include /opt/homebrew/include /usr/include)

find_path(ASIO_INCLUDE_DIR asio.hpp
    PATHS /usr/local/include /opt/homebrew/include /usr/include)

if(POLICY CMP0167)
    cmake_policy(SET CMP0167 OLD)
endif()
find_package(Boost COMPONENTS system QUIET)

if(WEBSOCKETPP_INCLUDE_DIR AND ASIO_INCLUDE_DIR)
    set(HAS_WEBSOCKETPP TRUE)
    message(STATUS "Found websocketpp: ${WEBSOCKETPP_INCLUDE_DIR}")
    message(STATUS "Found standalone ASIO: ${ASIO_INCLUDE_DIR}")
    
    add_library(okx_websocket adapters/okx/okx_websocket.cpp)
    target_include_directories(okx_websocket
        PUBLIC ${CMAKE_SOURCE_DIR}
        PUBLIC ${WEBSOCKETPP_INCLUDE_DIR}
        PUBLIC ${ASIO_INCLUDE_DIR}
    )
    target_compile_definitions(okx_websocket PRIVATE 
        USE_WEBSOCKETPP ASIO_STANDALONE _WEBSOCKETPP_CPP11_STL_
    )
    target_link_libraries(okx_websocket
        PUBLIC trading_core
        PRIVATE OpenSSL::SSL OpenSSL::Crypto Threads::Threads
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(okx_websocket PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ okx_websocket 库")
    
elseif(WEBSOCKETPP_INCLUDE_DIR AND Boost_FOUND)
    set(HAS_WEBSOCKETPP TRUE)
    message(STATUS "Found websocketpp with Boost.ASIO")
    
    add_library(okx_websocket adapters/okx/okx_websocket.cpp)
    target_include_directories(okx_websocket
        PUBLIC ${CMAKE_SOURCE_DIR}
        PUBLIC ${WEBSOCKETPP_INCLUDE_DIR}
        PUBLIC ${Boost_INCLUDE_DIRS}
    )
    target_compile_definitions(okx_websocket PRIVATE 
        USE_WEBSOCKETPP BOOST_ASIO_NO_DEPRECATED _WEBSOCKETPP_CPP11_STL_
    )
    target_link_libraries(okx_websocket
        PUBLIC trading_core
        PRIVATE OpenSSL::SSL OpenSSL::Crypto ${Boost_LIBRARIES}
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(okx_websocket PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ okx_websocket 库 (Boost.ASIO)")
else()
    message(FATAL_ERROR "WebSocket++ not found. Install with: brew install websocketpp asio")
endif()

# OKX REST API 库
add_library(okx_rest_api adapters/okx/okx_rest_api.cpp)
target_link_libraries(okx_rest_api
    PUBLIC trading_core
    PRIVATE CURL::libcurl OpenSSL::SSL OpenSSL::Crypto
)
if(nlohmann_json_FOUND)
    target_link_libraries(okx_rest_api PRIVATE nlohmann_json::nlohmann_json)
endif()
message(STATUS "  ✓ okx_rest_api 库")

# Binance REST API 库
add_library(binance_rest_api adapters/binance/binance_rest_api.cpp)
target_link_libraries(binance_rest_api
    PUBLIC trading_core
    PRIVATE CURL::libcurl OpenSSL::SSL OpenSSL::Crypto
)
if(nlohmann_json_FOUND)
    target_link_libraries(binance_rest_api PRIVATE nlohmann_json::nlohmann_json)
endif()
message(STATUS "  ✓ binance_rest_api 库")

# Binance WebSocket 库
if(HAS_WEBSOCKETPP)
    add_library(binance_websocket adapters/binance/binance_websocket.cpp)
    target_include_directories(binance_websocket
        PUBLIC ${CMAKE_SOURCE_DIR}
        PUBLIC ${WEBSOCKETPP_INCLUDE_DIR}
    )
    if(ASIO_INCLUDE_DIR)
        target_include_directories(binance_websocket PUBLIC ${ASIO_INCLUDE_DIR})
        target_compile_definitions(binance_websocket PRIVATE 
            USE_WEBSOCKETPP ASIO_STANDALONE _WEBSOCKETPP_CPP11_STL_
        )
    elseif(Boost_FOUND)
        target_include_directories(binance_websocket PUBLIC ${Boost_INCLUDE_DIRS})
        target_compile_definitions(binance_websocket PRIVATE 
            USE_WEBSOCKETPP BOOST_ASIO_NO_DEPRECATED _WEBSOCKETPP_CPP11_STL_
        )
        target_link_libraries(binance_websocket PRIVATE ${Boost_LIBRARIES})
    endif()
    target_link_libraries(binance_websocket
        PUBLIC trading_core binance_rest_api
        PRIVATE OpenSSL::SSL OpenSSL::Crypto Threads::Threads
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(binance_websocket PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ binance_websocket 库")
else()
    message(STATUS "  ⚠ binance_websocket 跳过 (缺少 websocketpp)")
endif()

# ============================================================
# ZeroMQ
# ============================================================
find_library(ZMQ_LIBRARY NAMES zmq libzmq
    PATHS /usr/local/lib /opt/homebrew/lib /usr/lib /usr/lib/x86_64-linux-gnu
    NO_DEFAULT_PATH
)
if(NOT ZMQ_LIBRARY)
    find_library(ZMQ_LIBRARY NAMES zmq libzmq)
endif()

find_path(ZMQ_INCLUDE_DIR zmq.h 
    PATHS /usr/local/include /opt/homebrew/include /usr/include)

find_path(CPPZMQ_INCLUDE_DIR zmq.hpp
    PATHS /usr/local/include /opt/homebrew/include /usr/include ${ZMQ_INCLUDE_DIR})

if(NOT ZMQ_LIBRARY OR NOT CPPZMQ_INCLUDE_DIR)
    message(FATAL_ERROR "ZeroMQ not found. Install with: brew install zeromq cppzmq")
endif()

message(STATUS "Found ZeroMQ: ${ZMQ_LIBRARY}")
message(STATUS "Found cppzmq: ${CPPZMQ_INCLUDE_DIR}")

# ZMQ 服务端库
add_library(zmq_server server/zmq_server.cpp)
target_include_directories(zmq_server 
    PUBLIC ${CMAKE_SOURCE_DIR}
    PUBLIC ${ZMQ_INCLUDE_DIR}
    PUBLIC ${CPPZMQ_INCLUDE_DIR}
)
target_link_libraries(zmq_server PUBLIC ${ZMQ_LIBRARY})
if(nlohmann_json_FOUND)
    target_link_libraries(zmq_server PUBLIC nlohmann_json::nlohmann_json)
endif()
message(STATUS "  ✓ zmq_server 库")

# WebSocket 服务端库
add_library(websocket_server core/websocket_server.cpp)
target_include_directories(websocket_server 
    PUBLIC ${CMAKE_SOURCE_DIR}
)
target_link_libraries(websocket_server 
    PUBLIC trading_core
    PRIVATE Threads::Threads
)
if(nlohmann_json_FOUND)
    target_link_libraries(websocket_server PUBLIC nlohmann_json::nlohmann_json)
endif()
message(STATUS "  ✓ websocket_server 库")

# ============================================================
# 主要目标: trading_server_full
# ============================================================
message(STATUS "")
message(STATUS "========================================")
message(STATUS "  构建目标")
message(STATUS "========================================")

add_executable(trading_server_full server/trading_server_full.cpp)
target_include_directories(trading_server_full PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(trading_server_full PRIVATE -O3 -march=native)
target_link_libraries(trading_server_full
    PRIVATE zmq_server okx_rest_api okx_websocket trading_core Threads::Threads
)
if(nlohmann_json_FOUND)
    target_link_libraries(trading_server_full PRIVATE nlohmann_json::nlohmann_json)
endif()

# Linux: 链接 libnuma
if(UNIX AND NOT APPLE)
    find_library(NUMA_LIBRARY numa)
    if(NUMA_LIBRARY)
        target_link_libraries(trading_server_full PRIVATE ${NUMA_LIBRARY})
    endif()
endif()

message(STATUS "  ✓ trading_server_full 实盘服务器")

# ============================================================
# Paper Trading 库
# ============================================================
if(HAS_WEBSOCKETPP)
    # Mock Account Engine 库
    add_library(mock_account_engine papertrading/mock_account_engine.cpp)
    target_include_directories(mock_account_engine
        PUBLIC ${CMAKE_SOURCE_DIR}
    )
    target_link_libraries(mock_account_engine
        PUBLIC trading_core
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(mock_account_engine PUBLIC nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ mock_account_engine 库")
    
    # Order Execution Engine 库
    add_library(order_execution_engine papertrading/order_execution_engine.cpp)
    target_include_directories(order_execution_engine
        PUBLIC ${CMAKE_SOURCE_DIR}
    )
    target_link_libraries(order_execution_engine
        PUBLIC mock_account_engine trading_core
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(order_execution_engine PUBLIC nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ order_execution_engine 库")
else()
    message(STATUS "  ⚠ papertrading 库跳过 (缺少 websocketpp)")
endif()

# ============================================================
# 主要目标: papertrading_server
# ============================================================
if(HAS_WEBSOCKETPP)
    add_executable(papertrading_server 
        papertrading/main.cpp 
        papertrading/papertrading_server.cpp
        papertrading/papertrading_config.cpp
    )
    target_include_directories(papertrading_server 
        PRIVATE ${CMAKE_SOURCE_DIR}
        PRIVATE ${ZMQ_INCLUDE_DIR}
        PRIVATE ${CPPZMQ_INCLUDE_DIR}
    )
    if(ASIO_INCLUDE_DIR)
        target_include_directories(papertrading_server PRIVATE ${ASIO_INCLUDE_DIR})
    elseif(Boost_FOUND)
        target_include_directories(papertrading_server PRIVATE ${Boost_INCLUDE_DIRS})
    endif()
    target_compile_options(papertrading_server PRIVATE -O3 -march=native)
    target_link_libraries(papertrading_server
        PRIVATE zmq_server 
        PRIVATE okx_websocket
        PRIVATE mock_account_engine
        PRIVATE order_execution_engine
        PRIVATE websocket_server
        PRIVATE trading_core
        PRIVATE ${ZMQ_LIBRARY}
        PRIVATE Threads::Threads
    )
    if(Boost_FOUND)
        target_link_libraries(papertrading_server PRIVATE ${Boost_LIBRARIES})
    endif()
    if(nlohmann_json_FOUND)
        target_link_libraries(papertrading_server PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ papertrading_server 模拟交易服务器")
else()
    message(STATUS "  ⚠ papertrading_server 跳过 (缺少 websocketpp)")
endif()

# ============================================================
# 主要目标: data_recorder
# ============================================================
find_library(HIREDIS_LIBRARY NAMES hiredis
    PATHS /usr/local/lib /opt/homebrew/lib /usr/lib /usr/lib/x86_64-linux-gnu)
find_path(HIREDIS_INCLUDE_DIR hiredis/hiredis.h
    PATHS /usr/local/include /opt/homebrew/include /usr/include)

if(HIREDIS_LIBRARY AND HIREDIS_INCLUDE_DIR)
    add_executable(data_recorder server/data_recorder.cpp)
    target_include_directories(data_recorder 
        PRIVATE ${CMAKE_SOURCE_DIR}
        PRIVATE ${ZMQ_INCLUDE_DIR}
        PRIVATE ${CPPZMQ_INCLUDE_DIR}
        PRIVATE ${HIREDIS_INCLUDE_DIR}
    )
    target_compile_options(data_recorder PRIVATE -O3 -march=native)
    target_link_libraries(data_recorder
        PRIVATE ${ZMQ_LIBRARY} ${HIREDIS_LIBRARY} Threads::Threads
    )
    if(nlohmann_json_FOUND)
        target_link_libraries(data_recorder PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ data_recorder 数据记录器")
else()
    message(STATUS "  ⚠ data_recorder 跳过 (缺少 hiredis)")
    message(STATUS "    安装: brew install hiredis (macOS) / apt install libhiredis-dev (Ubuntu)")
endif()

# ============================================================
# 主要目标: strategy_base Python 模块
# ============================================================
find_package(Python3 COMPONENTS Interpreter Development QUIET)
find_package(pybind11 CONFIG QUIET)

if(NOT pybind11_FOUND AND Python3_FOUND)
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -c "import pybind11; print(pybind11.get_cmake_dir())"
        OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )
    if(PYBIND11_CMAKE_DIR)
        list(APPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKE_DIR}")
        find_package(pybind11 CONFIG QUIET)
    endif()
endif()

if(pybind11_FOUND AND Python3_FOUND)
    pybind11_add_module(strategy_base strategies/py_strategy_bindings.cpp)
    target_include_directories(strategy_base PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/strategies
        ${ZMQ_INCLUDE_DIR}
        ${CPPZMQ_INCLUDE_DIR}
    )
    target_link_libraries(strategy_base PRIVATE ${ZMQ_LIBRARY})
    if(nlohmann_json_FOUND)
        target_link_libraries(strategy_base PRIVATE nlohmann_json::nlohmann_json)
    endif()
    
    # 编译后复制到 strategies 目录
    add_custom_command(TARGET strategy_base POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:strategy_base> 
                ${CMAKE_SOURCE_DIR}/strategies/
        COMMENT "Copying strategy_base module to strategies/"
    )
    
    message(STATUS "  ✓ strategy_base Python 模块 (Python ${Python3_VERSION})")
else()
    message(STATUS "  ⚠ strategy_base 跳过 (缺少 pybind11)")
    message(STATUS "    安装: pip install pybind11")
endif()

# ============================================================
# 示例和测试程序
# ============================================================
# OKX资金费率测试(REST API)
add_executable(test_okx_funding_rate examples/test_okx_funding_rate.cpp)
target_include_directories(test_okx_funding_rate PRIVATE ${CMAKE_SOURCE_DIR})
target_link_libraries(test_okx_funding_rate PRIVATE okx_rest_api)
if(nlohmann_json_FOUND)
    target_link_libraries(test_okx_funding_rate PRIVATE nlohmann_json::nlohmann_json)
endif()
message(STATUS "  ✓ test_okx_funding_rate 资金费率测试(REST)")

# OKX资金费率WebSocket测试
add_executable(test_okx_ws_funding_rate examples/test_okx_ws_funding_rate.cpp)
target_include_directories(test_okx_ws_funding_rate PRIVATE ${CMAKE_SOURCE_DIR})
target_link_libraries(test_okx_ws_funding_rate PRIVATE okx_websocket)
if(nlohmann_json_FOUND)
    target_link_libraries(test_okx_ws_funding_rate PRIVATE nlohmann_json::nlohmann_json)
endif()
message(STATUS "  ✓ test_okx_ws_funding_rate 资金费率测试(WebSocket)")

# Binance现货测试
add_executable(test_binance_spot examples/test_binance_spot.cpp)
target_include_directories(test_binance_spot PRIVATE ${CMAKE_SOURCE_DIR})
target_link_libraries(test_binance_spot PRIVATE binance_rest_api)
if(nlohmann_json_FOUND)
    target_link_libraries(test_binance_spot PRIVATE nlohmann_json::nlohmann_json)
endif()
message(STATUS "  ✓ test_binance_spot 币安现货测试")

# Binance WebSocket测试
if(HAS_WEBSOCKETPP)
    # WebSocket交易API测试
    add_executable(test_binance_ws_trading examples/test_binance_ws_trading.cpp)
    target_include_directories(test_binance_ws_trading PRIVATE ${CMAKE_SOURCE_DIR})
    target_link_libraries(test_binance_ws_trading PRIVATE binance_websocket)
    if(nlohmann_json_FOUND)
        target_link_libraries(test_binance_ws_trading PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_binance_ws_trading 币安WebSocket交易测试")
    
    # WebSocket行情推送测试
    add_executable(test_binance_ws_market examples/test_binance_ws_market.cpp)
    target_include_directories(test_binance_ws_market PRIVATE ${CMAKE_SOURCE_DIR})
    target_link_libraries(test_binance_ws_market PRIVATE binance_websocket)
    if(nlohmann_json_FOUND)
        target_link_libraries(test_binance_ws_market PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_binance_ws_market 币安WebSocket行情测试")

    # WebSocket(测试网)逐笔成交单项测试
    add_executable(test_binance_ws_trade_testnet examples/test_binance_ws_trade_testnet.cpp)
    target_include_directories(test_binance_ws_trade_testnet PRIVATE ${CMAKE_SOURCE_DIR})
    target_link_libraries(test_binance_ws_trade_testnet PRIVATE binance_websocket)
    if(nlohmann_json_FOUND)
        target_link_libraries(test_binance_ws_trade_testnet PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_binance_ws_trade_testnet 币安WS测试网逐笔成交测试")

    # WebSocket(测试网)K线单项测试
    add_executable(test_binance_ws_kline_testnet examples/test_binance_ws_kline_testnet.cpp)
    target_include_directories(test_binance_ws_kline_testnet PRIVATE ${CMAKE_SOURCE_DIR})
    target_link_libraries(test_binance_ws_kline_testnet PRIVATE binance_websocket)
    if(nlohmann_json_FOUND)
        target_link_libraries(test_binance_ws_kline_testnet PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_binance_ws_kline_testnet 币安WS测试网K线测试")

    # WebSocket(测试网)行情推送全量订阅测试
    add_executable(test_binance_ws_all_market_testnet examples/test_binance_ws_all_market_testnet.cpp)
    target_include_directories(test_binance_ws_all_market_testnet PRIVATE ${CMAKE_SOURCE_DIR})
    target_link_libraries(test_binance_ws_all_market_testnet PRIVATE binance_websocket)
    if(nlohmann_json_FOUND)
        target_link_libraries(test_binance_ws_all_market_testnet PRIVATE nlohmann_json::nlohmann_json)
    endif()
    message(STATUS "  ✓ test_binance_ws_all_market_testnet 币安WS测试网全量行情推送测试")
endif()

# ============================================================
# 配置摘要
# ============================================================
message(STATUS "")
message(STATUS "========================================")
message(STATUS "  配置摘要")
message(STATUS "========================================")
message(STATUS "  CMake: ${CMAKE_VERSION}")
message(STATUS "  C++: ${CMAKE_CXX_COMPILER}")
message(STATUS "  标准: C++${CMAKE_CXX_STANDARD}")
message(STATUS "  构建: ${CMAKE_BUILD_TYPE}")
message(STATUS "")
message(STATUS "  使用方法:")
message(STATUS "    make trading_server_full")
message(STATUS "    make papertrading_server")
message(STATUS "    make data_recorder")
message(STATUS "    make strategy_base")
message(STATUS "    OKX测试:")
message(STATUS "      make test_okx_funding_rate")
message(STATUS "      make test_okx_ws_funding_rate")
message(STATUS "    Binance测试:")
message(STATUS "      make test_binance_spot")
message(STATUS "      make test_binance_ws_trading")
message(STATUS "      make test_binance_ws_market")
message(STATUS "========================================")
