#pragma once
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <map>
#include <cstdio>
#include <unistd.h>
#include <cerrno>
#include "subsecond_time.h"
#include "log.h"
// Simulator-only transaction IDs, not architecture payload or guessed latency.
class SoftwareMaintenanceTracker {
 std::mutex mutex;std::condition_variable cv;
 UInt64 next=0;std::map<UInt64,IntPtr> pending;SubsecondTime latest=SubsecondTime::Zero();
 template<class... Args> static void emit(const char* format, Args... args){
  char record[256];
  const int length=std::snprintf(record,sizeof(record),format,args...);
  LOG_ASSERT_ERROR(length>0 && length<static_cast<int>(sizeof(record)), "invalid maintenance record length");
  ssize_t written;
  do { written=::write(STDERR_FILENO,record,length); } while(written<0 && errno==EINTR);
  LOG_ASSERT_ERROR(written==length,"incomplete maintenance record write");
 }
public:
 static SoftwareMaintenanceTracker& instance(){static SoftwareMaintenanceTracker t;return t;}
 UInt64 issue(IntPtr address){std::lock_guard<std::mutex> l(mutex);UInt64 id=++next;pending[id]=address;return id;}
 void complete(UInt64 id,IntPtr address,SubsecondTime start,SubsecondTime done){
  std::lock_guard<std::mutex> l(mutex);auto it=pending.find(id);
  LOG_ASSERT_ERROR(it!=pending.end() && it->second==address,"unmatched directory maintenance completion");
  LOG_ASSERT_ERROR(done>=start,"negative directory write latency");
  pending.erase(it);if(done>latest)latest=done;
  emit("MAINT_WRITE_ACK %llu %llu %llu %llu\n",(unsigned long long)id,(unsigned long long)address,(unsigned long long)start.getFS(),(unsigned long long)done.getFS());cv.notify_all();
 }
 SubsecondTime drain(SubsecondTime now){std::unique_lock<std::mutex> l(mutex);UInt64 issued=next;
  bool ready=cv.wait_for(l,std::chrono::seconds(10),[this]{return pending.empty();});
  LOG_ASSERT_ERROR(ready,"directory maintenance timed out with unacknowledged writes");
  SubsecondTime done=latest>now?latest:now;
  emit("MAINT_DRAIN %llu %llu %llu %llu\n",(unsigned long long)issued,(unsigned long long)pending.size(),(unsigned long long)now.getFS(),(unsigned long long)done.getFS());return done;
 }
};
