file(REMOVE_RECURSE
  "/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/toolchain/ramulator2_cross_request_v1/libramulator.pdb"
  "/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/toolchain/ramulator2_cross_request_v1/libramulator.so"
)

# Per-language clean rules from dependency scanning.
foreach(lang CXX)
  include(CMakeFiles/ramulator.dir/cmake_clean_${lang}.cmake OPTIONAL)
endforeach()
