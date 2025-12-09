# PyBind11 绑定配置

cmake_minimum_required(VERSION 3.15)

# 查找Python
find_package(Python COMPONENTS Interpreter Development REQUIRED)

# 查找或下载PyBind11
include(FetchContent)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# 创建Python模块
pybind11_add_module(trading_cpp 
    python_bindings.cpp
)

# 包含核心头文件
target_include_directories(trading_cpp PRIVATE
    ${CMAKE_SOURCE_DIR}/core
    ${CMAKE_SOURCE_DIR}/adapters
    ${CMAKE_SOURCE_DIR}/strategies
    ${CMAKE_SOURCE_DIR}/utils
)

# 链接选项（优化性能）
target_compile_options(trading_cpp PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/O2>
    $<$<CXX_COMPILER_ID:GNU,Clang>:-O3 -march=native>
)

# 设置输出目录
set_target_properties(trading_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/build
)

# 安装规则
install(TARGETS trading_cpp
    LIBRARY DESTINATION ${Python_SITELIB}
)

