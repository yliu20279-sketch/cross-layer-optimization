#pragma once

#include <cstdint>
#include <iosfwd>
#include <string>

namespace memory {

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
    double clockPeriodNs() const;
    std::uint64_t currentCycle() const;

    void printStats(std::ostream& output);
    void finalize();

private:
    struct Impl;
    Impl* impl_;
};

}  // namespace memory
