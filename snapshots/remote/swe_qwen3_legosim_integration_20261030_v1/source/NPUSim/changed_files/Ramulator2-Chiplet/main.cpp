#include "dram_chiplet_protocol.h"
#include "dram_func.h"
#include "ramulator2_wrapper.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "pipe_comm.h"
#include "sync_protocol.h"

namespace {

unsigned long long scaleCycles(unsigned long long cycles, double scale) {
    if (cycles == 0) {
        return 0;
    }
    return std::max<unsigned long long>(1, static_cast<unsigned long long>(
                                                std::ceil(static_cast<double>(cycles) * scale)));
}

void checkIoSize(int expected, int actual, const char* what) {
    if (actual != expected) {
        throw std::runtime_error(std::string("short DRAM chiplet ") + what);
    }
}

std::string receivePipe(int src_x, int src_y, int dram_x, int dram_y) {
    return InterChiplet::receiveSync(src_x, src_y, dram_x, dram_y);
}

std::string sendPipe(int dram_x, int dram_y, int dst_x, int dst_y) {
    return InterChiplet::sendSync(dram_x, dram_y, dst_x, dst_y);
}

long syncDescriptorForRequest(std::uint64_t request_id) {
    return DramChiplet::isNpuRequestId(request_id)
               ? static_cast<long>(request_id)
               : 0L;
}

}  // namespace

// Dynamic DRAM server protocol:
//   client request -> optional store payload -> reply/payload
// The original DRAMSim2 chiplet flow uses an explicit fixed client in the
// benchmark entry, so Ramulator2 follows the same shape by default.  A
// waitlaunch-based fallback remains available when no fixed client is passed.
int main(int argc, char* argv[]) {
    try {
        if (argc < 8 ||
            std::string(argv[4]) != "--server") {
            std::cerr
                << "usage: ramulator2 "
                << "<x> <y> <cycle_scale> --server "
                << "<config_yaml> <size_bytes> <clients> "
                << "[--fixed-client <src_x> <src_y>] [timing_trace.csv]\n";
            return 1;
        }

        const int dram_x = std::atoi(argv[1]);
        const int dram_y = std::atoi(argv[2]);
        const double cycle_scale = std::stod(argv[3]);
        const std::string config_path = argv[5];
        const std::uint64_t dram_size =
            std::stoull(argv[6]);
        const int expected_clients =
            std::max(1, std::atoi(argv[7]));

        bool has_fixed_client = false;
        int fixed_client_x = -1;
        int fixed_client_y = -1;
        std::string timing_trace_path;

        for (int i = 8; i < argc; ) {
            const std::string arg = argv[i];
            if (arg == "--fixed-client") {
                if (i + 2 >= argc) {
                    throw std::runtime_error("--fixed-client requires two coordinates");
                }
                has_fixed_client = true;
                fixed_client_x = std::stoi(argv[i + 1]);
                fixed_client_y = std::stoi(argv[i + 2]);
                i += 3;
                continue;
            }

            if (!timing_trace_path.empty()) {
                throw std::runtime_error("multiple timing trace paths provided");
            }
            timing_trace_path = arg;
            ++i;
        }

        if (dram_size == 0) {
            throw std::runtime_error("DRAM size must be positive");
        }
        if (cycle_scale <= 0.0) {
            throw std::runtime_error("DRAM cycle scale must be positive");
        }

        InterChiplet::PipeComm pipe_comm;
        memory::Ramulator2Wrapper timing(config_path);
        // Functional memory is deliberately fresh per run.  Inputs are
        // materialised by the NPU client, avoiding stale dram_data.bin state.
        funcDRAM dram(static_cast<std::size_t>(dram_size));

        std::ofstream timing_trace;
        if (!timing_trace_path.empty() && timing_trace_path != "-") {
            const std::filesystem::path trace_path(timing_trace_path);
            if (!trace_path.parent_path().empty()) {
                std::filesystem::create_directories(trace_path.parent_path());
            }
            timing_trace.open(timing_trace_path, std::ios::out | std::ios::trunc);
            if (!timing_trace.is_open()) {
                throw std::runtime_error("cannot open DRAM timing trace: " + timing_trace_path);
            }
            timing_trace << "request_id,operation,bytes,arrival_cycle,service_start_cycle,"
                            "service_cycles,service_done_cycle,response_issue_cycle\n";
        }

        std::uint64_t present_cycle = 0;
        int shutdown_count = 0;
        std::cout
            << "[DRAM-CHIPLET][BOOT] coord=("
            << dram_x << "," << dram_y
            << ") backend=Ramulator2-LPDDR5"
            << " size=" << dram_size
            << " clients=" << expected_clients
            << " tx_bytes=" << timing.transactionBytes()
            << " tCK_ns=" << timing.clockPeriodNs()
            << (has_fixed_client ? std::string(" fixed_client=(") +
                                       std::to_string(fixed_client_x) + "," +
                                       std::to_string(fixed_client_y) + ")"
                                 : std::string())
            << '\n';

        while (shutdown_count < expected_clients) {
            int src_x = -1;
            int src_y = -1;
            if (has_fixed_client) {
                src_x = fixed_client_x;
                src_y = fixed_client_y;
            } else {
                InterChiplet::waitlaunchSync(&src_x, &src_y, dram_x, dram_y);
            }

            const std::string command_pipe = receivePipe(src_x, src_y, dram_x, dram_y);
            DramChiplet::Request request{};
            checkIoSize(static_cast<int>(sizeof(request)),
                        pipe_comm.read_data(command_pipe.c_str(), &request, sizeof(request)),
                        "request read");
            const long sync_desc = syncDescriptorForRequest(request.request_id);
            present_cycle = InterChiplet::readSync(present_cycle,
                                                   src_x,
                                                   src_y,
                                                   dram_x,
                                                   dram_y,
                                                   sizeof(request),
                                                   sync_desc);

            const auto op = static_cast<DramChiplet::Operation>(request.operation);
            if (op == DramChiplet::Operation::kShutdown) {
                ++shutdown_count;
                std::cout << "[DRAM-CHIPLET][SHUTDOWN] client=(" << src_x << "," << src_y
                          << ") " << shutdown_count << "/" << expected_clients << '\n';
                continue;
            }
            if (op != DramChiplet::Operation::kStore && op != DramChiplet::Operation::kLoad) {
                throw std::runtime_error("unsupported DRAM request operation");
            }
            if (request.bytes == 0 || request.address > dram_size ||
                request.bytes > dram_size - request.address) {
                throw std::runtime_error("DRAM request is out of range");
            }
            if (request.bytes > static_cast<std::uint64_t>(std::numeric_limits<int>::max())) {
                throw std::runtime_error("DRAM request is too large for InterChiplet transport");
            }

            std::vector<std::uint8_t> payload(static_cast<std::size_t>(request.bytes));
            if (op == DramChiplet::Operation::kStore) {
                const std::string data_pipe = receivePipe(src_x, src_y, dram_x, dram_y);
                checkIoSize(static_cast<int>(request.bytes),
                            pipe_comm.read_data(data_pipe.c_str(), payload.data(), payload.size()),
                            "store payload read");
                present_cycle = InterChiplet::readSync(present_cycle,
                                                       src_x,
                                                       src_y,
                                                       dram_x,
                                                       dram_y,
                                                       static_cast<int>(request.bytes),
                                                       sync_desc);
                for (std::size_t i = 0; i < payload.size(); ++i) {
                    dram.write<std::uint8_t>(static_cast<std::size_t>(request.address) + i,
                                             payload[i]);
                }
            }

            const std::uint64_t service_start = present_cycle;
            const std::uint64_t service = scaleCycles(
                timing.run(
                    op == DramChiplet::Operation::kStore,
                    request.address,
                    request.bytes),
                cycle_scale);
            present_cycle += service;
            const std::uint64_t service_done = present_cycle;

            if (op == DramChiplet::Operation::kLoad) {
                for (std::size_t i = 0; i < payload.size(); ++i) {
                    payload[i] = dram.read<std::uint8_t>(static_cast<std::size_t>(request.address) + i);
                }
                const std::string data_pipe = sendPipe(dram_x, dram_y, src_x, src_y);
                checkIoSize(static_cast<int>(request.bytes),
                            pipe_comm.write_data(data_pipe.c_str(), payload.data(), payload.size()),
                            "load payload write");
                present_cycle = InterChiplet::writeSync(present_cycle,
                                                        dram_x,
                                                        dram_y,
                                                        src_x,
                                                        src_y,
                                                        static_cast<int>(request.bytes),
                                                        sync_desc);
            } else {
                DramChiplet::Reply reply{request.request_id, 0};
                const std::string reply_pipe = sendPipe(dram_x, dram_y, src_x, src_y);
                checkIoSize(static_cast<int>(sizeof(reply)),
                            pipe_comm.write_data(reply_pipe.c_str(), &reply, sizeof(reply)),
                            "store reply write");
                present_cycle = InterChiplet::writeSync(present_cycle,
                                                        dram_x,
                                                        dram_y,
                                                        src_x,
                                                        src_y,
                                                        sizeof(reply),
                                                        sync_desc);
            }

            if (timing_trace.is_open()) {
                timing_trace << request.request_id << ','
                             << (op == DramChiplet::Operation::kLoad ? "LOAD" : "STORE") << ','
                             << request.bytes << ','
                             << service_start << ','
                             << service_start << ','
                             << service << ','
                             << service_done << ','
                             << present_cycle << '\n';
                timing_trace.flush();
            }

            std::cout << "[DRAM-CHIPLET][DONE] id=" << request.request_id
                      << " op=" << (op == DramChiplet::Operation::kLoad ? "load" : "store")
                      << " bytes=" << request.bytes
                      << " service=" << service
                      << " ready=" << present_cycle << '\n';
        }

        timing.printStats(std::cout);
        timing.finalize();
        std::cout << "[DRAM-CHIPLET][EXIT] cycle=" << present_cycle << '\n';
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "[DRAM-CHIPLET][ERROR] " << ex.what() << '\n';
        return 1;
    }
}
