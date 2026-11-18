module hiband_fabric #(parameter int DEPTH=2,TYPE_PRIORITY=0)(
 input logic clk,reset,input logic [2:0] global_lanes,
 input logic [15:0] tx_valid[2],input noc_pkg::flit_t tx_flit[2][16],output logic [3:0] tx_credit[2][16],
 output logic [15:0] rx_valid[2],output noc_pkg::flit_t rx_flit[2][16],input logic [3:0] rx_credit[2][16],output logic busy
);
 import noc_pkg::*;
 logic [4:0] iv[2][16],ov[2][16];flit_t din[2][16][5],dout[2][16][5];
 logic [3:0] ic[2][16][5],oc[2][16][5];logic used[2][16],link_used[16][4];
 always_comb begin
  busy=0;for(int d=0;d<2;d++)for(int n=0;n<16;n++)busy|=used[d][n];
  for(int n=0;n<16;n++)for(int p=0;p<4;p++)busy|=link_used[n][p];
 end
 for(genvar n=0;n<16;n++)begin:node
  for(genvar p=0;p<4;p++)begin:port
   localparam int PEER=p==0?n+1:p==1?n-1:p==2?n+4:n-4;
   localparam bit CONNECTED=p==0?n%4!=3:p==1?n%4!=0:p==2?n/4!=3:n/4!=0;
   if(CONNECTED)begin
    wire [1:0] incoming,outgoing;flit_t link_input[2],link_output[2];wire [3:0] upstream[2],downstream[2];
    for(genvar d=0;d<2;d++)begin
     assign incoming[d]=ov[d][PEER][p^1];assign link_input[d]=dout[d][PEER][p^1];assign oc[d][PEER][p^1]=upstream[d];
     assign iv[d][n][p]=outgoing[d];assign din[d][n][p]=link_output[d];assign downstream[d]=ic[d][n][p];
    end
    split_width_link link(clk,reset,global_lanes,incoming,link_input,upstream,outgoing,link_output,downstream,link_used[n][p]);
   end else begin
    assign link_used[n][p]=0;
    for(genvar d=0;d<2;d++)begin assign iv[d][n][p]=0;assign din[d][n][p]='0;assign oc[d][n][p]=0;end
   end
  end
  for(genvar d=0;d<2;d++)begin:domain
   assign iv[d][n][4]=tx_valid[d][n];assign din[d][n][4]=tx_flit[d][n];assign tx_credit[d][n]=ic[d][n][4];
   assign rx_valid[d][n]=ov[d][n][4];assign rx_flit[d][n]=dout[d][n][4];assign oc[d][n][4]=rx_credit[d][n];
   xy_router #(.ID(n),.DEPTH(DEPTH),.BENES(1),.TYPE_PRIORITY(TYPE_PRIORITY)) r(clk,reset,iv[d][n],din[d][n],ic[d][n],ov[d][n],dout[d][n],oc[d][n],used[d][n]);
  end
 end
endmodule
