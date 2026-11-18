module xy_router #(parameter int ID=0,DEPTH=2,BENES=0,ACTIVE_VN=15)(
 input logic clk,reset,
 input logic [4:0] in_valid,input noc_pkg::flit_t in_flit[5],
 output logic [3:0] in_credit[5],
 output logic [4:0] out_valid,output noc_pkg::flit_t out_flit[5],
 input logic [3:0] out_credit[5],
 output logic busy
);
 // Node coordinates are fixed wires; share one core implementation across tiles.
 xy_router_core #(.DEPTH(DEPTH),.BENES(BENES),.ACTIVE_VN(ACTIVE_VN)) impl(.node_id(4'(ID)),.*);
endmodule

module xy_router_core #(parameter int DEPTH=2,BENES=0,ACTIVE_VN=15)(
 input logic [3:0] node_id,
 input logic clk,reset,
 input logic [4:0] in_valid,input noc_pkg::flit_t in_flit[5],
 output logic [3:0] in_credit[5],
 output logic [4:0] out_valid,output noc_pkg::flit_t out_flit[5],
 input logic [3:0] out_credit[5],
 output logic busy
);
 import noc_pkg::*;
 // Ports E,W,+row,-row,local. Independent request/response virtual networks.
 flit_t front[5][4];logic full[5][4],empty[5][4],push[5][4],pop[5][4];
 logic [$clog2(DEPTH+1)-1:0] count[5][4];
 logic [2:0] body_route[5][4],owner[5][4],first[5][4];
 logic locked[5][4];logic [1:0] vfirst[5];logic [2:0] out_first;
 logic [2:0] selected_input[5];logic [1:0] selected_vn[5];
 logic [4:0] used;
 flit_t chosen_data[5],benes_in[8],benes_out[8];logic [23:0] permutation;logic [19:0] benes_configuration;
 if(BENES)begin:benes
  benes8 #(.WIDTH(FW),.ROUTER(1)) b(permutation,benes_in,benes_out,benes_configuration);
  for(genvar o=0;o<5;o++)assign out_flit[o]=benes_out[o];
 end else for(genvar o=0;o<5;o++)assign out_flit[o]=chosen_data[o];
 function automatic logic [2:0] xy(input logic [3:0] dst);
  if(dst[1:0]>node_id[1:0])xy=0;else if(dst[1:0]<node_id[1:0])xy=1;
  else if(dst[3:2]>node_id[3:2])xy=2;else if(dst[3:2]<node_id[3:2])xy=3;else xy=4;
 endfunction
 for(genvar p=0;p<5;p++)for(genvar v=0;v<4;v++)begin:q
  if((ACTIVE_VN>>v)&1)begin
   assign in_credit[p][v]=!reset&&!full[p][v];
   assign push[p][v]=in_valid[p]&&in_flit[p][259:258]==v&&in_credit[p][v];
   noc_fifo #(.WIDTH(FW),.DEPTH(DEPTH)) f(clk,reset,push[p][v],pop[p][v],in_flit[p],front[p][v],full[p][v],empty[p][v],count[p][v]);
  end else begin assign in_credit[p][v]=0;assign push[p][v]=0;assign front[p][v]='0;assign full[p][v]=1;assign empty[p][v]=1;assign count[p][v]=0;end
 end
 always_comb begin
  busy=0;used=0;out_valid=0;
  for(int p=0;p<5;p++)begin
   selected_input[p]=0;selected_vn[p]=0;
   for(int v=0;v<4;v++)begin pop[p][v]=0;busy|=!empty[p][v];end
  end
  // Rotate output priority to resolve different VNs sharing an input port.
  for(int ot=0;ot<5;ot++)begin
   automatic int o=(out_first+ot)%5;
   for(int vt=0;vt<4;vt++)begin
    automatic int v=(vfirst[o]+vt)%4;
    for(int it=0;it<5;it++)begin
     automatic int i=locked[o][v]?owner[o][v]:(first[o][v]+it)%5;
     automatic logic [2:0] route=front[i][v][257]?xy(front[i][v][251:248]):body_route[i][v];
     if(!out_valid[o]&&!used[i]&&!empty[i][v]&&route==o&&out_credit[o][v])begin
      out_valid[o]=1;selected_input[o]=3'(i);selected_vn[o]=2'(v);
      pop[i][v]=1;used[i]=1;
     end
    end
   end
  end
 end
 // Select wide payloads once, after the narrow arbitration decision.
 for(genvar o=0;o<5;o++)assign chosen_data[o]=out_valid[o]?front[selected_input[o]][selected_vn[o]]:'0;
 if(BENES)begin:benes_inputs
  for(genvar i=0;i<5;i++)begin:input_mux
   always_comb begin
    benes_in[i]='0;
    for(int o=0;o<5;o++)if(out_valid[o]&&selected_input[o]==i)benes_in[i]=chosen_data[o];
   end
  end
  for(genvar i=5;i<8;i++)assign benes_in[i]='0;
  always_comb begin
   automatic logic [4:0] assigned_input=0,assigned_output=out_valid;
   permutation=24'b111_110_101_000_000_000_000_000;
   for(int i=0;i<5;i++)for(int o=0;o<5;o++)if(out_valid[o]&&selected_input[o]==i)begin
    permutation[i*3+:3]=3'(o);assigned_input[i]=1;
   end
   for(int i=0;i<5;i++)begin
    automatic logic found=0;
    if(!assigned_input[i])for(int o=0;o<5;o++)if(!assigned_output[o]&&!found)begin
     permutation[i*3+:3]=3'(o);assigned_output[o]=1;found=1;
    end
   end
  end
 end else begin
  assign permutation='0;
  for(genvar i=0;i<8;i++)assign benes_in[i]='0;
 end
 always_ff @(posedge clk)begin
  if(reset)begin
   out_first<=0;
   for(int o=0;o<5;o++)begin
    vfirst[o]<=0;
    for(int v=0;v<4;v++)begin owner[o][v]<=0;first[o][v]<=0;locked[o][v]<=0;body_route[o][v]<=0;end
   end
  end else begin
   out_first<=out_first==4?0:out_first+1'b1;
   for(int o=0;o<5;o++)if(out_valid[o])begin
    automatic int i=selected_input[o],v=selected_vn[o];
    assert(out_credit[o][v])else $fatal(1,"uncredited router output");
    vfirst[o]<=v==3?0:2'(v+1);
    if(out_flit[o][257])body_route[i][v]<=3'(o);
    if(out_flit[o][256])begin locked[o][v]<=0;first[o][v]<=i==4?0:3'(i+1);end
    else begin locked[o][v]<=1;owner[o][v]<=3'(i);end
   end
  end
 end
endmodule
