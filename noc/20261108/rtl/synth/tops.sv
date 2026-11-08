module router_local_top(
    input clk,rst_n,input [1279:0] in_data,input [4:0] in_valid,
    output [4:0] in_ready,output [1279:0] out_data,output [4:0] out_valid,input [4:0] out_ready
);
    aux_xy_router #(.NODE_ID(5),.DEPTH(2),.ENABLE_AUX(0),.DEBUG(0)) r(
        .clk(clk),.rst_n(rst_n),.in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),
        .out_data(out_data),.out_valid(out_valid),.out_ready(out_ready),.buffered_flits(),.pending_aux_gateways());
endmodule
module router_aux_top(
    input clk,rst_n,input [1279:0] in_data,input [4:0] in_valid,
    output [4:0] in_ready,output [1535:0] out_data,output [5:0] out_valid,input [5:0] out_ready
);
    aux_xy_router #(.NODE_ID(5),.DEPTH(2),.ENABLE_AUX(1),.DEBUG(0)) r(
        .clk(clk),.rst_n(rst_n),.in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),
        .out_data(out_data),.out_valid(out_valid),.out_ready(out_ready),.buffered_flits(),.pending_aux_gateways());
endmodule
