#pragma once
#include <cmath>
#include <map>
extern "C" void hb_thermal_init(const char*,const char*,int);
extern "C" void hb_thermal_step(const double*,double,double*);
struct ThermalLoop {
    bool enabled=false;double threshold=1e9,frequency=.75;long next=0;
    std::array<double,16> scale;
    struct Window { std::array<double,16> busy{},dynamic{},memory{}; };
    std::map<long,Window> windows;
    std::ofstream trace,power,decisions,activity;
    ThermalLoop(const std::string &out) {
        scale.fill(1.);
        const char *cfg=std::getenv("HB_THERMAL_CONFIG");if(!cfg||!*cfg)return;
        enabled=true;
        threshold=envd("HB_THROTTLE_C","1000000000");frequency=envd("HB_THROTTLE_F","0.75");
        if(frequency<=0||frequency>1)throw std::runtime_error("invalid thermal frequency");
        hb_thermal_init(cfg,envs("HB_THERMAL_LCF").c_str(),int(envd("HB_THERMAL_GRID","16")));
        trace.open(out+"/temperature.csv");power.open(out+"/power.csv");decisions.open(out+"/thermal_decisions.csv");activity.open(out+"/thermal_activity.csv");
        for(auto *f:{&trace,&power}){*f<<"window,end_cycle";for(int n=0;n<16;n++)for(auto u:{"CORE","LBUF","SRAM","RTR","NI"})*f<<",N"<<n<<'_'<<u;for(int n=0;n<16;n++)*f<<",CH"<<n<<"_DRAM";*f<<'\n'<<std::setprecision(17);}
        decisions<<"window,decision_cycle,npu,observed_max_logic_c,next_frequency\n";
        activity<<"window,npu,allocated_busy_cycles,dynamic_scaled_cycles,represented_mem_bytes,crossbar_flits,link_flits\n";
    }
    void reserve(int pe,double a,double b,double share,double f,bool compute,uint64_t bytes=0) {
        if(!enabled||b<=a)return;
        for(long w=long(a/100000);w<=long((b-1e-8)/100000);w++){
            double overlap=std::max(0.,std::min(b,(w+1)*100000.)-std::max(a,w*100000.));
            if(compute){windows[w].busy[pe]+=overlap*share;windows[w].dynamic[pe]+=overlap*share*f*f*f;}
            else windows[w].memory[pe]+=bytes*overlap/(b-a);
        }
    }
    void step(double end) {
        if(!enabled||end<=next*100000.)return;
        auto &w=windows[next];double duration=end-next*100000.;double values[96],temps[96];
        for(int n=0;n<16;n++){
            if(w.busy[n]>duration+1e-5)throw std::runtime_error("thermal compute budget overflow");
            auto counts=PopnetMicroStats::instance().coupled_counts((n%4)*4+n/4,next);
            double u=w.dynamic[n]/duration,m=std::min(1.,w.memory[n]/(duration*102.4)),xa=std::min(1.,counts.first/(duration*5.)),li=std::min(1.,counts.second/(duration*4.));
            values[n*5]=.35+3*u;values[n*5+1]=.10+.45*u;values[n*5+2]=.15+.65*std::min(1.,u+m);
            values[n*5+3]=.06+.25*xa+.10*li;values[n*5+4]=.04+.20*li;values[80+n]=.18+.82*m;
            activity<<next<<','<<n<<','<<w.busy[n]<<','<<w.dynamic[n]<<','<<w.memory[n]<<','<<counts.first<<','<<counts.second<<'\n';
        }
        hb_thermal_step(values,duration*1e-9,temps);
        trace<<next<<','<<end;power<<next<<','<<end;
        for(int k=0;k<96;k++){if(!std::isfinite(temps[k]))throw std::runtime_error("nonfinite thermal state");trace<<','<<temps[k];power<<','<<values[k];}
        trace<<'\n';power<<'\n';
        for(int n=0;n<16;n++){double peak=*std::max_element(temps+n*5,temps+n*5+5);scale[n]=peak>=threshold?frequency:1.;decisions<<next<<','<<end<<','<<n<<','<<peak<<','<<scale[n]<<'\n';}
        windows.erase(next++);
    }
};
