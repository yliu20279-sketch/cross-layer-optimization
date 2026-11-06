#新的编译脚本

#https://blog.csdn.net/liitdar/article/details/81144461

cmake_minimum_required(VERSION 3.0)

project(popnet)

set(CMAKE_CXX_STANDARD 17)
#set(CMAKE_BUILD_TYPE DEBUG)
set(CMAKE_BUILD_TYPE RELEASE)

set(POWER_RELEASE orion_power_beta_mar2003)
set(GRAPH_LIB graph_lib)

add_subdirectory(${POWER_RELEASE}/power)
add_subdirectory(${GRAPH_LIB})

set(CMAKE_CXX_FLAGS "-DS_OUT_DEBUG -Wno-deprecated -g -DPOWER_TEST")
include_directories(${POWER_RELEASE}/power ${POWER_RELEASE}/library)
include_directories(${GRAPH_LIB})

set(SIM_SRCS SString.cc SStd.cc SRGen.cc configuration.cc flit.cc sim_router.cc sim_routing.cc sim_vcarb.cc  mess_event.cc sim_foundation.cc sim_protoengine.cc mess_queue.cc coupled_main.cc)
aux_source_directory(changes NEW_SRCS)

link_directories(${POWER_RELEASE}/power)

find_package(Boost REQUIRED COMPONENTS
   graph
)
include_directories(${Boost_INCLUDE_DIRS})

add_executable(popnet ${SIM_SRCS} ${NEW_SRCS})

target_link_libraries(popnet orion_power mygraph)

target_link_libraries(popnet ${Boost_LIBRARIES})

set(RAMULATOR_ROOT "$ENV{RAMULATOR_ROOT}")
if(NOT EXISTS "${RAMULATOR_ROOT}/src" OR NOT EXISTS "${RAMULATOR_ROOT}/libramulator.so")
  message(FATAL_ERROR "RAMULATOR_ROOT must name the isolated Ramulator2 build")
endif()
include_directories("${RAMULATOR_ROOT}/src")
target_link_libraries(popnet "${RAMULATOR_ROOT}/libramulator.so")
set_target_properties(popnet PROPERTIES BUILD_RPATH "${RAMULATOR_ROOT}")




# CMD006
target_link_libraries(popnet "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/thermal_bridge.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/microchannel.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/materials.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/temperature.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/RCutil.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/package.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/temperature_block.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/temperature_grid.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/flp.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/flp_desc.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/npe.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/shape.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/util.o" "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006/hotspot_src/wire.o" m)
