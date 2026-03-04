CXX      := g++
CXXFLAGS := -std=c++17 -O2 -Wall
LIBS_ZMQ := -lzmq
LIBS_REDIS := -lhiredis

# 自动查找 nlohmann/json
NLOHMANN := $(shell find /usr/include /usr/local/include -name "json.hpp" -path "*/nlohmann/*" 2>/dev/null | head -1 | xargs dirname | xargs dirname)
ifneq ($(NLOHMANN),)
    CXXFLAGS += -I$(NLOHMANN)
endif

.PHONY: all clean

all: kline_latency_monitor kline_8h_monitor kline_5m_monitor

kline_latency_monitor: kline_latency_monitor.cpp
	$(CXX) $(CXXFLAGS) $< $(LIBS_ZMQ) -o $@
	@echo "编译成功: $@"

kline_8h_monitor: kline_8h_monitor.cpp
	$(CXX) $(CXXFLAGS) $< $(LIBS_REDIS) -o $@
	@echo "编译成功: $@"

kline_5m_monitor: kline_5m_monitor.cpp
	$(CXX) $(CXXFLAGS) $< $(LIBS_REDIS) -o $@
	@echo "编译成功: $@"

clean:
	rm -f kline_latency_monitor kline_8h_monitor kline_5m_monitor
