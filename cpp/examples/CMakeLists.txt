cmake_minimum_required(VERSION 3.15)

# 添加Journal测试程序
add_executable(test_journal_latency test_journal_latency.cpp)
target_include_directories(test_journal_latency PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_journal_latency PRIVATE -O3 -march=native)

add_executable(test_journal_benchmark test_journal_benchmark.cpp)
target_include_directories(test_journal_benchmark PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_journal_benchmark PRIVATE -O3 -march=native)

# 安装
install(TARGETS test_journal_latency test_journal_benchmark
        RUNTIME DESTINATION bin)

