CXX ?= g++

override SIMULATOR_ROOT := $(abspath ..)
RAMULATOR_ROOT ?= $(abspath $(SIMULATOR_ROOT)/ramulator2)
INTERCHIPLET_ROOT ?= $(abspath $(SIMULATOR_ROOT)/interchiplet)

CXXFLAGS = -std=c++2a -O2 -Wall -Wextra \
	-I. \
	-I$(RAMULATOR_ROOT)/src \
	-I$(INTERCHIPLET_ROOT)/includes

LDFLAGS = \
	-L$(RAMULATOR_ROOT) \
	-lramulator \
	-Wl,-rpath,'$$ORIGIN/../ramulator2'

TARGET = ramulator2
SOURCES = main.cpp dram_func.cpp ramulator2_wrapper.cpp
OBJECTS = $(SOURCES:.cpp=.o)

.PHONY: all clean probe

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

probe: ramulator2_wrapper_probe

ramulator2_wrapper_probe: ramulator2_wrapper_probe.cpp ramulator2_wrapper.cpp
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

clean:
	rm -f $(OBJECTS) $(TARGET) ramulator2_wrapper_probe
