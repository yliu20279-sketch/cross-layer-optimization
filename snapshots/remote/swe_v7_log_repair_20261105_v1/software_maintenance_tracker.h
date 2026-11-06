#pragma once
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <map>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include "subsecond_time.h"
#include "log.h"
// Simulator-only transaction IDs, not architecture payload or guessed latency.
class SoftwareMaintenanceTracker {
 std::mutex mutex;std::condition_variable cv;
 UInt64 next=0;std::map<UInt64,IntPtr> pending;SubsecondTime latest=SubsecondTime::Zero();
 void record(const char* kind,UInt64 a,UInt64 b,UInt64 c,UInt64 d){
  const char* path=std::getenv("MAINT_EVENT_LOG");
  LOG_ASSERT_ERROR(path && *path,"MAINT_EVENT_LOG must name an isolated event file");
  int fd=::open(path,O_WRONLY|O_CREAT|O_APPEND,0600);
  LOG_ASSERT_ERROR(fd>=0,"maintenance event open failed");
  char row[256];int length=std::snprintf(row,sizeof(row),"%s %llu %llu %llu %llu\n",kind,
    (unsigned long long)a,(unsigned long long)b,(unsigned long long)c,(unsigned long long)d);
  ssize_t written;do {written=::write(fd,row,length);} while(written<0 && errno==EINTR);
  ::close(fd);
  LOG_ASSERT_ERROR(written==length,"maintenance event write failed");
 }
public:
 static SoftwareMaintenanceTracker& instance(){static SoftwareMaintenanceTracker t;return t;}
 UInt64 issue(IntPtr address){std::lock_guard<std::mutex> l(mutex);UInt64 id=++next;pending[id]=address;return id;}
 void complete(UInt64 id,IntPtr address,SubsecondTime start,SubsecondTime done){
  std::lock_guard<std::mutex> l(mutex);auto it=pending.find(id);
  LOG_ASSERT_ERROR(it!=pending.end() && it->second==address,"unmatched directory maintenance completion");
  LOG_ASSERT_ERROR(done>=start,"negative directory write latency");
  pending.erase(it);if(done>latest)latest=done;
  record("MAINT_WRITE_ACK",id,address,start.getFS(),done.getFS());cv.notify_all();
 }
 SubsecondTime drain(SubsecondTime now){std::unique_lock<std::mutex> l(mutex);UInt64 issued=next;
  bool ready=cv.wait_for(l,std::chrono::seconds(10),[this]{return pending.empty();});
  LOG_ASSERT_ERROR(ready,"directory maintenance timed out with unacknowledged writes");
  SubsecondTime done=latest>now?latest:now;
  record("MAINT_DRAIN",issued,pending.size(),now.getFS(),done.getFS());return done;
 }
};
