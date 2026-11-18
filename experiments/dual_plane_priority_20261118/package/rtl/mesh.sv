module typed_mesh #(parameter int DEPTH=2,BENES=0,SERIAL=0,ACTIVE_VN=15,TYPE_PRIORITY=0)(
 input logic clk,reset,input logic [15:0] tx_valid,input noc_pkg::flit_t tx_flit[16],
 output logic [3:0] tx_credit[16],output logic [15:0] rx_valid,
 output noc_pkg::flit_t rx_flit[16],input logic [3:0] rx_credit[16],output logic busy,input logic [2:0] link_lanes
);
 import noc_pkg::*;
 logic [4:0] iv[16],ov[16];flit_t data_in[16][5],data_out[16][5];
 logic [3:0] credit_in[16][5],credit_out[16][5];logic [15:0] used;
 logic [3:0] link_busy[16];
 always_comb begin busy=|used;for(int n=0;n<16;n++)busy|=|link_busy[n];end
 for(genvar n=0;n<16;n++)begin:node
  for(genvar p=0;p<4;p++)begin:port
   localparam int PEER=p==0?n+1:p==1?n-1:p==2?n+4:n-4;
   localparam bit CONNECTED=p==0?n%4!=3:p==1?n%4!=0:p==2?n/4!=3:n/4!=0;
   if(CONNECTED)begin
    if(SERIAL)begin
     width_link link(clk,reset,link_lanes,ov[PEER][p^1],data_out[PEER][p^1],credit_out[PEER][p^1],iv[n][p],data_in[n][p],credit_in[n][p],link_busy[n][p]);
    end else begin
     assign iv[n][p]=ov[PEER][p^1];assign data_in[n][p]=data_out[PEER][p^1];
     assign credit_out[PEER][p^1]=credit_in[n][p];assign link_busy[n][p]=0;
    end
   end else begin assign iv[n][p]=0;assign data_in[n][p]='0;assign credit_out[n][p]=0;assign link_busy[n][p]=0;end
  end
  assign iv[n][4]=tx_valid[n];assign data_in[n][4]=tx_flit[n];assign tx_credit[n]=credit_in[n][4];
  assign rx_valid[n]=ov[n][4];assign rx_flit[n]=data_out[n][4];assign credit_out[n][4]=rx_credit[n];
  xy_router #(.ID(n),.DEPTH(DEPTH),.BENES(BENES),.ACTIVE_VN(ACTIVE_VN),.TYPE_PRIORITY(TYPE_PRIORITY)) r(clk,reset,iv[n],data_in[n],credit_in[n],ov[n],data_out[n],credit_out[n],used[n]);
 end
endmodule
