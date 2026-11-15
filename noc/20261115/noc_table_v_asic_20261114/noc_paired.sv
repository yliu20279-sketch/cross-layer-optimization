module noc_paired #(parameter W=256, parameter ENHANCED=1)(
  input wire clk, reset,
  input wire cfg_valid, input wire [77:0] cfg,
  output wire cfg_ready, cfg_applied, cfg_rejected,
  input wire [16*(W+4)-1:0] tx_data,
  input wire [15:0] tx_valid, rx_ready, use_circuit,
  input wire [63:0] tx_cs,
  output wire [15:0] tx_ready, rx_valid,
  output wire [16*W-1:0] rx_data
);
  wire [15:0] mesh_ready, mesh_valid, mesh_rx_ready, mesh_tx_valid;
  wire [15:0] cs_ready, cs_valid, cs_rx_ready;
  wire [16*W-1:0] mesh_data, cs_data, cs_tx_data;
  mesh16 #(.W(W)) mesh(clk,reset,tx_data,mesh_tx_valid,mesh_rx_ready,
    mesh_ready,mesh_valid,mesh_data);
  if(ENHANCED) begin: circuits
    aux13 #(.W(W)) bypass(clk,reset,cfg_valid,cfg,cfg_ready,cfg_applied,cfg_rejected,
      cs_tx_data,tx_valid & use_circuit,tx_cs,cs_rx_ready,cs_ready,cs_valid,cs_data);
  end else begin: baseline
    assign {cfg_ready,cfg_applied,cfg_rejected,cs_ready,cs_valid,cs_data}='0;
  end
  for(genvar n=0;n<16;n=n+1) begin: ni
    wire circuit=ENHANCED && use_circuit[n];
    wire slot_ready;
    reg prefer_cs;
    wire choose_cs=cs_valid[n] && (prefer_cs || !mesh_valid[n]);
    assign mesh_tx_valid[n]=tx_valid[n] && !circuit;
    assign tx_ready[n]=circuit ? cs_ready[n] : mesh_ready[n];
    assign cs_tx_data[n*W+:W]=tx_data[n*(W+4)+:W];
    assign mesh_rx_ready[n]=slot_ready && !choose_cs;
    assign cs_rx_ready[n]=slot_ready && choose_cs;
    always @(posedge clk)
      if(reset) prefer_cs<=0;
      else if(slot_ready && (mesh_valid[n] || cs_valid[n])) prefer_cs<=!choose_cs;
    noc_slot #(.W(W)) receive_slot(clk,reset,
      choose_cs ? cs_data[n*W+:W] : mesh_data[n*W+:W],
      mesh_valid[n] || cs_valid[n],rx_ready[n],slot_ready,rx_data[n*W+:W],rx_valid[n]);
  end
endmodule
