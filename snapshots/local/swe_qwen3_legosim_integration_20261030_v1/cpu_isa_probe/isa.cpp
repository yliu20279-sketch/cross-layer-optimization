#include <dlfcn.h>
#include <fstream>
#include "sim_api.h"
int main(int argc,char**argv){void*l=dlopen(argv[1],RTLD_NOW);if(!l)return 3;auto f=(int(*)(const float*,float*,float*,float*,int,int))dlsym(l,"sm");if(!f)return 4;float x[128],y[128],e[128],s[3];for(int i=0;i<128;++i)x[i]=(i-64)*0.125f;SimRoiStart();int rc=f(x,y,s,e,1,128);SimRoiEnd();if(rc)return 5;std::ofstream(argv[2],std::ios::binary).write((char*)y,sizeof(y));return 0;}