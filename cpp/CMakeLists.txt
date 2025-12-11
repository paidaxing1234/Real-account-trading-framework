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

# 可选：WebSocket++ 和 OpenSSL（用于OKX WebSocket）
# find_package(websocketpp REQUIRED)
# find_package(OpenSSL REQUIRED)

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

# OKX适配器库（需要实现.cpp文件后取消注释）
# add_library(okx_adapter
#     adapters/okx/okx_rest_api.cpp
#     adapters/okx/okx_websocket.cpp
#     adapters/okx/okx_adapter.cpp
# )
# target_link_libraries(okx_adapter
#     PUBLIC trading_core
#     PRIVATE nlohmann_json::nlohmann_json
#     # PRIVATE websocketpp::websocketpp
#     # PRIVATE OpenSSL::SSL OpenSSL::Crypto
# )

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

# 安装规则
install(TARGETS main_example test_core test_journal_latency test_journal_benchmark test_latency_precise test_disruptor_latency test_disruptor_benchmark DESTINATION bin)
install(DIRECTORY core/ DESTINATION include/trading/core FILES_MATCHING PATTERN "*.h")
install(DIRECTORY strategies/ DESTINATION include/trading/strategies FILES_MATCHING PATTERN "*.h")
install(DIRECTORY utils/ DESTINATION include/trading/utils FILES_MATCHING PATTERN "*.h")
install(DIRECTORY adapters/ DESTINATION include/trading/adapters FILES_MATCHING PATTERN "*.h")

# 打印配置信息
message(STATUS "CMake version: ${CMAKE_VERSION}")
message(STATUS "C++ compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "C++ standard: C++${CMAKE_CXX_STANDARD}")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")

