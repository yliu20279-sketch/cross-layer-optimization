#pragma once

#include <fstream>
#include <cstdint>
#include <map>
#include <unordered_map>
#include <algorithm>
#include <cstdlib>
#include <string>

#include "global_define.h"
#include "hb_transport.h"
#include "spdlog/spdlog.h"

// #define PAC_PAYLOAD_BIT 64
// #define PAC_PAYLOAD_BYTE (PAC_PAYLOAD_BIT / 8)

/**
 * @defgroup net_delay
 * @brief Network latency information interface.
 * @{
 */
/**
 * @brief Structure presents delay of one package in network.
 */
class NetworkDelayItem {
   public:
    /**
     * @brief Package injection cycle. Used to order packages.
     */
    InterChiplet::InnerTimeType m_cycle;
    /**
     * @brief Packate id. (Not used yet.)
     */
    uint64_t m_id;
    /**
     * @brief Source address.
     */
    InterChiplet::AddrType m_src;
    /**
     * @brief Destination address.
     */
    InterChiplet::AddrType m_dst;
    /**
     * @brief Synchronization protocol descriptor.
     */
    long m_desc;
    /**
     * @brief Delay of packages.
     *
     * Each package has two delay values. The first value is the delay from the write side, and the
     * second value is the delay from the read side.
     */
    std::vector<InterChiplet::InnerTimeType> m_delay_list;

   public:
    /**
     * @brief Construct Empty NetworkDelayItem.
     */
    NetworkDelayItem() {}

    /**
     * @brief Construct NetworkDelayItem.
     * @param __cycle Package injection cycle.
     * @param __src Source address.
     * @param __dst Destination address.
     * @param __desc Synchronization protocol descriptor.
     * @param __delay_list List of package delays.
     */
    NetworkDelayItem(InterChiplet::InnerTimeType __cycle, const InterChiplet::AddrType& __src,
                     const InterChiplet::AddrType& __dst, long __desc,
                     const std::vector<InterChiplet::InnerTimeType>& __delay_list)
        : m_cycle(__cycle), m_dst(__dst), m_src(__src), m_delay_list(__delay_list) {}

    /**
     * @brief Overloading operator <<.
     *
     * Write NetworkDelayItem to output stream.
     */
    friend std::ostream& operator<<(std::ostream& os, const NetworkDelayItem& __item) {
        os << __item.m_cycle << " " << DIM_X(__item.m_src) << " " << DIM_Y(__item.m_src) << " "
           << DIM_Y(__item.m_dst) << " " << DIM_X(__item.m_dst) << " " << __item.m_desc << " "
           << __item.m_delay_list.size();
        for (auto& delay : __item.m_delay_list) {
            os << " " << delay;
        }
        return os;
    }

    /**
     * @brief Overloading operator >>.
     *
     * Read NetworkDelayItem from input stream.
     */
    friend std::istream& operator>>(std::istream& os, NetworkDelayItem& __item) {
        os >> __item.m_cycle;
        long src_x, src_y, dst_x, dst_y;
        os >> src_x >> src_y >> dst_x >> dst_y;
        __item.m_src.push_back(src_x);
        __item.m_src.push_back(src_y);
        __item.m_dst.push_back(dst_x);
        __item.m_dst.push_back(dst_y);
        os >> __item.m_desc;
        int delay_cnt = 0;
        os >> delay_cnt;
        for (int i = 0; i < delay_cnt; i++) {
            InterChiplet::TimeType delay;
            os >> delay;
            __item.m_delay_list.push_back(delay);
        }
        return os;
    }
};

class NetworkDelayItem_onDim {
   public:
    InterChiplet::InnerTimeType m_cycle;
    uint64_t m_id;
    long m_src;  // 修改为 long 类型
    long m_dst;  // 修改为 long 类型
    long m_desc;
    std::vector<InterChiplet::InnerTimeType> m_delay_list;

   public:
    NetworkDelayItem_onDim() {}

    NetworkDelayItem_onDim(InterChiplet::InnerTimeType __cycle, long __src, long __dst, long __desc,
                           const std::vector<InterChiplet::InnerTimeType>& __delay_list)
        : m_cycle(__cycle), m_src(__src), m_dst(__dst), m_desc(__desc), m_delay_list(__delay_list) {}

    friend std::ostream& operator<<(std::ostream& os, const NetworkDelayItem_onDim& __item) {
        os << __item.m_cycle << " " << __item.m_src << " " << __item.m_dst << " "
           << __item.m_desc << " " << __item.m_delay_list.size();
        for (auto& delay : __item.m_delay_list) {
            os << " " << delay;
        }
        return os;
    }

    friend std::istream& operator>>(std::istream& os, NetworkDelayItem_onDim& __item) {
        os >> __item.m_cycle;
        os >> __item.m_src >> __item.m_dst;
        os >> __item.m_desc;

        int delay_cnt = 0;
        os >> delay_cnt;
        __item.m_delay_list.clear();
        for (int i = 0; i < delay_cnt; i++) {
            InterChiplet::TimeType delay;
            os >> delay;
            __item.m_delay_list.push_back(delay);
        }

        return os;
    }
};


typedef std::tuple<InterChiplet::InnerTimeType, InterChiplet::InnerTimeType> CmdDelayPair;
#define SRC_DELAY(pair) std::get<0>(pair)
#define DST_DELAY(pair) std::get<1>(pair)
typedef std::multimap<InterChiplet::InnerTimeType, NetworkDelayItem> NetworkDelayOrder;

// NPUSim's DRAM-chiplet protocol reserves 0x4e50 in bits [63:48] of a
// descriptor as a stable request-id tag.  Only these tagged transactions may
// be matched out of cross-chiplet issue order: feedback stalls can reorder
// independently issued NPU requests at the shared DRAM server.  Keep the
// legacy order-based behavior for every other non-zero descriptor.
inline bool isStableNpuRequestIdDescriptor(long descriptor) {
    constexpr std::uint64_t kNpuRequestIdMagic = 0x4E50000000000000ULL;
    constexpr std::uint64_t kNpuRequestIdMagicMask = 0xFFFF000000000000ULL;
    const std::uint64_t value = static_cast<std::uint64_t>(descriptor);
    return (value & kNpuRequestIdMagicMask) == kNpuRequestIdMagic;
}

// Horizontal application flows use a second descriptor namespace. The
// descriptor is derived from (slot, phase, source, destination), so the same
// logical packet can be located in a feedback round even when independent host
// threads reach InterChiplet in a different order.
inline bool isStableNocFlowDescriptor(long descriptor) {
    constexpr std::uint64_t kNocFlowMagic = 0x4E4F000000000000ULL;
    constexpr std::uint64_t kNocFlowMagicMask = 0xFFFF000000000000ULL;
    const std::uint64_t value = static_cast<std::uint64_t>(descriptor);
    return (value & kNocFlowMagicMask) == kNocFlowMagic;
}

inline bool isStablePacketDescriptor(long descriptor) {
    return isStableNpuRequestIdDescriptor(descriptor) ||
           isStableNocFlowDescriptor(descriptor);
}

/**
 * @brief Map for network delay information.
 */
class NetworkDelayMap : public std::map<InterChiplet::AddrType, NetworkDelayOrder> {
   private:
    struct PacketIndexEntry {
        InterChiplet::AddrType m_addr;
        NetworkDelayOrder::iterator m_iterator;
    };

    // Stable descriptors are unique packet identifiers.  Keep an iterator
    // index so feedback replay is O(log N) for insertion and O(1) for lookup,
    // instead of scanning the per-source multimap three times per packet.
    std::unordered_map<long, PacketIndexEntry> m_packet_index;

   public:
    /**
     * @brief Insert delay information.
     * @param __addr Address as key.
     * @param __cycle Event cycle.
     * @param __item Delay information structure.
     */
    void insert(const InterChiplet::AddrType& __addr, InterChiplet::InnerTimeType __cycle,
                const NetworkDelayItem& __item) {
        if (find(__addr) == end()) {
            (*this)[__addr] = NetworkDelayOrder();
        }
        NetworkDelayOrder::iterator inserted = (*this)[__addr].insert(
            std::pair<InterChiplet::InnerTimeType, NetworkDelayItem>(__cycle, __item));
        if (isStablePacketDescriptor(__item.m_desc)) {
            auto index_result = m_packet_index.emplace(
                __item.m_desc, PacketIndexEntry{__addr, inserted});
            if (!index_result.second) {
                spdlog::error("Duplicate stable packet descriptor {} in delayInfo.",
                              __item.m_desc);
            }
        }
    }

    /**
     * @brief Check whether there is delay information for the specified address.
     * @param __addr Address.
     * @return If there is delay information for the specified address, return True.
     */
    bool hasAddr(const InterChiplet::AddrType& __addr) {
        // If there is no address, return false.
        if (find(__addr) == end()) {
            return false;
        }
        // If there is no delay information for the address, return false.
        return at(__addr).size() > 0;
    }

    /**
     * @brief Check whether there is delay information for the specified address.
     * @param __addr Address as key.
     * @param __src Source address.
     * @param __dst Destination address.
     * @return If there is delay information for the specified address, return True.
     */
    bool hasAddr(const InterChiplet::AddrType& __addr, const InterChiplet::AddrType& __src,
                 const InterChiplet::AddrType& __dst) {
        // If there is no address, return false.
        if (find(__addr) == end()) {
            return false;
        }
        // If there is no delay information for the address, return false.
        for (NetworkDelayOrder::iterator it = (*this)[__addr].begin(); it != (*this)[__addr].end();
             it++) {
            if (it->second.m_src == __src && it->second.m_dst == __dst) {
                return true;
            }
        }
        return false;
    }

    /**
     * @brief Check whether a delay item exists for one uniquely described packet.
     *
     * A non-zero descriptor can carry an application request id.  Unlike the
     * legacy descriptor-zero traffic, independently issued request-id packets
     * may legitimately arrive at the interchiplet runtime in a different
     * cross-source order in a later feedback iteration.
     */
    bool hasPacket(const InterChiplet::AddrType& __addr, const InterChiplet::AddrType& __src,
                   const InterChiplet::AddrType& __dst, long __desc) {
        auto indexed = m_packet_index.find(__desc);
        if (indexed == m_packet_index.end()) {
            return false;
        }
        const NetworkDelayItem& item = indexed->second.m_iterator->second;
        return indexed->second.m_addr == __addr && item.m_src == __src &&
               item.m_dst == __dst && item.m_desc == __desc;
    }

    /**
     * @brief Return the first delay information for the specified address.
     * @param __addr Address.
     * @return The first delay information to the specified address.
     */
    NetworkDelayItem front(const InterChiplet::AddrType& __addr) {
        // If there is no destination address, return empty.
        if (find(__addr) == end()) {
            return NetworkDelayItem();
        }
        // If there is no delay information for the address, return false.
        if (at(__addr).size() == 0) {
            return NetworkDelayItem();
        }

        return at(__addr).begin()->second;
    }

    /**
     * @brief Return the first delay information for the specified address.
     * @param __addr Address as key.
     * @param __src Source address.
     * @param __dst Destination address.
     * @return The first delay information to the specified address.
     */
    NetworkDelayItem front(const InterChiplet::AddrType& __addr,
                           const InterChiplet::AddrType& __src,
                           const InterChiplet::AddrType& __dst) {
        // If there is no destination address, return empty.
        if (find(__addr) == end()) {
            return NetworkDelayItem();
        }
        // If there is no delay information for the address, return false.
        for (NetworkDelayOrder::iterator it = (*this)[__addr].begin(); it != (*this)[__addr].end();
             it++) {
            if (it->second.m_src == __src && it->second.m_dst == __dst) {
                return it->second;
            }
        }
        return NetworkDelayItem();
    }

    /**
     * @brief Return the earliest matching item for one unique packet key.
     */
    NetworkDelayItem frontPacket(const InterChiplet::AddrType& __addr,
                                 const InterChiplet::AddrType& __src,
                                 const InterChiplet::AddrType& __dst, long __desc) {
        auto indexed = m_packet_index.find(__desc);
        if (indexed == m_packet_index.end()) {
            return NetworkDelayItem();
        }
        const NetworkDelayItem& item = indexed->second.m_iterator->second;
        if (indexed->second.m_addr == __addr && item.m_src == __src &&
            item.m_dst == __dst && item.m_desc == __desc) {
            return item;
        }
        return NetworkDelayItem();
    }

    /**
     * @brief Pop the first delay information for the specified address.
     * @param __addr Asdress.
     */
    void pop(const InterChiplet::AddrType& __addr) {
        // If there is no destination address, do nothing.
        if (find(__addr) == end()) {
            return;
        }
        // If there is no delay information for the address, do nothing.
        if (at(__addr).size() == 0) {
            return;
        }

        at(__addr).erase(at(__addr).begin());
    }

    /**
     * @brief Pop the first delay information for the specified address.
     * @param __addr Address as key.
     * @param __src Source address.
     * @param __dst Destination address.
     */
    void pop(const InterChiplet::AddrType& __addr, const InterChiplet::AddrType& __src,
             const InterChiplet::AddrType& __dst) {
        // If there is no destination address, do nothing.
        if (find(__addr) == end()) {
            return;
        }
        // If there is no delay information for the address, return false.
        for (NetworkDelayOrder::iterator it = (*this)[__addr].begin(); it != (*this)[__addr].end();
             it++) {
            if (it->second.m_src == __src && it->second.m_dst == __dst) {
                (*this)[__addr].erase(it);
                return;
            }
        }
    }

    /**
     * @brief Remove the earliest matching item for one unique packet key.
     */
    void popPacket(const InterChiplet::AddrType& __addr, const InterChiplet::AddrType& __src,
                   const InterChiplet::AddrType& __dst, long __desc) {
        auto indexed = m_packet_index.find(__desc);
        if (indexed == m_packet_index.end()) {
            return;
        }
        const NetworkDelayItem& item = indexed->second.m_iterator->second;
        if (indexed->second.m_addr == __addr && item.m_src == __src &&
            item.m_dst == __dst && item.m_desc == __desc) {
            auto address = find(indexed->second.m_addr);
            if (address != end()) {
                address->second.erase(indexed->second.m_iterator);
            }
            m_packet_index.erase(indexed);
        }
    }

    /** Clear both the ordered storage and the stable-descriptor index. */
    void clear() {
        std::map<InterChiplet::AddrType, NetworkDelayOrder>::clear();
        m_packet_index.clear();
    }

    /**
     * @brief Check the order of write/read commands.
     * @param __cmd Command to check.
     * @return If the order of command matches the order of delay infomation, return True.
     * Otherwise return False.
     */
    bool checkOrderOfCommand(const InterChiplet::SyncCommand& __cmd) {
        // If the source does not exist, return false.
        if (find(__cmd.m_src) == end()) {
            return true;
        }

        // If the source has no packet, return false.
        if ((*this)[__cmd.m_src].size() == 0) {
            return true;
        }

        // NPU DRAM request-id traffic may be reordered across independent
        // clients by feedback stalls.  All other traffic keeps the legacy
        // order-based behavior, including descriptor-zero transfers.
        if (isStablePacketDescriptor(__cmd.m_desc)) {
            if (hasPacket(__cmd.m_src, __cmd.m_src, __cmd.m_dst, __cmd.m_desc)) {
                return true;
            }
        }

        NetworkDelayItem& delay_item = (*this)[__cmd.m_src].begin()->second;
        // Return true if command matches the first item in delay information list.
        if (delay_item.m_src == __cmd.m_src && delay_item.m_dst == __cmd.m_dst &&
            delay_item.m_desc == __cmd.m_desc) {
            return true;
        } else {
            spdlog::warn("Delay info from {},{} to {},{} with flag {}.", delay_item.m_src[0],
                         delay_item.m_src[1], delay_item.m_dst[0], delay_item.m_dst[1],
                         delay_item.m_desc);
            spdlog::warn("Command    from {},{} to {},{} with flag {}.", __cmd.m_src[0],
                         __cmd.m_src[1], __cmd.m_dst[0], __cmd.m_dst[1], __cmd.m_desc);
            return false;
        }
    }
};

/**
 * @brief List of network delay item.
 */
class NetworkDelayStruct {
   public:
    NetworkDelayStruct() : m_item_count(0) {}

    int size() const { return m_item_count; }

   public:
    /**
     * @brief Load package delay list from specified file.
     * @param __file_name Path to benchmark file.
     * @param __clock_rate Clock ratio (Simulator clock/Interchiplet clock).
     */
    void loadDelayInfo(const std::string& __file_name, double __clock_rate, int __width) {
        std::ifstream bench_if(__file_name, std::ios::in);
        m_item_count = 0;

        while (bench_if) {
            // 读取一维的 item_onDim 数据
            NetworkDelayItem_onDim item_onDim;
            bench_if >> item_onDim;
            if (!bench_if) break;

            // 初始化二维的 item
            NetworkDelayItem item;
            item.m_cycle = item_onDim.m_cycle / __clock_rate;
            item.m_desc = item_onDim.m_desc;
            item.m_delay_list = item_onDim.m_delay_list;

            // 将一维源地址转换为二维 (src_x, src_y)
            int src_x = item_onDim.m_src % __width;
            int src_y = item_onDim.m_src / __width;
            item.m_src = {src_x, src_y};

            // 将一维目标地址转换为二维 (dst_x, dst_y)
            int dst_x = item_onDim.m_dst % __width;
            int dst_y = item_onDim.m_dst / __width;
            item.m_dst = {dst_x, dst_y};

            // 缩放延迟时间
            for (std::size_t i = 0; i < item.m_delay_list.size(); i++) {
                item.m_delay_list[i] = item_onDim.m_delay_list[i] / __clock_rate;
            }

            m_item_count += 1;

            // 插入到 Source map
            m_src_delay_map.insert(item.m_src, item.m_cycle, item);

            // 处理不同的同步协议
            if (item.m_desc & 0xF0000) {
                InterChiplet::InnerTimeType end_cycle = item.m_cycle + item.m_delay_list[1];
                if (item.m_desc & InterChiplet::SPD_BARRIER) {
                    m_barrier_delay_map.insert(item.m_dst, end_cycle, item);
                } else if (item.m_desc & InterChiplet::SPD_LAUNCH) {
                    m_launch_delay_map.insert(item.m_dst, end_cycle, item);
                } else if (item.m_desc & InterChiplet::SPD_LOCK) {
                    m_lock_delay_map.insert(item.m_dst, end_cycle, item);
                } else if (item.m_desc & InterChiplet::SPD_UNLOCK) {
                    m_unlock_delay_map.insert(item.m_dst, end_cycle, item);
                }
            }
        }
    }


    /**
     * @brief Check the order of write/read commands.
     * @param __cmd Command to check.
     * @return If the order of command matches the order of delay infomation, return True.
     * Otherwise return False.
     */
    bool checkOrderOfCommand(const InterChiplet::SyncCommand& __cmd) {
        return m_src_delay_map.checkOrderOfCommand(__cmd);
    }

    /**
     * @brief Clear delay information.
     */
    void clearDelayInfo() {
        // Launch delay list
        m_src_delay_map.clear();
        // Launch order.
        m_launch_delay_map.clear();
        // Barrier order.
        m_barrier_delay_map.clear();
        // Lock order.
        m_lock_delay_map.clear();
        // Unlock order.
        m_unlock_delay_map.clear();
    }

   public:
    /**
     * @brief Check whether there is LAUNCH command in order.
     * @param __dst Destination address.
     * @return If there is LAUNCH command to the specified destination address, return True.
     */
    inline bool hasLaunch(const InterChiplet::AddrType& __dst) {
        return m_launch_delay_map.hasAddr(__dst);
    }

    /**
     * @brief Return the source address of the first LAUNCH command to the specified destination
     * address.
     *
     * @param __dst Destination address.
     * @return The source address of the first LAUNCH command.
     */
    inline InterChiplet::AddrType frontLaunchSrc(const InterChiplet::AddrType& __dst) {
        return m_launch_delay_map.front(__dst).m_src;
    }

    /**
     * @brief Pop the first LAUNCH command to the specified destination address.
     * @param __dst Destination address.
     */
    inline void popLaunch(const InterChiplet::AddrType& __dst) { m_launch_delay_map.pop(__dst); }

    /**
     * @brief Check whether there is LOCK command in order.
     * @param __dst Destination address.
     * @return If there is LOCK command to the specified destination address, return True.
     */
    inline bool hasLock(const InterChiplet::AddrType& __dst) {
        return m_lock_delay_map.hasAddr(__dst);
    }

    /**
     * @brief Return the source address of the first LOCK command to the specified destination
     * address.
     *
     * @param __dst Destination address.
     * @return The source address of the first LOCK command.
     */
    inline InterChiplet::AddrType frontLockSrc(const InterChiplet::AddrType& __dst) {
        return m_lock_delay_map.front(__dst).m_src;
    }

    /**
     * @brief Pop the first LOCK command to the specified destination address.
     * @param __dst Destination address.
     */
    inline void popLock(const InterChiplet::AddrType& __dst) { m_lock_delay_map.pop(__dst); }

   public:
    /**
     * @brief Get end cycle of one communication.
     * @param __write_cmd Write command
     * @param __read_cmd  Read command.
     * @return End cycle of this communication, used to acknowledge SYNC command.
     */
    CmdDelayPair getEndCycle(const InterChiplet::SyncCommand& __write_cmd,
                             const InterChiplet::SyncCommand& __read_cmd) {
        // Vertical memory RPCs never consume horizontal PopNet feedback.
        if (isStableNpuRequestIdDescriptor(__write_cmd.m_desc) &&
            HbTransport::enabled()) {
            return getDefaultEndCycle(__write_cmd, __read_cmd);
        }
        const char* ready_flit=std::getenv("LEGOSIM_RENDEZVOUS_FLIT_BYTES");
        const bool rendezvous=ready_flit&&isStableNocFlowDescriptor(__write_cmd.m_desc)&&!(__write_cmd.m_desc&0xF0000);
        auto causal_bounds=[&](CmdDelayPair prediction){
            if(!rendezvous)return prediction;
            const long bytes=std::stol(ready_flit);
            if(bytes<=0||__write_cmd.m_nbytes<=0)throw std::runtime_error("invalid rendezvous flit/payload size");
            // A real receive-ready notice precedes DATA admission. The source
            // port then reads at most one physical flit per common clock edge.
            // This is a causal lower bound on a NUMERICAL prediction, never a
            // substitute for the measured PopNet completion times.
            const auto flits=(__write_cmd.m_nbytes+bytes-1)/bytes+1;
            const auto source=std::max(SRC_DELAY(prediction),std::max(__write_cmd.m_cycle,__read_cmd.m_cycle)+flits);
            const auto destination=std::max(DST_DELAY(prediction),source+1);
            return CmdDelayPair(source,destination);
        };
        const bool is_tagged_request = isStablePacketDescriptor(__write_cmd.m_desc);
        const bool has_packet_delay = is_tagged_request
            ? m_src_delay_map.hasPacket(__write_cmd.m_src, __write_cmd.m_src,
                                        __write_cmd.m_dst, __write_cmd.m_desc)
            : m_src_delay_map.hasAddr(__write_cmd.m_src, __write_cmd.m_src,
                                      __write_cmd.m_dst);
        if (!has_packet_delay) {
            if(rendezvous)return causal_bounds(CmdDelayPair(0,0));
            return causal_bounds(getDefaultEndCycle(__write_cmd, __read_cmd));
        }

        NetworkDelayItem delay_info = is_tagged_request
            ? m_src_delay_map.frontPacket(__write_cmd.m_src, __write_cmd.m_src,
                                          __write_cmd.m_dst, __write_cmd.m_desc)
            : m_src_delay_map.front(__write_cmd.m_src, __write_cmd.m_src,
                                    __write_cmd.m_dst);

        if (is_tagged_request) {
            m_src_delay_map.popPacket(__write_cmd.m_src, __write_cmd.m_src,
                                      __write_cmd.m_dst, __write_cmd.m_desc);
        } else {
            m_src_delay_map.pop(__write_cmd.m_src, __write_cmd.m_src, __write_cmd.m_dst);
        }
        // Optional absolute-completion Picard iterate for the horizontal NoC.
        // Only the numerical predictor changes; actual PopNet execution is
        // untouched. At an accepted fixed point old/current source issue
        // timestamps coincide, so this is algebraically the legacy formula.
        // Vertical R2 traffic and native synchronization flags are unchanged.
        const char* absolute_predictor=std::getenv("LEGOSIM_ABSOLUTE_NOC_COMPLETIONS");
        if(absolute_predictor&&std::string(absolute_predictor)=="1"&&
           isStableNocFlowDescriptor(__write_cmd.m_desc)&&!(__write_cmd.m_desc&0xF0000)){
            const auto source_done=delay_info.m_cycle+delay_info.m_delay_list.at(0);
            const auto receive_done=delay_info.m_cycle+delay_info.m_delay_list.at(1);
            return causal_bounds(CmdDelayPair(std::max(source_done,__write_cmd.m_cycle),
                                std::max({receive_done,__write_cmd.m_cycle,__read_cmd.m_cycle})));
        }
        // Launch/Barrier/Lock/Unlock communication.
        if (__write_cmd.m_desc & (InterChiplet::SPD_LAUNCH | InterChiplet::SPD_BARRIER |
                                  InterChiplet::SPD_LOCK | InterChiplet::SPD_UNLOCK)) {
            // Forward packet.
            InterChiplet::InnerTimeType pac_delay_src = delay_info.m_delay_list[0];
            InterChiplet::InnerTimeType pac_delay_dst = delay_info.m_delay_list[1];
            InterChiplet::InnerTimeType write_end_time = __write_cmd.m_cycle + pac_delay_src;
            InterChiplet::InnerTimeType read_end_time = __write_cmd.m_cycle + pac_delay_dst;
            if (__read_cmd.m_cycle > read_end_time) {
                read_end_time = __read_cmd.m_cycle;
            }
            // Acknowledge packet.
            InterChiplet::InnerTimeType ack_delay_src = delay_info.m_delay_list[2];
            InterChiplet::InnerTimeType ack_delay_dst = delay_info.m_delay_list[3];
            read_end_time = read_end_time + ack_delay_src;
            write_end_time = read_end_time - ack_delay_src + ack_delay_dst;

            return causal_bounds(CmdDelayPair(write_end_time, read_end_time));
        }
        // Normal communication.
        else {
            // Forward packet.
            InterChiplet::InnerTimeType pac_delay_src = delay_info.m_delay_list[0];
            InterChiplet::InnerTimeType pac_delay_dst = delay_info.m_delay_list[1];
            InterChiplet::InnerTimeType write_end_time = __write_cmd.m_cycle + pac_delay_src;
            InterChiplet::InnerTimeType read_end_time = __write_cmd.m_cycle + pac_delay_dst;
            if (__read_cmd.m_cycle > read_end_time) {
                read_end_time = __read_cmd.m_cycle;
            }
            return causal_bounds(CmdDelayPair(write_end_time, read_end_time));
        }
    }

    InterChiplet::InnerTimeType getBarrierCycle(
        const std::vector<InterChiplet::SyncCommand>& barrier_items) {
        InterChiplet::InnerTimeType barrier_cycle = 0;
        for (auto& item : barrier_items) {
            InterChiplet::InnerTimeType t_cycle = 0;
            if (!m_src_delay_map.hasAddr(item.m_src, item.m_src, item.m_dst)) {
                t_cycle = getDefaultEndCycle(item);
            } else {
                NetworkDelayItem delay_info =
                    m_src_delay_map.front(item.m_src, item.m_src, item.m_dst);
                t_cycle = delay_info.m_cycle + delay_info.m_delay_list[1];
            }

            if (t_cycle > barrier_cycle) {
                barrier_cycle = t_cycle;
            }
        }
        return barrier_cycle;
    }

   public:
    /**
     * @brief Get end cycle of one communication if cannot find this communication from delay
     * list.
     * @param __write_cmd Write command
     * @return End cycle of this communication, used to acknowledge SYNC command.
     */
    InterChiplet::InnerTimeType getDefaultEndCycle(const InterChiplet::SyncCommand& write_cmd) {
        if (isStableNpuRequestIdDescriptor(write_cmd.m_desc) && HbTransport::enabled()) {
            return write_cmd.m_cycle + HbTransport::serialization(write_cmd.m_nbytes);
        }
        // TODO: Get more accurate end cycle.
        int pac_size = write_cmd.m_nbytes / PAC_PAYLOAD_BYTE +
                       ((write_cmd.m_nbytes % PAC_PAYLOAD_BYTE) > 0 ? 1 : 0) + 1;

        return write_cmd.m_cycle + pac_size;
    }
    /**
     * @brief Get end cycle of one communication if cannot find this communication from delay
     * list.
     * @param __write_cmd Write command
     * @param __read_cmd  Read command.
     * @return End cycle of this communication, used to acknowledge SYNC command.
     */
    CmdDelayPair getDefaultEndCycle(const InterChiplet::SyncCommand& write_cmd,
                                    const InterChiplet::SyncCommand& read_cmd) {
        if (isStableNpuRequestIdDescriptor(write_cmd.m_desc) && HbTransport::enabled()) {
            if (write_cmd.m_nbytes != read_cmd.m_nbytes ||
                write_cmd.m_src != read_cmd.m_src || write_cmd.m_dst != read_cmd.m_dst ||
                write_cmd.m_desc != read_cmd.m_desc) {
                throw std::runtime_error("mismatched vertical memory transfer");
            }
            const auto done = std::max(write_cmd.m_cycle, read_cmd.m_cycle) +
                              HbTransport::serialization(write_cmd.m_nbytes);
            return CmdDelayPair(done, done);
        }
        // TODO: Get more accurate end cycle.
        int pac_size = write_cmd.m_nbytes / PAC_PAYLOAD_BYTE +
                       ((write_cmd.m_nbytes % PAC_PAYLOAD_BYTE) > 0 ? 1 : 0) + 1;

        if (write_cmd.m_cycle >= read_cmd.m_cycle) {
            return CmdDelayPair(write_cmd.m_cycle + pac_size, write_cmd.m_cycle + pac_size);
        } else {
            return CmdDelayPair(read_cmd.m_cycle + pac_size, read_cmd.m_cycle + pac_size);
        }
    }

   private:
    int m_item_count;

    /**
     * @brief Launch delay list. Key is the destination address and value is a list of delay item.
     */
    NetworkDelayMap m_src_delay_map;
    /**
     * @brief Launch order. Key is the destination address and value is a list of delay item.
     */
    NetworkDelayMap m_launch_delay_map;
    /**
     * @brief Barrier order. Key is the destination address and value is a list of delay item.
     */
    NetworkDelayMap m_barrier_delay_map;
    /**
     * @brief Lock order. Key is the destination address and value is a list of delay item.
     */
    NetworkDelayMap m_lock_delay_map;
    /**
     * @brief Unlock order. Key is the destination address and value is a list of delay item.
     */
    NetworkDelayMap m_unlock_delay_map;
};
/**
 * @}
 */
