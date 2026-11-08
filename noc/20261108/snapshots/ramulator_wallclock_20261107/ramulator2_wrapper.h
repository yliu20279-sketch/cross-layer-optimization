#pragma once

#include <cstdint>
#include <iosfwd>
#include <string>

namespace memory {

struct WallClockService {
    std::uint64_t idle_ticks=0;
    std::uint64_t start_tick=0;
    std::uint64_t end_tick=0;
    std::uint64_t global_done_cycle=0;
};

class Ramulator2Wrapper {
public:
    explicit Ramulator2Wrapper(const std::string& config_path);
    ~Ramulator2Wrapper();

    Ramulator2Wrapper(const Ramulator2Wrapper&) = delete;
    Ramulator2Wrapper& operator=(const Ramulator2Wrapper&) = delete;

    std::uint64_t run(
        bool is_write,
        std::uint64_t address,
        std::uint64_t bytes);

    int transactionBytes() const;
    void advanceTo(std::uint64_t target_tick);
    WallClockService runAtGlobal(bool is_write,std::uint64_t address,std::uint64_t bytes,
                                std::uint64_t global_arrival_cycle,double cycle_scale);
    double clockPeriodNs() const;
    std::uint64_t currentCycle() const;

    void printStats(std::ostream& output);
    void finalize();

private:
    struct Impl;
    Impl* impl_;
};

}  // namespace memory
