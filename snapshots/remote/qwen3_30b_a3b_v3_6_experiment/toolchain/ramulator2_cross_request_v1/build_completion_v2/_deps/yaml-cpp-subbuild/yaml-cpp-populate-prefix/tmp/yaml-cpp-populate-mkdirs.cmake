# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/ext/yaml-cpp"
  "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-build"
  "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-subbuild/yaml-cpp-populate-prefix"
  "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-subbuild/yaml-cpp-populate-prefix/tmp"
  "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-subbuild/yaml-cpp-populate-prefix/src/yaml-cpp-populate-stamp"
  "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-subbuild/yaml-cpp-populate-prefix/src"
  "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-subbuild/yaml-cpp-populate-prefix/src/yaml-cpp-populate-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-subbuild/yaml-cpp-populate-prefix/src/yaml-cpp-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/toolchain/ramulator2/build_completion_v2/_deps/yaml-cpp-subbuild/yaml-cpp-populate-prefix/src/yaml-cpp-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
