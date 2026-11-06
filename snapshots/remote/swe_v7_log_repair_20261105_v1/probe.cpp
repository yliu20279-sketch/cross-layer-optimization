#include "software_maintenance_tracker.h"
#include <thread>
#include <vector>
int main(){auto&t=SoftwareMaintenanceTracker::instance();std::vector<std::thread> workers;
for(int j=0;j<4;j++)workers.emplace_back([&t,j]{for(int i=0;i<1000;i++){auto id=t.issue(j*1000+i);t.complete(id,j*1000+i,{100},{200});}});
for(auto&w:workers)w.join();t.drain({300});}
