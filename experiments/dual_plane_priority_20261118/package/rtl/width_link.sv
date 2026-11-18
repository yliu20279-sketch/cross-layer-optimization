module width_link #(parameter int DEPTH=16)(
 input logic clk,reset,input logic [2:0] lanes,
 input logic in_valid,input noc_pkg::flit_t in_flit,output logic [3:0] in_credit,
 output logic out_valid,output noc_pkg::flit_t out_flit,input logic [3:0] out_credit,
 output logic busy
);
 import noc_pkg::*;
 // Four-way banked phit FIFOs implement 64/128/192-bit physical links.
 // Three lanes pack across flit boundaries: no ceil(256/192) throughput loss.
 logic [65:0] txmem[4][DEPTH],rxmem[4][DEPTH];
 logic [$clog2(DEPTH)-1:0] tw[4],tr[4],rw[4],rr[4];
 logic [$clog2(DEPTH+1)-1:0] tc[4],rc[4];
 int moved[4];logic [65:0] sent[4];int selected[4];int inject_v,output_v;
 logic [1:0] tf,rf,next_tf;
 for(genvar v=0;v<4;v++)assign in_credit[v]=!reset&&(lanes==4?out_credit[v]:lanes!=0&&tc[v]<=DEPTH-4);
 always_comb begin
  busy=0;out_valid=0;out_flit='0;inject_v=-1;output_v=-1;next_tf=tf;
  for(int v=0;v<4;v++)begin busy|=tc[v]!=0||rc[v]!=0;moved[v]=0;end
  for(int l=0;l<4;l++)begin sent[l]=0;selected[l]=-1;end
   if(!reset&&lanes!=4&&in_valid&&in_credit[in_flit[259:258]])inject_v=int'(in_flit[259:258]);
   for(int l=0;l<4;l++)begin
    for(int t=0;t<4;t++)begin
     automatic int v=(next_tf+t)%4;
     if(!reset&&lanes!=4&&l<lanes&&selected[l]<0&&int'(tc[v])>moved[v]&&int'(rc[v])+moved[v]<DEPTH)begin
      selected[l]=v;sent[l]=txmem[v][(int'(tr[v])+moved[v])%DEPTH];moved[v]++;next_tf=2'((v+1)%4);
     end
    end
   end
   for(int t=0;t<4;t++)begin
    automatic int v=(rf+t)%4;
    if(!reset&&lanes!=4&&output_v<0&&rc[v]>=4&&out_credit[v])begin
     output_v=v;out_valid=1;out_flit[259:258]=2'(v);
     for(int k=0;k<4;k++)out_flit[k*64+:64]=rxmem[v][(int'(rr[v])+k)%DEPTH][63:0];
     out_flit[257]=rxmem[v][rr[v]][64];out_flit[256]=rxmem[v][(int'(rr[v])+3)%DEPTH][65];
    end
   end
  if(lanes==4)begin out_valid=in_valid&&!reset;out_flit=in_flit;end
 end
 always_ff @(posedge clk)begin
  if(reset)begin
   tf<=0;rf<=0;for(int v=0;v<4;v++)begin tw[v]<=0;tr[v]<=0;rw[v]<=0;rr[v]<=0;tc[v]<=0;rc[v]<=0;end
  end else if(lanes!=4)begin
   tf<=next_tf;
   for(int v=0;v<4;v++)begin
    automatic int enq=inject_v==v?4:0,deq=output_v==v?4:0;
    tc[v]<=($clog2(DEPTH+1))'(int'(tc[v])+enq-moved[v]);
    rc[v]<=($clog2(DEPTH+1))'(int'(rc[v])+moved[v]-deq);
    tr[v]<=($clog2(DEPTH))'((int'(tr[v])+moved[v])%DEPTH);
    tw[v]<=($clog2(DEPTH))'((int'(tw[v])+enq)%DEPTH);
    rr[v]<=($clog2(DEPTH))'((int'(rr[v])+deq)%DEPTH);
    rw[v]<=($clog2(DEPTH))'((int'(rw[v])+moved[v])%DEPTH);
    if(inject_v==v)for(int k=0;k<4;k++)txmem[v][(int'(tw[v])+k)%DEPTH]<={in_flit[256]&&k==3,in_flit[257]&&k==0,in_flit[k*64+:64]};
    for(int l=0;l<4;l++)if(selected[l]==v)begin
     automatic int pos=0;for(int j=0;j<l;j++)if(selected[j]==v)pos++;
     rxmem[v][(int'(rw[v])+pos)%DEPTH]<=sent[l];
    end
    assert(int'(tc[v])+enq-moved[v]<=DEPTH&&int'(rc[v])+moved[v]-deq<=DEPTH)else $fatal(1,"phit FIFO overflow");
   end
   if(output_v>=0)rf<=2'((output_v+1)%4);
  end
 end
endmodule
