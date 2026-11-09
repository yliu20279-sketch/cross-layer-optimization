module full_fabric #(parameter W=256) (
  input wire [36*W-1:0] in_data,
  input wire [35:0] in_valid, returned,
  input wire [107:0] local_cfg,
  input wire [11:0] enable, select_second,
  input wire [3:0] tx, rx,
  input wire [7:0] tx_corner, rx_corner,
  output wire [36*W-1:0] out_data,
  output wire [35:0] out_valid, credit,
  output wire [8:0] local_legal
);
  // Lower CS IDs are row-major 0..8. Corners are NW, NE, SW, SE.
  // Upper clockwise ring is CS9, CS10, CS12, CS11.
  wire [3*W-1:0] data_i [0:3], data_o [0:3];
  wire [2:0] valid_i [0:3], valid_o [0:3], credit_i [0:3], credit_o [0:3];
  for(genvar s=0;s<4;s=s+1) begin: ring
    localparam NEXT=(s+1)%4, PREV=(s+3)%4;
    assign data_i[s][0+:W]=data_o[NEXT][W+:W];
    assign data_i[s][W+:W]=data_o[PREV][0+:W];
    assign valid_i[s][0]=valid_o[NEXT][1];
    assign valid_i[s][1]=valid_o[PREV][0];
    assign credit_i[s][0]=credit_o[NEXT][1];
    assign credit_i[s][1]=credit_o[PREV][0];
    wire [3*W-1:0] mux_data;
    for(genvar o=0;o<3;o=o+1) begin: isolate_disabled
      assign data_o[s][o*W+:W]=enable[3*s+o] ? mux_data[o*W+:W] : {W{1'b0}};
    end
    upper_cs #(.W(W)) sw(data_i[s],valid_i[s],credit_i[s],
      enable[3*s+:3],select_second[3*s+:3],mux_data,valid_o[s],credit_o[s]);
  end
  for(genvar c=0;c<9;c=c+1) begin: lower
    localparam S=c==0 ? 0 : c==2 ? 1 : c==8 ? 2 : c==6 ? 3 : -1;
    wire [4*W-1:0] ci, co;
    wire [3:0] vi, vo, dc, uc;
    if(S>=0) begin: five_outputs
      attachment #(.W(W)) a(
        .node_valid(in_valid[4*c+:4]), .core_valid(vo),
        .node_credit(returned[4*c+:4]), .node_data(in_data[4*c*W+:4*W]),
        .core_data(co), .core_source_credit(uc),
        .tx_enable(tx[S]), .rx_enable(rx[S]),
        .upper_valid(valid_o[S][2]), .upper_credit(credit_o[S][2]),
        .t(tx_corner[2*S+:2]), .r(rx_corner[2*S+:2]), .upper_data(data_o[S][2*W+:W]),
        .up_data(data_i[S][2*W+:W]), .up_valid(valid_i[S][2]), .up_credit(credit_i[S][2]),
        .to_core_valid(vi), .to_node_valid(out_valid[4*c+:4]), .source_credit(credit[4*c+:4]),
        .to_node_data(out_data[4*c*W+:4*W]), .to_core_credit(dc), .to_core_data(ci));
    end else begin: four_outputs
      assign ci=in_data[4*c*W+:4*W];
      assign vi=in_valid[4*c+:4];
      assign dc=returned[4*c+:4];
      assign out_data[4*c*W+:4*W]=co;
      assign out_valid[4*c+:4]=vo;
      assign credit[4*c+:4]=uc;
    end
    terminal_switch #(.W(W)) core(
      .active_cfg(local_cfg[12*c+:12]), .in_data(ci), .in_valid(vi),
      .downstream_credit(dc), .out_data(co), .out_valid(vo),
      .upstream_credit(uc), .cfg_legal(local_legal[c]));
  end
endmodule

