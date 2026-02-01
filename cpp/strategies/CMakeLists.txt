# CMakeLists.txt for Python Strategy Base Module
# 
# 编译生成 strategy_base.cpython-*.so 模块
# 
# 使用方法:
#   mkdir build && cd build
#   cmake ..
#   make
#
# 编译后将生成 strategy_base.cpython-*.so，可直接在 Python 中 import

cmake_minimum_required(VERSION 3.15)
project(StrategyBase LANGUAGES CXX)

# C++17 标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 编译选项（优化）
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native")

# ============================================================
# 查找依赖
# ============================================================

# 查找 Python 和 pybind11
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)
find_package(pybind11 CONFIG QUIET)

if(NOT pybind11_FOUND)
    # 尝试通过 pip 安装的 pybind11 找到
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -c "import pybind11; print(pybind11.get_cmake_dir())"
        OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )
    if(PYBIND11_CMAKE_DIR)
        list(APPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKE_DIR}")
        find_package(pybind11 CONFIG REQUIRED)
    else()
        message(FATAL_ERROR "pybind11 not found. Install with: pip install pybind11")
    endif()
endif()

message(STATUS "Found pybind11: ${pybind11_VERSION}")
message(STATUS "Python: ${Python3_EXECUTABLE} (${Python3_VERSION})")

# 查找 ZeroMQ
find_library(ZMQ_LIBRARY NAMES zmq libzmq
    PATHS 
        /usr/local/lib 
        /opt/homebrew/lib 
        /usr/lib
        /usr/lib/x86_64-linux-gnu
)
find_path(ZMQ_INCLUDE_DIR zmq.h 
    PATHS /usr/local/include /opt/homebrew/include /usr/include)

if(NOT ZMQ_LIBRARY)
    message(FATAL_ERROR "ZeroMQ not found. Install with: brew install zeromq (macOS) or apt install libzmq3-dev (Ubuntu)")
endif()

# 查找 cppzmq
find_path(CPPZMQ_INCLUDE_DIR zmq.hpp
    PATHS 
        /usr/local/include 
        /opt/homebrew/include 
        /usr/include
        ${ZMQ_INCLUDE_DIR}
)

if(NOT CPPZMQ_INCLUDE_DIR)
    message(FATAL_ERROR "cppzmq not found. Install with: brew install cppzmq (macOS)")
endif()

message(STATUS "Found ZeroMQ: ${ZMQ_LIBRARY}")
message(STATUS "Found cppzmq: ${CPPZMQ_INCLUDE_DIR}")

# 查找 nlohmann/json
find_package(nlohmann_json 3.2.0 QUIET)
if(NOT nlohmann_json_FOUND)
    # 尝试手动查找
    find_path(NLOHMANN_JSON_INCLUDE_DIR nlohmann/json.hpp
        PATHS
            /usr/local/include
            /opt/homebrew/include
            /usr/include
            ${CMAKE_CURRENT_SOURCE_DIR}/../external/include
    )
    if(NLOHMANN_JSON_INCLUDE_DIR)
        message(STATUS "Found nlohmann_json: ${NLOHMANN_JSON_INCLUDE_DIR}")
    else()
        message(FATAL_ERROR "nlohmann_json not found. Install with: brew install nlohmann-json")
    endif()
endif()

# 查找 hiredis (Redis客户端库)
find_library(HIREDIS_LIBRARY NAMES hiredis
    PATHS
        /usr/local/lib
        /opt/homebrew/lib
        /usr/lib
        /usr/lib/x86_64-linux-gnu
)
find_path(HIREDIS_INCLUDE_DIR hiredis/hiredis.h
    PATHS /usr/local/include /opt/homebrew/include /usr/include)

if(NOT HIREDIS_LIBRARY)
    message(WARNING "hiredis not found. Install with: apt install libhiredis-dev (Ubuntu)")
else()
    message(STATUS "Found hiredis: ${HIREDIS_LIBRARY}")
    message(STATUS "Found hiredis include: ${HIREDIS_INCLUDE_DIR}")
endif()

# ============================================================
# 构建 Python 模块
# ============================================================

pybind11_add_module(strategy_base
    core/py_strategy_bindings.cpp
    ../server/managers/redis_data_provider.cpp
)

target_include_directories(strategy_base PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${CMAKE_CURRENT_SOURCE_DIR}/..
    ${CMAKE_CURRENT_SOURCE_DIR}/../server
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/managers
    ${ZMQ_INCLUDE_DIR}
    ${CPPZMQ_INCLUDE_DIR}
    ${HIREDIS_INCLUDE_DIR}
)

# 强制添加系统 include 路径（conda 编译器不会自动搜索）
target_compile_options(strategy_base PRIVATE -isystem /usr/include)

if(NLOHMANN_JSON_INCLUDE_DIR)
    target_include_directories(strategy_base PRIVATE ${NLOHMANN_JSON_INCLUDE_DIR})
endif()

target_link_libraries(strategy_base PRIVATE
    ${ZMQ_LIBRARY}
)

if(HIREDIS_LIBRARY)
    target_link_libraries(strategy_base PRIVATE ${HIREDIS_LIBRARY})
endif()

if(nlohmann_json_FOUND)
    target_link_libraries(strategy_base PRIVATE nlohmann_json::nlohmann_json)
endif()

# ============================================================
# 输出信息
# ============================================================

message(STATUS "")
message(STATUS "========================================")
message(STATUS "  Strategy Base Python Module")
message(STATUS "========================================")
message(STATUS "  Python: ${Python3_VERSION}")
message(STATUS "  pybind11: ${pybind11_VERSION}")
message(STATUS "  ZeroMQ: ${ZMQ_LIBRARY}")
message(STATUS "")
message(STATUS "  编译后生成: strategy_base.cpython-*.so")
message(STATUS "  使用方法: from strategy_base import StrategyBase")
message(STATUS "========================================")

