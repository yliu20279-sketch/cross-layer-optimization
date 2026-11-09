module upper_cs #(parameter W=256) (
  input wire [3*W-1:0] data_i, input wire [2:0] valid_i,
  input wire [2:0] credit_i, enable, select_second,
  output wire [3*W-1:0] data_o, output wire [2:0] valid_o, credit_o
);
  wire [8:0] selected;
  for (genvar o=0; o<3; o=o+1) begin: outputs
    localparam FIRST = o == 0 ? 1 : 0;
    localparam SECOND = o == 2 ? 1 : 2;
    assign data_o[o*W+:W] = select_second[o] ? data_i[SECOND*W+:W] : data_i[FIRST*W+:W];
    assign valid_o[o] = enable[o] && (select_second[o] ? valid_i[SECOND] : valid_i[FIRST]);
    for (genvar i=0; i<3; i=i+1) begin: inputs
      assign selected[3*i+o] = enable[o] && (select_second[o] ? i==SECOND : i==FIRST);
    end
  end
  for (genvar i=0; i<3; i=i+1) begin: reverse_path
    assign credit_o[i] = |(selected[3*i+:3] & credit_i);
  end
endmodule

module attachment #(parameter W=256) (
  input wire [3:0] node_valid, core_valid, node_credit, core_source_credit,
  input wire [4*W-1:0] node_data, core_data,
  input wire tx_enable, rx_enable, upper_valid, upper_credit,
  input wire [1:0] t, r,
  input wire [W-1:0] upper_data,
  output wire [W-1:0] up_data,
  output wire up_valid, up_credit,
  output wire [3:0] to_core_valid, to_node_valid, source_credit, to_core_credit,
  output wire [4*W-1:0] to_node_data, to_core_data
);
  assign to_core_data = node_data;
  assign up_data = node_data[t*W+:W];
  assign up_valid = tx_enable && node_valid[t];
  assign up_credit = rx_enable && node_credit[r];
  for (genvar i=0; i<4; i=i+1) begin: corners
    assign to_core_valid[i] = node_valid[i] && !(tx_enable && t==i);
    assign to_node_data[i*W+:W] = rx_enable && r==i ? upper_data : core_data[i*W+:W];
    assign to_node_valid[i] = rx_enable && r==i ? upper_valid : core_valid[i];
    assign to_core_credit[i] = node_credit[i] && !(rx_enable && r==i);
    assign source_credit[i] = tx_enable && t==i ? upper_credit : core_source_credit[i];
  end
endmodule

