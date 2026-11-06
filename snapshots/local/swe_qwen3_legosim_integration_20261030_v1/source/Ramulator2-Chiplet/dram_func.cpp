#include "dram_func.h"
#include <fstream>
#include <stdexcept>
#include <cstring>

funcDRAM::funcDRAM(size_t size_bytes, const std::string& filename)
    : storage_(size_bytes, 0), filename_(filename) {
    if (!filename.empty()) {
        load_from_file();
    }
}

void funcDRAM::save_to_file() {
    if (filename_.empty()) return;

    std::ofstream file(filename_, std::ios::binary);
    if (!file) {
        throw std::runtime_error("[DRAMERR] Failed to open file for writing");
    }

    file.write(reinterpret_cast<const char*>(storage_.data()), storage_.size());
    if (!file) {
        throw std::runtime_error("[DRAMERR] Failed to write data to file");
    }
}

void funcDRAM::load_from_file() {
    if (filename_.empty()) return;

    std::ifstream file(filename_, std::ios::binary | std::ios::ate);
    if (!file) return;

    const size_t file_size = file.tellg();
    file.seekg(0);

    if (file_size != storage_.size()) {
        throw std::runtime_error("[DRAMERR] File size does not match DRAM size");
    }

    file.read(reinterpret_cast<char*>(storage_.data()), storage_.size());
    if (!file) {
        throw std::runtime_error("[DRAMERR] Failed to read data from file");
    }
}

size_t funcDRAM::size() const {
    return storage_.size();
}

void funcDRAM::check_address(size_t addr, size_t data_size) const {
    if (addr + data_size > storage_.size()) {
        throw std::out_of_range("[DRAMERR] DRAM address out of range");
    }
}