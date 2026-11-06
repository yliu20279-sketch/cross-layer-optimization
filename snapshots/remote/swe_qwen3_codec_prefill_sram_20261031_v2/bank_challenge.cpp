#include "npusim_chiplet_runtime.h"
#include <iostream>
// Test-only access visibility; production header and executable remain frozen.
#include "sram_kernel_public_test.h"
int main(int argc,char**argv){
 NPUSim::NPUConfig c;c.external_memory_enable=true;c.external_memory_model="chiplet";c.dram_chiplet_x=0;c.dram_chiplet_y=8;c.dram_chiplet_grid_cols=4;c.dram_size_bytes=536870912;c.dram_chiplet_region_bytes=536870912;c.mac_unit_count=4096;c.sram_per_mac_bytes=1024;c.vector_ops_per_cycle=16;c.reduce_ops_per_cycle=16;
 c.intra_delay_enable=false;
 NPUSim::ChipletNpuRuntimeOptions o;o.report_directory=argv[1];NPUSim::ChipletNpuRuntime r(c,o);ExplicitSramKernel k(r,argv[1]);
 auto n=r.chipCycle();k.access({{0,32},{256,32}},false);if(r.chipCycle()-n!=2)return 2;
 n=r.chipCycle();k.access({{0,32},{32,32}},false);if(r.chipCycle()-n!=1)return 3;
 n=r.chipCycle();k.access({{0,64},{256,64},{512,64}},false);if(r.chipCycle()-n!=3)return 4;
 int refused=0;try{k.access({{4194300,8}},true);}catch(const std::runtime_error&){refused++;}
 try{k.run(0,0,0,2049,768,argv[1]);}catch(const std::runtime_error&){refused++;}
 if(refused!=2)return 5;
 std::cout<<"PASS_3_BANK_CONFLICT_CHALLENGES_2_FAIL_CLOSED_CONTROLS\n";
}
