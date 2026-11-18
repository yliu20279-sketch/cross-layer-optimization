module benes8 #(parameter int WIDTH=260,ROUTER=0)(
 input logic [23:0] permutation,input logic [WIDTH-1:0] din[8],
 output logic [WIDTH-1:0] dout[8],output logic [19:0] configuration
);
 /* verilator no_inline_module */
 // Canonical 8x8 Beneš: five columns of four 2x2 switches.
 // The adapter uses unicast; unused ports complete a permutation.
 function automatic logic [5:0] route4(input logic [7:0] perm);
  int p[4],color[4],sub[2][2];logic [5:0] cfg;
  for(int i=0;i<4;i++)begin p[i]=int'(perm[i*2+:2]);color[i]=-1;end
  for(int a=0;a<2;a++)for(int b=0;b<2;b++)sub[a][b]=0;
  cfg=0;
  for(int seed=0;seed<4;seed++)begin
   if(color[seed]<0)color[seed]=0;
   for(int pass=0;pass<4;pass++)for(int i=0;i<4;i++)if(color[i]>=0)begin
    color[i^1]=1-color[i];
    for(int j=0;j<4;j++)if(p[j]==(p[i]^1))color[j]=1-color[i];
   end
  end
  for(int i=0;i<4;i++)begin
   sub[color[i]][i/2]=p[i]/2;
   if(i%2==0)cfg[i/2]=1'(color[i]);
   if(p[i]%2==0)cfg[4+p[i]/2]=1'(color[i]);
  end
  cfg[2]=1'(sub[0][0]);cfg[3]=1'(sub[1][0]);return cfg;
 endfunction
 function automatic logic [19:0] route8(input logic [23:0] perm);
  int p[8],color[8];logic [7:0] sub[2];logic [5:0] middle[2];logic [19:0] cfg;
  for(int i=0;i<8;i++)begin p[i]=int'(perm[i*3+:3]);color[i]=-1;end
  sub[0]=0;sub[1]=0;cfg=0;
  for(int seed=0;seed<8;seed++)begin
   if(color[seed]<0)color[seed]=0;
   for(int pass=0;pass<8;pass++)for(int i=0;i<8;i++)if(color[i]>=0)begin
    color[i^1]=1-color[i];
    for(int j=0;j<8;j++)if(p[j]==(p[i]^1))color[j]=1-color[i];
   end
  end
  for(int i=0;i<8;i++)begin
   sub[color[i]][(i/2)*2+:2]=2'(p[i]/2);
   if(i%2==0)cfg[i/2]=1'(color[i]);
   if(p[i]%2==0)cfg[16+p[i]/2]=1'(color[i]);
  end
  for(int c=0;c<2;c++)begin
   middle[c]=route4(sub[c]);
   for(int stage=0;stage<3;stage++)for(int i=0;i<2;i++)cfg[(stage+1)*4+2*i+c]=middle[c][stage*2+i];
  end
  return cfg;
 endfunction
 logic [WIDTH-1:0] stage_data[6][8];
 `include "benes5_lut.svh"
 if(ROUTER)assign configuration=route5(permutation[14:0]);
 else assign configuration=route8(permutation);
 for(genvar p=0;p<8;p++)begin assign stage_data[0][p]=din[p];assign dout[p]=stage_data[5][p];end
 for(genvar s=0;s<5;s++)begin:stage
  localparam int DIST=s==0||s==4?1:s==1||s==3?2:4;
  for(genvar p=0;p<8;p++)if((p&DIST)==0)begin:sw
   localparam int INDEX=(p/(2*DIST))*DIST+(p%DIST);
   assign stage_data[s+1][p]=configuration[s*4+INDEX]?stage_data[s][p+DIST]:stage_data[s][p];
   assign stage_data[s+1][p+DIST]=configuration[s*4+INDEX]?stage_data[s][p]:stage_data[s][p+DIST];
  end
 end
endmodule
