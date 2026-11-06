#include <cmath>
extern "C" int split(const float*x,const float*w,float*y,int M,int N,int K,int parts,int tile){
 int size=((K+parts*tile-1)/(parts*tile))*tile;
 #pragma omp parallel for
 for(int m=0;m<M;m++)for(int n=0;n<N;n++)for(int p=0;p<parts;p++){float acc=0;int end=(p+1)*size;if(end>K)end=K;for(int k=p*size;k<end;k++)acc=std::fmaf(x[m*K+k],w[n*K+k],acc);y[(p*M+m)*N+n]=acc;}return 0;
}
