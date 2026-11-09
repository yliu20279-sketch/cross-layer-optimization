module diagonal_top #(parameter W=256) (
  input wire [4*W-1:0] node_data,
  input wire [3:0] inject, returned, tx_enable, rx_enable,
  input wire [11:0] enable, select_second,
  output wire [4*W-1:0] delivered,
  output wire [3:0] arrived, credit, leaked
);
  // Clockwise ring 9,10,12,11. A is clockwise, B counterclockwise, D vertical.
  wire [3*W-1:0] data_i [0:3], data_o [0:3];
  wire [2:0] valid_i [0:3], valid_o [0:3], credit_i [0:3], credit_o [0:3];
  for (genvar s=0; s<4; s=s+1) begin: sites
    localparam NEXT=(s+1)%4, PREV=(s+3)%4;
    // Site 1 (CS2) uses SE for N3; site 3 (CS6) uses NW for N12.
    localparam CORNER=s==1 ? 3 : 0;
    wire [4*W-1:0] to_node, to_core_data, core_data;
    wire [3:0] to_core, to_node_valid, source_credit;
    wire [3:0] core_valid, to_core_credit, core_source_credit;
    assign data_i[s][0*W+:W]=data_o[NEXT][1*W+:W];
    assign data_i[s][1*W+:W]=data_o[PREV][0*W+:W];
    assign valid_i[s][0]=valid_o[NEXT][1];
    assign valid_i[s][1]=valid_o[PREV][0];
    assign credit_i[s][0]=credit_o[NEXT][1];
    assign credit_i[s][1]=credit_o[PREV][0];
    upper_cs #(.W(W)) sw(data_i[s],valid_i[s],credit_i[s],
      enable[3*s+:3],select_second[3*s+:3],data_o[s],valid_o[s],credit_o[s]);
    // Core outputs are disabled for this single reserved circuit.
    wire [4*W-1:0] corner_data;
    for (genvar c=0;c<4;c=c+1) begin: lanes
      assign corner_data[c*W+:W]=c==CORNER ? node_data[s*W+:W] : {W{1'b0}};
    end
    terminal_switch #(.W(W)) lower_core(
      .active_cfg(12'h000), .in_data(to_core_data), .in_valid(to_core),
      .downstream_credit(to_core_credit), .out_data(core_data), .out_valid(core_valid),
      .upstream_credit(core_source_credit), .cfg_legal());
    attachment #(.W(W)) attach(
      .node_valid({3'b0,inject[s]} << CORNER), .core_valid(core_valid),
      .node_credit({3'b0,returned[s]} << CORNER), .node_data(corner_data),
      .core_data(core_data), .core_source_credit(core_source_credit), .tx_enable(tx_enable[s]), .rx_enable(rx_enable[s]),
      .upper_valid(valid_o[s][2]), .upper_credit(credit_o[s][2]),
      .t(CORNER[1:0]),.r(CORNER[1:0]),.upper_data(data_o[s][2*W+:W]),
      .up_data(data_i[s][2*W+:W]),.up_valid(valid_i[s][2]),.up_credit(credit_i[s][2]),
      .to_core_valid(to_core),.to_node_valid(to_node_valid),
      .source_credit(source_credit),.to_node_data(to_node),
      .to_core_credit(to_core_credit),.to_core_data(to_core_data));
    assign delivered[s*W+:W]=to_node[CORNER*W+:W];
    assign arrived[s]=to_node_valid[CORNER];
    assign credit[s]=source_credit[CORNER];
    assign leaked[s]=|to_core;
  end
endmodule




