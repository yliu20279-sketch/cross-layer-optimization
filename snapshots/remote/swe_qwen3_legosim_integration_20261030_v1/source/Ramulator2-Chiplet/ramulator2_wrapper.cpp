#include "ramulator2_wrapper.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <ostream>
#include <stdexcept>
#include <string>

#include <ramulator/base/config.h>
#include <ramulator/base/factory.h>
#include <ramulator/base/request.h>
#include <ramulator/frontend/i_frontend.h>
#include <ramulator/memory_system/i_memory_system.h>

namespace memory {

struct Ramulator2Wrapper::Impl {
    Ramulator::ConfigNode config;
    Ramulator::IFrontEnd* frontend = nullptr;
    Ramulator::IMemorySystem* memory_system = nullptr;

    std::uint64_t cycle = 0;
    int transaction_bytes = 0;
    double clock_period_ns = 0.0;
    bool finalized = false;

    explicit Impl(const std::string& config_path)
        : config(Ramulator::Config::parse_config_file(config_path)) {
        frontend = Ramulator::Factory::create_frontend(config);
        memory_system =
            Ramulator::Factory::create_memory_system(config);

        if (frontend == nullptr || memory_system == nullptr) {
            throw std::runtime_error(
                "Ramulator2 component creation failed");
        }

        frontend->connect_memory_system(memory_system);
        memory_system->connect_frontend(frontend);

        transaction_bytes = memory_system->get_tx_bytes();
        clock_period_ns =
            static_cast<double>(memory_system->get_tCK());

        if (transaction_bytes <= 0) {
            throw std::runtime_error(
                "Ramulator2 returned invalid transaction size");
        }

        if (clock_period_ns <= 0.0) {
            throw std::runtime_error(
                "Ramulator2 returned invalid tCK");
        }
    }
};

Ramulator2Wrapper::Ramulator2Wrapper(
    const std::string& config_path)
    : impl_(new Impl(config_path)) {}

Ramulator2Wrapper::~Ramulator2Wrapper() {
    try {
        finalize();
    } catch (...) {
    }

    delete impl_;
}

std::uint64_t Ramulator2Wrapper::run(
    bool is_write,
    std::uint64_t address,
    std::uint64_t bytes) {
    if (impl_->finalized) {
        throw std::runtime_error(
            "Ramulator2 request submitted after finalize");
    }

    if (bytes == 0) {
        return 0;
    }

    if (address >
        std::numeric_limits<std::uint64_t>::max() - bytes) {
        throw std::runtime_error(
            "Ramulator2 request address overflow");
    }

    const std::uint64_t begin_cycle = impl_->cycle;
    const std::uint64_t end_address = address + bytes;
    std::uint64_t next_address = address;

    std::uint64_t submitted = 0;
    std::uint64_t completed = 0;

    const int request_type =
        is_write
            ? Ramulator::Request::Type::Write
            : Ramulator::Request::Type::Read;

    while (next_address < end_address ||
           completed < submitted) {
        while (next_address < end_address) {
            const std::uint64_t offset =
                next_address %
                static_cast<std::uint64_t>(
                    impl_->transaction_bytes);

            const std::uint64_t bytes_to_boundary =
                static_cast<std::uint64_t>(
                    impl_->transaction_bytes) -
                offset;

            const std::uint64_t chunk_bytes =
                std::min(
                    end_address - next_address,
                    bytes_to_boundary);

            const bool accepted =
                impl_->frontend->receive_external_requests(
                    request_type,
                    static_cast<Ramulator::Addr_t>(
                        next_address),
                    0,
                    [&](Ramulator::Request&) {
                        ++completed;
                    },
                    static_cast<int>(chunk_bytes));

            if (!accepted) {
                break;
            }

            ++submitted;
            next_address += chunk_bytes;
        }

        if (next_address >= end_address &&
            completed >= submitted) {
            break;
        }

        impl_->memory_system->tick();
        ++impl_->cycle;

        if (impl_->cycle - begin_cycle >
            10000000000ULL) {
            throw std::runtime_error(
                "Ramulator2 request completion timeout");
        }
    }

    return impl_->cycle - begin_cycle;
}

int Ramulator2Wrapper::transactionBytes() const {
    return impl_->transaction_bytes;
}

double Ramulator2Wrapper::clockPeriodNs() const {
    return impl_->clock_period_ns;
}

std::uint64_t Ramulator2Wrapper::currentCycle() const {
    return impl_->cycle;
}

void Ramulator2Wrapper::printStats(std::ostream& output) {
    impl_->memory_system->update_stats_recursive();
    impl_->memory_system->print_stats(output);
}

void Ramulator2Wrapper::finalize() {
    if (impl_ == nullptr || impl_->finalized) {
        return;
    }

    impl_->frontend->finalize();
    impl_->memory_system->finalize();
    impl_->finalized = true;
}

}  // namespace memory
