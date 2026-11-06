#include "ramulator2_wrapper.h"

#include <cstdint>
#include <iostream>

int main() {
    try {
        memory::Ramulator2Wrapper memory(
            "lpddr5_config.yaml");

        constexpr std::uint64_t address = 0x00100000ULL;
        constexpr std::uint64_t bytes = 411648ULL;

        std::cout
            << "[RAMULATOR2-WRAPPER-PROBE][BOOT]"
            << " tx_bytes=" << memory.transactionBytes()
            << " tCK_ns=" << memory.clockPeriodNs()
            << " bytes=" << bytes
            << '\n';


        const std::uint64_t write_cycles =
            memory.run(true, address, bytes);

        const std::uint64_t read_cycles =
            memory.run(false, address, bytes);

        std::cout
            << "[RAMULATOR2-WRAPPER-PROBE][DONE]"
            << " write_cycles=" << write_cycles
            << " read_cycles=" << read_cycles
            << " final_cycle=" << memory.currentCycle()
            << '\n';

        memory.printStats(std::cout);
        memory.finalize();

        std::cout
            << "[RAMULATOR2-WRAPPER-PROBE][PASS]\n";

        return 0;
    } catch (const std::exception& ex) {
        std::cerr
            << "[RAMULATOR2-WRAPPER-PROBE][ERROR] "
            << ex.what() << '\n';
        return 1;
    }
}
