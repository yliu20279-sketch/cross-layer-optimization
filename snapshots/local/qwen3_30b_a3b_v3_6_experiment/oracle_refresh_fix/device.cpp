#include "ramulator/dram/device.h"

namespace Ramulator {

void DRAMDevice::init(std::unique_ptr<DRAMSpec> spec) {
  m_spec_owner = std::move(spec);
  m_spec = m_spec_owner.get();
  m_bank_level = m_spec->get_level_id("Bank");
  m_root = std::make_unique<DRAMNode>(m_spec, nullptr, 0, 0);
  m_root->for_each_at_level(m_bank_level, [&](DRAMNode* bank) { m_bank_nodes.push_back(bank); });
}

void DRAMDevice::set_channel_id(int channel_id) {
  m_root->m_node_id = channel_id;
}

void DRAMDevice::issue_command(int command, const AddrVec_t& addr_vec, Clk_t clk, int owner,
                               bool isolate_owner_bank) {
  m_root->update_timing(command, addr_vec, clk, owner);
  apply_action(command, addr_vec, clk, owner, isolate_owner_bank);
}

bool DRAMDevice::first_timing_block(int command, const AddrVec_t& addr_vec,
                                    Clk_t clk, int& level, int& owner,
                                    Clk_t& ready_clk) {
  return m_root->first_timing_block(command, addr_vec, clk, level, owner, ready_clk);
}

bool DRAMDevice::check_timing(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  return m_root->check_timing(command, addr_vec, clk);
}

bool DRAMDevice::check_timing_for_owner(int command, const AddrVec_t& addr_vec,
                                        Clk_t clk, int owner) {
  return m_root->check_timing_for_owner(command, addr_vec, clk, owner, m_bank_level);
}

int DRAMDevice::get_preq_command(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  auto preq_fn = m_spec->funcs.preqs[command];
  if (!preq_fn) return command;

  int resolved = command;
  for_each_target_bank_while(command, addr_vec, [&](int flat_bank_id) {
    int preq = preq_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
    if (preq != command) { resolved = preq; return false; }
    return true;
  });
  return resolved;
}

DRAMNode* DRAMDevice::owner_bank(int owner, int flat_bank_id) {
  auto& banks = m_owner_bank_nodes[owner];
  if (banks.empty()) banks.resize(m_bank_nodes.size());
  if (!banks[flat_bank_id]) {
    banks[flat_bank_id] = std::make_unique<DRAMNode>(
        m_spec, nullptr, m_bank_level, m_bank_nodes[flat_bank_id]->m_node_id);
  }
  return banks[flat_bank_id].get();
}

int DRAMDevice::get_preq_command_for_owner(int command, const AddrVec_t& addr_vec,
                                           Clk_t clk, int owner) {
  if (owner < 0) return get_preq_command(command, addr_vec, clk);
  auto preq_fn = m_spec->funcs.preqs[command];
  if (!preq_fn) return command;
  int resolved = command;
  for_each_target_bank_while(command, addr_vec, [&](int flat_bank_id) {
    int preq = preq_fn(owner_bank(owner, flat_bank_id), command, addr_vec, clk);
    if (preq != command) { resolved = preq; return false; }
    return true;
  });
  return resolved;
}

bool DRAMDevice::check_rowbuffer_hit(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  auto rowhit_fn = m_spec->funcs.rowhits[command];
  if (!rowhit_fn) {
    return false;
  }
  int flat_bank_id = get_flat_bank_id(addr_vec);
  return rowhit_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
}

bool DRAMDevice::check_rowbuffer_hit_for_owner(
    int command, const AddrVec_t& addr_vec, Clk_t clk, int owner) {
  if (owner < 0) return check_rowbuffer_hit(command, addr_vec, clk);
  auto rowhit_fn = m_spec->funcs.rowhits[command];
  if (!rowhit_fn) return false;
  const int flat_bank_id = get_flat_bank_id(addr_vec);
  return rowhit_fn(owner_bank(owner, flat_bank_id), command, addr_vec, clk);
}

bool DRAMDevice::check_node_open(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  auto rowopen_fn = m_spec->funcs.rowopens[command];
  if (!rowopen_fn) {
    return false;
  }
  int flat_bank_id = get_flat_bank_id(addr_vec);
  return rowopen_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
}

bool DRAMDevice::check_node_open_for_owner(
    int command, const AddrVec_t& addr_vec, Clk_t clk, int owner) {
  if (owner < 0) return check_node_open(command, addr_vec, clk);
  auto rowopen_fn = m_spec->funcs.rowopens[command];
  if (!rowopen_fn) return false;
  const int flat_bank_id = get_flat_bank_id(addr_vec);
  return rowopen_fn(owner_bank(owner, flat_bank_id), command, addr_vec, clk);
}

int DRAMDevice::get_flat_bank_id(const AddrVec_t& addr_vec) const {
  int id = 0;
  for (int lvl = 1; lvl <= m_bank_level; lvl++) {
    id = id * m_spec->organization.level_sizes[lvl] + addr_vec[lvl];
  }
  return id;
}

bool DRAMDevice::bank_matches(DRAMNode* bank, const AddrVec_t& addr_vec) {
  for (auto* n = bank; n != nullptr; n = n->m_parent_node) {
    if (addr_vec[n->m_level] != -1 && addr_vec[n->m_level] != n->m_node_id) {
      return false;
    }
  }
  return true;
}

std::vector<int> DRAMDevice::get_target_banks(int command, const AddrVec_t& addr_vec) const {
  std::vector<int> ids;
  for_each_target_bank(command, addr_vec, [&](int id) { ids.push_back(id); });
  return ids;
}

void DRAMDevice::apply_action(int command, const AddrVec_t& addr_vec, Clk_t clk,
                              int owner, bool isolate_owner_bank) {
  auto action_fn = m_spec->funcs.actions[command];
  if (!action_fn) return;
  for_each_target_bank(command, addr_vec, [&](int flat_bank_id) {
    if (isolate_owner_bank && owner >= 0) {
      action_fn(owner_bank(owner, flat_bank_id), command, addr_vec, clk);
      return;
    }

    // Controller-owned commands (for example refresh) have owner < 0.  They
    // change physical Bank state for every request, so an owner-isolated
    // oracle must mirror the same action into every materialized owner Bank.
    // Without this propagation, normal and oracle diverge even for c1 where
    // cross-request contention is impossible.
    action_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
    if (isolate_owner_bank && owner < 0) {
      for (auto& entry : m_owner_bank_nodes) {
        auto& banks = entry.second;
        if (flat_bank_id < static_cast<int>(banks.size()) && banks[flat_bank_id]) {
          action_fn(banks[flat_bank_id].get(), command, addr_vec, clk);
        }
      }
    }
  });
}

}  // namespace Ramulator
