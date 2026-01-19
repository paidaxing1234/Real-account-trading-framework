cmake_minimum_required(VERSION 3.15)

# 添加Journal测试程序
add_executable(test_journal_latency test_journal_latency.cpp)
target_include_directories(test_journal_latency PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_journal_latency PRIVATE -O3 -march=native)

add_executable(test_journal_benchmark test_journal_benchmark.cpp)
target_include_directories(test_journal_benchmark PRIVATE ${CMAKE_SOURCE_DIR})
target_compile_options(test_journal_benchmark PRIVATE -O3 -march=native)

<<<<<<< HEAD
# 安装
install(TARGETS test_journal_latency test_journal_benchmark
=======
# 账户管理器测试程序
add_executable(test_manager test_manager.cpp)
target_include_directories(test_manager PRIVATE ${CMAKE_SOURCE_DIR})
target_link_libraries(test_manager
    PRIVATE okx_rest_api binance_rest_api logger trading_core Threads::Threads
)
if(nlohmann_json_FOUND)
    target_link_libraries(test_manager PRIVATE nlohmann_json::nlohmann_json)
endif()

# 安装
install(TARGETS test_journal_latency test_journal_benchmark test_manager
>>>>>>> origin/master
        RUNTIME DESTINATION bin)

