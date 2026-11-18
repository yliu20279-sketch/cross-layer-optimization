module split_width_link #(parameter int DEPTH=8)(
 input logic clk,reset,input logic [2:0] global_lanes,
 input logic [1:0] in_valid,input noc_pkg::flit_t in_flit[2],output logic [3:0] in_credit[2],
 output logic [1:0] out_valid,output noc_pkg::flit_t out_flit[2],input logic [3:0] out_credit[2],output logic busy
);
 import noc_pkg::*;
 // One physical bundle: four 64-bit data lanes. Lane mode selects the
 // global or local stream; each lane has VN/head/tail control sidebands.
 logic [65:0] txmem[8][DEPTH],rxmem[8][DEPTH];
 logic [$clog2(DEPTH)-1:0] tw[8],tr[8],rw[8],rr[8];
 logic [$clog2(DEPTH+1)-1:0] tc[8],rc[8];
 logic [1:0] tf[2],rf[2],next_tf[2];
 logic [67:0] lane_data[4];logic [3:0] lane_valid;
 int moved[8],selected[4],inject[2],output_v[2];
 logic direct;
 assign direct=global_lanes==0||global_lanes==4;
 for(genvar d=0;d<2;d++)for(genvar v=0;v<4;v++)begin
  assign in_credit[d][v]=!reset&&(direct?((d==0)==(global_lanes==4)&&out_credit[d][v]):tc[4*d+v]<=DEPTH-4);
 end
 always_comb begin
  busy=0;lane_valid=0;out_valid=0;
  for(int q=0;q<8;q++)begin moved[q]=0;busy|=tc[q]!=0||rc[q]!=0;end
  for(int d=0;d<2;d++)begin
   inject[d]=-1;output_v[d]=-1;out_flit[d]='0;next_tf[d]=tf[d];
   if(!reset&&!direct&&in_valid[d]&&in_credit[d][in_flit[d][259:258]])inject[d]=4*d+int'(in_flit[d][259:258]);
  end
  for(int l=0;l<4;l++)begin
   automatic int domain=l<global_lanes?0:1;
   selected[l]=-1;lane_data[l]='0;
   for(int t=0;t<4;t++)begin
    automatic int v=(next_tf[domain]+t)%4,q=4*domain+v;
    if(!reset&&!direct&&selected[l]<0&&int'(tc[q])>moved[q]&&int'(rc[q])+moved[q]<DEPTH)begin
     selected[l]=q;lane_valid[l]=1;lane_data[l]={2'(v),txmem[q][(int'(tr[q])+moved[q])%DEPTH]};
     moved[q]++;next_tf[domain]=2'((v+1)%4);
    end
   end
  end
  for(int d=0;d<2;d++)for(int t=0;t<4;t++)begin
   automatic int v=(rf[d]+t)%4,q=4*d+v;
   if(!reset&&!direct&&output_v[d]<0&&rc[q]>=4&&out_credit[d][v])begin
    output_v[d]=q;out_valid[d]=1;out_flit[d][259:258]=2'(v);
    for(int k=0;k<4;k++)out_flit[d][k*64+:64]=rxmem[q][(int'(rr[q])+k)%DEPTH][63:0];
    out_flit[d][257]=rxmem[q][rr[q]][64];out_flit[d][256]=rxmem[q][(int'(rr[q])+3)%DEPTH][65];
   end
  end
  if(direct&&!reset)begin
   automatic int d=global_lanes==4?0:1;
   for(int l=0;l<4;l++)begin
    lane_valid[l]=in_valid[d]&&out_credit[d][in_flit[d][259:258]];
    lane_data[l]={in_flit[d][259:258],in_flit[d][256]&&l==3,in_flit[d][257]&&l==0,in_flit[d][l*64+:64]};
    out_flit[d][l*64+:64]=lane_data[l][63:0];
   end
   out_valid[d]=&lane_valid;out_flit[d][259:258]=lane_data[0][67:66];
   out_flit[d][257]=lane_data[0][64];out_flit[d][256]=lane_data[3][65];
  end
 end
 always_ff @(posedge clk)begin
  if(reset)begin
   for(int d=0;d<2;d++)begin tf[d]<=0;rf[d]<=0;end
   for(int q=0;q<8;q++)begin tw[q]<=0;tr[q]<=0;rw[q]<=0;rr[q]<=0;tc[q]<=0;rc[q]<=0;end
  end else if(!direct)begin
   for(int d=0;d<2;d++)begin tf[d]<=next_tf[d];if(output_v[d]>=0)rf[d]<=2'((output_v[d]+1)%4);end
   for(int q=0;q<8;q++)begin
    automatic int d=q/4,enq=inject[d]==q?4:0,deq=output_v[d]==q?4:0;
    tc[q]<=($clog2(DEPTH+1))'(int'(tc[q])+enq-moved[q]);rc[q]<=($clog2(DEPTH+1))'(int'(rc[q])+moved[q]-deq);
    tw[q]<=($clog2(DEPTH))'((int'(tw[q])+enq)%DEPTH);tr[q]<=($clog2(DEPTH))'((int'(tr[q])+moved[q])%DEPTH);
    rw[q]<=($clog2(DEPTH))'((int'(rw[q])+moved[q])%DEPTH);rr[q]<=($clog2(DEPTH))'((int'(rr[q])+deq)%DEPTH);
    if(inject[d]==q)for(int k=0;k<4;k++)txmem[q][(int'(tw[q])+k)%DEPTH]<={in_flit[d][256]&&k==3,in_flit[d][257]&&k==0,in_flit[d][k*64+:64]};
    for(int l=0;l<4;l++)if(lane_valid[l]&&(l<global_lanes?0:1)==d&&int'(lane_data[l][67:66])==q%4)begin
     automatic int pos=0;for(int j=0;j<l;j++)if(lane_valid[j]&&(j<global_lanes?0:1)==d&&lane_data[j][67:66]==lane_data[l][67:66])pos++;
     rxmem[q][(int'(rw[q])+pos)%DEPTH]<=lane_data[l][65:0];
    end
    assert(int'(tc[q])+enq-moved[q]<=DEPTH&&int'(rc[q])+moved[q]-deq<=DEPTH)else $fatal(1,"split link FIFO overflow");
   end
  end
 end
endmodule
