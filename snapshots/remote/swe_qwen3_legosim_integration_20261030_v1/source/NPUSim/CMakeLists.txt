# The checked-in official ONNX source requires CMake 3.26 or newer.
cmake_minimum_required(VERSION 3.26)

project(NPUSim LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build the checked-in official ONNX source as part of the Ubuntu/server build.
# ONNX configures or finds Protobuf itself and generates onnx-ml.pb.{h,cc} in
# the CMake build tree.  NPUSim code never hand-decodes protobuf wire fields.
set(ONNX_BUILD_PYTHON OFF CACHE BOOL "" FORCE)
set(ONNX_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(ONNX_BUILD_BENCHMARKS OFF CACHE BOOL "" FORCE)
set(ONNX_BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(ONNX_USE_LITE_PROTO OFF CACHE BOOL "" FORCE)
set(ONNX_GEN_PB_TYPE_STUBS OFF CACHE BOOL "" FORCE)
set(ONNX_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory(onnx EXCLUDE_FROM_ALL)

add_library(npusim_core STATIC
    npusim_runtime.cpp
    npusim_chiplet_memory.cpp
    npusim_chiplet_runtime.cpp
    onnx_official_parser.cpp
    onnx_event_lowering.cpp)
target_include_directories(npusim_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/../Ramulator2-Chiplet
        ${CMAKE_CURRENT_SOURCE_DIR}/../artifact/MLP/json/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../interchiplet/includes)
target_compile_options(npusim_core PRIVATE -Wall -Wextra)
# CMake targets always carry the official frontend.  This turns runModel's
# parser dependency into a strong archive reference, so the linker cannot
# discard onnx_official_parser.cpp while extracting npusim_runtime.cpp.
target_compile_definitions(npusim_core PRIVATE NPUSIM_REQUIRE_OFFICIAL_ONNX=1)
target_link_libraries(npusim_core PUBLIC onnx)

add_executable(npusim main.cpp)
target_include_directories(npusim PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../interchiplet/includes)
target_compile_options(npusim PRIVATE -Wall -Wextra)
target_link_libraries(npusim PRIVATE npusim_core)

find_library(INTERCHIPLET_C_LIBRARY
    NAMES interchiplet_c libinterchiplet_c
    PATHS ${CMAKE_CURRENT_SOURCE_DIR}/../interchiplet/lib
    NO_DEFAULT_PATH)
if(NOT INTERCHIPLET_C_LIBRARY)
    message(FATAL_ERROR "interchiplet/lib/libinterchiplet_c.a is required to link NPUSim")
endif()
target_link_libraries(npusim PRIVATE ${INTERCHIPLET_C_LIBRARY})

find_package(Threads REQUIRED)

# A copied workload template can request an ONNX chiplet wrapper without
# copying official-ONNX link flags into every benchmark Makefile.  The source
# path is deliberately a cache variable: users normally point it at
# benchmark/<workload>/npu_onnx_chiplet_workload.cpp.
set(NPUSIM_ONNX_CHIPLET_WRAPPER_SOURCE "" CACHE FILEPATH
    "Optional C++ ONNX chiplet wrapper source built against npusim_core")
if(NPUSIM_ONNX_CHIPLET_WRAPPER_SOURCE)
    if(NOT EXISTS "${NPUSIM_ONNX_CHIPLET_WRAPPER_SOURCE}")
        message(FATAL_ERROR
            "NPUSIM_ONNX_CHIPLET_WRAPPER_SOURCE does not exist: ${NPUSIM_ONNX_CHIPLET_WRAPPER_SOURCE}")
    endif()
    add_executable(npusim_onnx_chiplet_wrapper
        "${NPUSIM_ONNX_CHIPLET_WRAPPER_SOURCE}")
    target_include_directories(npusim_onnx_chiplet_wrapper PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../interchiplet/includes)
    target_compile_options(npusim_onnx_chiplet_wrapper PRIVATE -Wall -Wextra)
    target_link_libraries(npusim_onnx_chiplet_wrapper PRIVATE
        npusim_core ${INTERCHIPLET_C_LIBRARY} Threads::Threads)
endif()

option(NPUSIM_BUILD_SMOKE_TESTS "Build NPUSim runtime smoke executables" ON)
if(NPUSIM_BUILD_SMOKE_TESTS)
    # Smoke sources are useful for a full developer checkout, but a minimal
    # workload delivery may intentionally omit them.  They must never prevent
    # the normal NPUSim/ONNX executable from being configured.
    function(add_npusim_optional_smoke target source)
        if(NOT EXISTS "${source}")
            message(STATUS "Skipping optional NPUSim smoke '${target}': source not found")
            return()
        endif()
        add_executable(${target} "${source}")
        if(ARGC GREATER 2)
            target_link_libraries(${target} PRIVATE ${ARGN})
        endif()
    endfunction()

    add_npusim_optional_smoke(npusim_chiplet_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_chiplet_smoke.cpp"
        npusim_core ${INTERCHIPLET_C_LIBRARY})
    add_npusim_optional_smoke(npusim_onnx_matmul_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_onnx_matmul_smoke.cpp"
        npusim_core)
    add_npusim_optional_smoke(npusim_onnx_event_lowering_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_onnx_event_lowering_smoke.cpp"
        npusim_core)
    add_npusim_optional_smoke(npusim_onnx_functional_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_onnx_functional_smoke.cpp"
        npusim_core)
    add_npusim_optional_smoke(npusim_tensor_codec_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_tensor_codec_smoke.cpp")
    if(TARGET npusim_tensor_codec_smoke)
        target_include_directories(npusim_tensor_codec_smoke PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    endif()
    add_npusim_optional_smoke(npusim_qwen_ops_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_qwen_ops_smoke.cpp"
        npusim_core)
    add_npusim_optional_smoke(npusim_request_wait_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_request_wait_smoke.cpp"
        npusim_core)
    add_npusim_optional_smoke(npusim_compute_memory_compute_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/npusim_compute_memory_compute_smoke.cpp"
        npusim_core)
endif()
