// #include <iostream>

// extern const std::string DRAM_FILE;
// extern const size_t DRAM_SIZE;

// void initializeDRAM();

// void writeDataToDRAM(size_t offset, const int* data, size_t count);
// void readDataFromDRAM(size_t offset, int* buffer, size_t count);
#ifndef FUNC_DRAM_HH
#define FUNC_DRAM_HH

#include <cstddef>
#include <cstdint>
#include <string>
#include <cstring>
#include <stdexcept>
#include <vector>

class funcDRAM {
public:
    funcDRAM(size_t size_bytes, const std::string& filename = "");

    funcDRAM(const funcDRAM&) = delete;
    funcDRAM& operator=(const funcDRAM&) = delete;

    template <typename T>
    void write(size_t addr, const T& data);
    template <typename T>
    T read(size_t addr) const;

    void save_to_file();
    void load_from_file();

    size_t size() const;

private:
    std::vector<uint8_t> storage_;
    std::string filename_;

    void check_address(size_t addr, size_t data_size) const;
};

template <typename T>
void funcDRAM::write(size_t addr, const T& data) {
    check_address(addr, sizeof(T));
    memcpy(&storage_[addr], &data, sizeof(T));
}

template <typename T>
T funcDRAM::read(size_t addr) const {
    check_address(addr, sizeof(T));
    T data;
    memcpy(&data, &storage_[addr], sizeof(T));
    return data;
}

#endif // FUNC_DRAM_HH