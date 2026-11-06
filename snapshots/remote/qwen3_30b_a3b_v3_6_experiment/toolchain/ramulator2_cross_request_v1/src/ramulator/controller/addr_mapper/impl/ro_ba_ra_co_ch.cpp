#include "ramulator/controller/addr_mapper/i_addr_mapper.h"
#include "ramulator/controller/addr_mapper/addr_mapper_base.h"
#include <cstdlib>
#include <stdexcept>
#include <string>

namespace Ramulator {

static uint64_t bank_mix64(uint64_t x) {
  x += 0x9e3779b97f4a7c15ULL;
  x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
  x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}

// Row-Bank-Rank-Column-Channel (MSB to LSB in original scheme)
class RoBaRaCoCh : public IAddrMapper, public AddrMapperBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(IAddrMapper, RoBaRaCoCh, AddrMapperBase, "RoBaRaCoCh")
  void init() override;
  void apply(Request& req) override;
};

void RoBaRaCoCh::init() {
  AddrMapperBase::init();
}

void RoBaRaCoCh::apply(Request& req) {
  req.addr_vec.resize(m_num_mapped_levels + 1, -1);
  Addr_t addr = req.intra_channel_addr >> m_tx_offset;
  // Column at LSB
  req.addr_vec[m_col_idx + 1] = slice_lower_bits(addr, m_addr_bits[m_col_idx]);
  // Rank through Row (levels 0 to row_idx in m_addr_bits order)
  for (int i = 0; i <= m_row_idx; i++) {
    req.addr_vec[i + 1] = slice_lower_bits(addr, m_addr_bits[i]);
  }

  // Controlled address-mapping stress.  This is deliberately applied after
  // the frontend has accepted the original physical address, so read/write
  // forwarding and request identity remain unchanged.  Only the decoded
  // BankGroup/Bank fields are replaced; Row and Column stay bit-identical.
  const char* mode_env = std::getenv("HB_BANK_ADDRESS_MODE");
  const std::string mode = mode_env ? mode_env : "native";
  if (mode == "native") return;
  const char* banks_env = std::getenv("HB_EFFECTIVE_BANKS");
  const int effective_banks = banks_env ? std::stoi(banks_env) : 16;
  if (effective_banks != 2 && effective_banks != 4 &&
      effective_banks != 8 && effective_banks != 16) {
    throw std::runtime_error("HB_EFFECTIVE_BANKS must be 2,4,8,16");
  }
  if (req.addr_vec.size() != 6) {
    throw std::runtime_error("Bank-alias stress requires LPDDR5 six-level address vector");
  }
  const int original_bank = req.addr_vec[2] * 4 + req.addr_vec[3];
  int mapped_bank = original_bank;
  if (mode == "alias") {
    mapped_bank = original_bank % effective_banks;
  } else if (mode == "soft_hot" || mode == "soft_hot_xor") {
    const char* pct_env = std::getenv("HB_SOFT_HOT_PERCENT");
    const int hot_pct = pct_env ? std::stoi(pct_env) : 70;
    int b0, b4, b12, b14, cold;
    if (hot_pct == 50) { b0=5000; b4=1000; b12=1000; b14=1000; cold=2000; }
    else if (hot_pct == 70) { b0=7000; b4=700; b12=700; b14=500; cold=1100; }
    else if (hot_pct == 85) { b0=8500; b4=300; b12=300; b14=300; cold=600; }
    else throw std::runtime_error("HB_SOFT_HOT_PERCENT must be 50,70,85");
    const uint64_t h = bank_mix64(uint64_t(req.intra_channel_addr));
    const int slot = int(h % 10000ULL);
    if (slot < b0) mapped_bank = 0;
    else if (slot < b0+b4) mapped_bank = 4;
    else if (slot < b0+b4+b12) mapped_bank = 12;
    else if (slot < b0+b4+b12+b14) mapped_bank = 14;
    else {
      static const int cold_banks[12] = {1,2,3,5,6,7,8,9,10,11,13,15};
      mapped_bank = cold_banks[bank_mix64(h ^ 0xd1b54a32d192ed03ULL) % 12ULL];
    }
    if (mode == "soft_hot_xor") {
      // Apply the previously validated static Bank XOR after constructing the
      // soft70 pressure mapping. RowLow is taken from byte-address bits 21:18,
      // matching Bank[17:14] XOR RowLow[21:18].
      const int row_low = int((uint64_t(req.intra_channel_addr) >> 18) & 0xfULL);
      mapped_bank ^= row_low;
    }
    (void)cold;
  } else if (mode == "balanced") {
    const uint64_t owner = req.source_id >= 0 ? uint64_t(req.source_id) : 0ULL;
    mapped_bank = int(bank_mix64(uint64_t(req.intra_channel_addr) ^ (owner << 48)) % 16ULL);
  } else {
    throw std::runtime_error("HB_BANK_ADDRESS_MODE must be native, alias, soft_hot, soft_hot_xor, or balanced");
  }
  req.addr_vec[2] = mapped_bank / 4;
  req.addr_vec[3] = mapped_bank % 4;
}

}  // namespace Ramulator
