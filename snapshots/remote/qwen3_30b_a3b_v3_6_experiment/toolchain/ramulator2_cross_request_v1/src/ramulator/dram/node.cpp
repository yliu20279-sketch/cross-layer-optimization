#include "ramulator/dram/node.h"
#include <stdexcept>
#include <string>

namespace Ramulator {

DRAMNode::DRAMNode(DRAMSpec* spec, DRAMNode* parent, int level, int id)
    : m_spec(spec), m_parent_node(parent), m_level(level), m_node_id(id) {
  int num_cmds = spec->command_count;
  m_cmd_ready_clk.resize(num_cmds, -1);
  m_cmd_ready_owner.resize(num_cmds, -1);
  m_cmd_history.resize(num_cmds);
  for (int cmd = 0; cmd < num_cmds; cmd++) {
    int window = 0;
    for (const auto& t : spec->timing_cons[level][cmd]) {
      window = std::max(window, t.window);
    }
    if (window != 0) {
      m_cmd_history[cmd].resize(window, -1);
    } else {
      m_cmd_history[cmd].clear();
    }
  }

  m_state = spec->init_states[m_level];

  // Recursively construct next levels
  int next_level = level + 1;
  int last_level = spec->get_level_id("Row");
  if (next_level == last_level) {
    return;
  } else {
    int next_level_size = m_spec->organization.level_sizes[next_level];
    if (next_level_size == 0) {
      return;
    } else {
      for (int i = 0; i < next_level_size; i++) {
        m_child_nodes.push_back(std::make_unique<DRAMNode>(spec, this, next_level, i));
      }
    }
  }
}

void DRAMNode::update_timing(int command, const AddrVec_t& addr_vec, Clk_t clk, int owner) {
  /************************************************
   *         Update Sibling Node Timing
   ***********************************************/
  if (m_node_id != addr_vec[m_level] && addr_vec[m_level] != -1) {
    for (const auto& t : m_spec->timing_cons[m_level][command]) {
      if (!t.sibling) {
        continue;
      }
      Clk_t future = clk + t.val;
      if (future > m_cmd_ready_clk[t.cmd] ||
          (future == m_cmd_ready_clk[t.cmd] && owner >= 0)) {
        m_cmd_ready_clk[t.cmd] = future;
        m_cmd_ready_owner[t.cmd] = owner;
      }
    }
    return;
  }

  /************************************************
   *          Update Target Node Timing
   ***********************************************/
  if (m_cmd_history[command].size()) {
    m_cmd_history[command].pop_back();
    m_cmd_history[command].push_front(clk);
  }

  for (const auto& t : m_spec->timing_cons[m_level][command]) {
    if (t.sibling) {
      continue;
    }
    Clk_t past = m_cmd_history[command][t.window - 1];
    if (past < 0) {
      continue;
    }
    Clk_t future = past + t.val;
    if (future > m_cmd_ready_clk[t.cmd] ||
        (future == m_cmd_ready_clk[t.cmd] && owner >= 0)) {
      m_cmd_ready_clk[t.cmd] = future;
      m_cmd_ready_owner[t.cmd] = owner;
    }
  }

  if (m_child_nodes.empty()) {
    return;
  }

  // Skip traversal that does not have sibling timing constraints
  int child_level = m_level + 1;
  int target_child_id = addr_vec[child_level];
  bool children_have_sibling_cons = m_spec->has_sibling_cons[child_level][command];

  if (children_have_sibling_cons || target_child_id == -1) {
    for (auto& child : m_child_nodes) {
      child->update_timing(command, addr_vec, clk, owner);
    }
  } else {
    m_child_nodes[target_child_id]->update_timing(command, addr_vec, clk, owner);
  }
}

bool DRAMNode::first_timing_block(int command, const AddrVec_t& addr_vec,
                                 Clk_t clk, int& level, int& owner,
                                 Clk_t& ready_clk) {
  if (command < 0 || command >= static_cast<int>(m_cmd_ready_clk.size()))
    throw std::runtime_error("first_timing_block: command out of range");
  if (m_cmd_ready_clk[command] != -1 && clk < m_cmd_ready_clk[command]) {
    level = m_level;
    owner = m_cmd_ready_owner[command];
    ready_clk = m_cmd_ready_clk[command];
    return true;
  }
  if (m_child_nodes.empty()) return false;
  if (m_level + 1 >= static_cast<int>(addr_vec.size()))
    throw std::runtime_error("first_timing_block: address vector too short");
  int child_id = addr_vec[m_level + 1];
  if (child_id == -1) {
    for (auto& child : m_child_nodes) {
      if (child->first_timing_block(command, addr_vec, clk, level, owner, ready_clk))
        return true;
    }
    return false;
  }
  if (child_id < 0 || child_id >= static_cast<int>(m_child_nodes.size()))
    throw std::runtime_error("first_timing_block: child id out of range at level " +
                             std::to_string(m_level) + " child " + std::to_string(child_id));
  return m_child_nodes[child_id]->first_timing_block(
      command, addr_vec, clk, level, owner, ready_clk);
}

bool DRAMNode::check_timing(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  if (m_cmd_ready_clk[command] != -1 && clk < m_cmd_ready_clk[command]) {
    return false;
  }

  int child_id = addr_vec[m_level + 1];
  if (m_child_nodes.empty()) {
    return true;
  }

  if (child_id == -1) {
    bool timing_ok = true;
    for (auto& child : m_child_nodes) {
      timing_ok = timing_ok && child->check_timing(command, addr_vec, clk);
    }
    return timing_ok;
  } else {
    return m_child_nodes[child_id]->check_timing(command, addr_vec, clk);
  }
}

bool DRAMNode::check_timing_for_owner(int command, const AddrVec_t& addr_vec,
                                      Clk_t clk, int owner, int bank_level) {
  if (m_cmd_ready_clk[command] != -1 && clk < m_cmd_ready_clk[command]) {
    bool removable = m_level == bank_level && owner >= 0 &&
                     m_cmd_ready_owner[command] >= 0 &&
                     owner != m_cmd_ready_owner[command];
    if (!removable) return false;
  }
  if (m_child_nodes.empty()) return true;
  int child_id = addr_vec[m_level + 1];
  if (child_id == -1) {
    for (auto& child : m_child_nodes)
      if (!child->check_timing_for_owner(command, addr_vec, clk, owner, bank_level))
        return false;
    return true;
  }
  return m_child_nodes[child_id]->check_timing_for_owner(
      command, addr_vec, clk, owner, bank_level);
}

}  // namespace Ramulator
