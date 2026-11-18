module cs_fabric(
 input logic clk,reset,input logic commit,input logic [77:0] config_state,
 output logic legal,ready,busy,
 input logic [15:0] tx_valid,input noc_pkg::flit_t tx_flit[16],
 input logic [3:0] tx_attachment[16],output logic [15:0] tx_ready,
 output logic [15:0] rx_valid,output noc_pkg::flit_t rx_flit[16],input logic [15:0] rx_ready
);
 import noc_pkg::*;
 function automatic int peer(input int s,p);
  if(s<9&&p<4)return 4*(s/3)+s%3+(p>=2?4:0)+p%2;
  case(5*s+p)
   4:return 16+5*9+2;14:return 16+5*10+2;34:return 16+5*11+2;44:return 16+5*12+2;
   45:return 16+5*10;46:return 16+5*11+1;47:return 16+4;
   50:return 16+5*9;51:return 16+5*12+1;52:return 16+14;
   55:return 16+5*12;56:return 16+5*9+1;57:return 16+34;
   60:return 16+5*11;61:return 16+5*10+1;62:return 16+44;
   default:return -1;
  endcase
 endfunction
 logic [77:0] active;logic [12:0] occupied;
 logic [2:0] input_port[13],output_port[13],candidate_input[13],candidate_output[13];
 logic [12:0] enabled,valid_state;logic [12:0] reach[14];
 flit_t data[13],din[13];logic push[13],pop[13],full[13],empty[13];logic [1:0] count[13];
 flit_t ni_receive_data[16][9];
 flit_t port_data[13][5];wire [4:0] port_valid[13],port_ready[13];
 logic [15:0][3:0] arb_first,arb_owner;logic [15:0] arb_lock;
 logic [15:0][3:0] winner;
 for(genvar n=0;n<16;n++)for(genvar c=0;c<9;c++)begin:physical_ni_receive
  localparam bit CONNECTED=n==peer(c,0)||n==peer(c,1)||n==peer(c,2)||n==peer(c,3);
  if(CONNECTED)assign ni_receive_data[n][c]=data[c];
  else assign ni_receive_data[n][c]='0;
 end
 assign busy=|occupied;assign ready=!busy;
 assign reach[0]='0;assign legal=&valid_state;
 for(genvar s=0;s<13;s++)begin:cs
  assign occupied[s]=!empty[s];
  assign enabled[s]=active[s*6+5];assign output_port[s]=active[s*6+2+:3];
  assign input_port[s]={1'b0,active[s*6+:2]}+3'({1'b0,active[s*6+:2]}>=output_port[s]);
  assign candidate_output[s]=config_state[s*6+2+:3];
  assign candidate_input[s]={1'b0,config_state[s*6+:2]}+3'({1'b0,config_state[s*6+:2]}>=candidate_output[s]);
  // Two elastic entries, one registered forward stage; no ready loop.
  noc_fifo #(.WIDTH(FW),.DEPTH(2)) f(clk,reset,push[s],pop[s],din[s],data[s],full[s],empty[s],count[s]);
  for(genvar p=0;p<5;p++)begin:physical_port
   localparam int P=peer(s,p);
   if(P<0)begin assign port_data[s][p]='0;assign port_valid[s][p]=0;assign port_ready[s][p]=0;end
   else if(P<16)begin
    assign port_data[s][p]=tx_flit[P];assign port_valid[s][p]=tx_valid[P]&&tx_attachment[P]==s;
    assign port_ready[s][p]=rx_ready[P]&&rx_valid[P]&&winner[P]==s;
   end else begin
    localparam int T=(P-16)/5,Q=(P-16)%5;
    assign port_data[s][p]=data[T];assign port_valid[s][p]=enabled[T]&&output_port[T]==Q&&!empty[T];
    assign port_ready[s][p]=enabled[T]&&input_port[T]==Q&&!full[T];
   end
  end
  for(genvar h=0;h<13;h++)begin:r
   wire [4:0] incoming;
   for(genvar p=0;p<5;p++)begin:port
    localparam int Q=peer(s,p);
    if(Q>=0&&Q<16)assign incoming[p]=candidate_input[s]==p;
    else if(Q>=16)assign incoming[p]=candidate_input[s]==p&&reach[h][(Q-16)/5];
    else assign incoming[p]=0;
   end
   assign reach[h+1][s]=config_state[s*6+5]&&(|incoming);
  end
  always_comb begin
   automatic int a=peer(s,candidate_input[s]),b=peer(s,candidate_output[s]);
   automatic logic paired_in,paired_out;
   paired_in=a>=0&&a<16;paired_out=b>=0&&b<16;
   if(a>=16)paired_in=config_state[((a-16)/5)*6+5]&&candidate_output[(a-16)/5]==(a-16)%5;
   if(b>=16)paired_out=config_state[((b-16)/5)*6+5]&&candidate_input[(b-16)/5]==(b-16)%5;
   valid_state[s]=!config_state[s*6+5]||(paired_in&&paired_out&&reach[13][s]&&
      candidate_input[s]<5&&candidate_output[s]<5&&(s<9||(candidate_input[s]<3&&candidate_output[s]<3)));
  end
 end
 always_comb begin
  tx_ready=0;
  for(int n=0;n<16;n++)for(int c=0;c<9;c++)for(int p=0;p<4;p++)
   if(peer(c,p)==n&&enabled[c]&&input_port[c]==p&&tx_attachment[n]==c&&!full[c])tx_ready[n]=!reset;
 end
 always_comb begin
  rx_valid=0;winner='0;
  for(int n=0;n<16;n++)begin
   rx_flit[n]='0;
   for(int ct=0;ct<9;ct++)begin
    automatic int c=arb_lock[n]?arb_owner[n]:(arb_first[n]+ct)%9;
    for(int p=0;p<4;p++)if(peer(c,p)==n)begin
     if(!rx_valid[n]&&enabled[c]&&output_port[c]==p&&!empty[c])begin
      rx_valid[n]=!reset;rx_flit[n]=ni_receive_data[n][c];winner[n]=4'(c);
     end
    end
   end
  end
  for(int s=0;s<13;s++)begin
   push[s]=0;pop[s]=0;din[s]='0;
   if(enabled[s]&&!full[s]&&!reset)begin
    push[s]=port_valid[s][input_port[s]];din[s]=port_data[s][input_port[s]];
   end
   if(enabled[s]&&!empty[s]&&!reset)begin
    pop[s]=port_ready[s][output_port[s]];
   end
  end
 end
 always_ff @(posedge clk)begin
  if(reset)begin active<=0;arb_first<=0;arb_owner<=0;arb_lock<=0;end
  else begin
   if(commit)begin assert(ready&&legal)else $fatal(1,"unsafe CS commit");active<=config_state;end
   for(int n=0;n<16;n++)if(rx_valid[n]&&rx_ready[n])begin
    if(rx_flit[n][256])begin arb_lock[n]<=0;arb_first[n]<=winner[n]==8?0:winner[n]+1'b1;end
    else begin arb_lock[n]<=1;arb_owner[n]<=winner[n];end
   end
  end
 end
endmodule
