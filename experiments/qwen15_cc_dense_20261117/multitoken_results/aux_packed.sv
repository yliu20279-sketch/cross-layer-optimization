module single_cs #(parameter W=256)(
  input wire clk, reset,
  input wire [5:0] config_bits,
  input wire [5*W-1:0] in_data,
  input wire [4:0] in_valid, out_ready,
  output wire [4:0] in_ready, out_valid,
  output wire [W-1:0] out_data,
  output wire occupied
);
  wire [2:0] output_port=config_bits[4:2];
  wire [1:0] code=config_bits[1:0];
  // The MUX inputs are in ascending port order, excluding the output itself.
  wire [2:0] input_port={1'b0,code}+{2'b0,({1'b0,code}>=output_port)};
  wire slot_ready;
  noc_slot #(.W(W)) pipeline(clk,reset,in_data[input_port*W+:W],
    config_bits[5] && in_valid[input_port],out_ready[output_port],
    slot_ready,out_data,occupied);
  for(genvar p=0;p<5;p=p+1) begin: ports
    assign in_ready[p]=config_bits[5] && input_port==p && slot_ready;
    assign out_valid[p]=config_bits[5] && output_port==p && occupied;
  end
endmodule

module aux13 #(parameter W=256)(
  input wire clk, reset,
  input wire cfg_valid,
  input wire [77:0] cfg,
  output wire cfg_ready,
  output reg cfg_applied, cfg_rejected,
  input wire [16*W-1:0] tx_data,
  input wire [15:0] tx_valid, rx_ready,
  output reg [15:0] tx_ready, rx_valid,
  output reg [16*W-1:0] rx_data
);
  // Endpoint IDs 0..15; switch peers are encoded as 16 + 5*CS + port.
  // Lower port order: NW, NE, SW, SE, U. Upper order follows the figure table.
  function automatic integer peer(input integer port_id);
    case(port_id)
      0: peer=4;
      1: peer=5;
      2: peer=0;
      3: peer=1;
      4: peer=63;
      5: peer=5;
      6: peer=6;
      7: peer=1;
      8: peer=2;
      10: peer=6;
      11: peer=7;
      12: peer=2;
      13: peer=3;
      14: peer=68;
      15: peer=8;
      16: peer=9;
      17: peer=4;
      18: peer=5;
      20: peer=9;
      21: peer=10;
      22: peer=5;
      23: peer=6;
      25: peer=10;
      26: peer=11;
      27: peer=6;
      28: peer=7;
      30: peer=12;
      31: peer=13;
      32: peer=8;
      33: peer=9;
      34: peer=73;
      35: peer=13;
      36: peer=14;
      37: peer=9;
      38: peer=10;
      40: peer=14;
      41: peer=15;
      42: peer=10;
      43: peer=11;
      44: peer=78;
      45: peer=66;
      46: peer=72;
      47: peer=20;
      50: peer=61;
      51: peer=77;
      52: peer=30;
      55: peer=76;
      56: peer=62;
      57: peer=50;
      60: peer=71;
      61: peer=67;
      62: peer=60;
      default: peer=-1;
    endcase
  endfunction
  reg [77:0] active;
  wire [12:0] occupied;
  assign cfg_ready=!reset && !(|occupied);
  wire [12:0][4:0] iv, ir, ov, rd;
  wire [12:0][5*W-1:0] idata;
  wire [12:0][W-1:0] odata;
  wire [4:0] candidate_in [0:12], candidate_out [0:12];
  wire [4:0] input_ok [0:12], output_ok [0:12];
  wire [12:0] reached [0:13];
  wire [12:0] legal_switch;
  wire [15:0] legal_node;
  assign reached[0]=0;
  for(genvar s=0;s<13;s=s+1) begin: validate_switch
    wire enabled=cfg[6*s+5];
    wire [2:0] op=cfg[6*s+2+:3];
    wire [2:0] code={1'b0,cfg[6*s+:2]};
    wire [2:0] ip=code+{2'b0,(code>=op)};
    wire [12:0] reachable_input [0:4];
    for(genvar p=0;p<5;p=p+1) begin: validate_port
      localparam P=peer(5*s+p);

      assign candidate_in[s][p]=enabled && ip==p;
      assign candidate_out[s][p]=enabled && op==p;
      if(P<0) begin
        assign input_ok[s][p]=0;
        assign output_ok[s][p]=0;
        assign reachable_input[p]=0;
      end else if(P<16) begin
        assign input_ok[s][p]=1;
        assign output_ok[s][p]=1;
        assign reachable_input[p]='1;
      end else begin
        localparam T=(P-16)/5, Q=(P-16)%5;
        assign input_ok[s][p]=candidate_out[T][Q];
        assign output_ok[s][p]=candidate_in[T][Q];
        for(genvar hop=0;hop<13;hop=hop+1)
          assign reachable_input[p][hop]=reached[hop][T];
      end
    end
    for(genvar hop=0;hop<13;hop=hop+1) begin: propagate
      wire [4:0] incoming;
      for(genvar p=0;p<5;p=p+1)
        assign incoming[p]=candidate_in[s][p] && reachable_input[p][hop];
      assign reached[hop+1][s]=|incoming;
    end
    assign legal_switch[s]=!enabled ||
      ((|(candidate_in[s]&input_ok[s])) &&
       (|(candidate_out[s]&output_ok[s])) && reached[13][s]);
  end
  for(genvar node=0;node<16;node=node+1) begin: validate_node
    wire [35:0] sources, sinks;
    for(genvar c=0;c<9;c=c+1)
      for(genvar p=0;p<4;p=p+1) begin: attachment_port
        assign sources[4*c+p]=(peer(5*c+p)==node) && candidate_in[c][p];
        assign sinks[4*c+p]=(peer(5*c+p)==node) && candidate_out[c][p];
      end
    assign legal_node[node]=((sources&(sources-1'b1))==0) &&
                             ((sinks&(sinks-1'b1))==0);
  end
  wire legal=(&legal_switch) && (&legal_node);
  always @(posedge clk) begin
    cfg_applied<=0; cfg_rejected<=0;
    if(reset) active<=0;
    else if(cfg_valid && cfg_ready) begin
      if(legal) begin active<=cfg; cfg_applied<=1; end
      else cfg_rejected<=1;
    end
  end

  for(genvar s=0;s<13;s=s+1) begin: switches
    single_cs #(.W(W)) cs(clk,reset,active[6*s+:6],idata[s],iv[s],rd[s],
      ir[s],ov[s],odata[s],occupied[s]);
    for(genvar p=0;p<5;p=p+1) begin: ports
      localparam P=peer(5*s+p);
      if(P<0) begin
        assign iv[s][p]=0;
        assign idata[s][p*W+:W]=0;
        assign rd[s][p]=0;
      end else if(P<16) begin
        assign iv[s][p]=tx_valid[P] && !cfg_valid;
        assign idata[s][p*W+:W]=tx_data[P*W+:W];
        assign rd[s][p]=rx_ready[P];
      end else begin
        localparam T=(P-16)/5, Q=(P-16)%5;
        assign iv[s][p]=ov[T][Q];
        assign idata[s][p*W+:W]=odata[T];
        assign rd[s][p]=ir[T][Q];
      end
    end
  end
  integer s, p, n;
  always @* begin
    tx_ready=0; rx_valid=0; rx_data=0;
    for(s=0;s<9;s=s+1)
      for(p=0;p<4;p=p+1) begin
        n=peer(5*s+p);
        if(ir[s][p] && !cfg_valid) tx_ready[n]=1;
        if(ov[s][p]) begin
          rx_valid[n]=1;
          rx_data[n*W+:W]=odata[s];
        end
      end
  end
endmodule

module noc_top #(parameter W=256)(
  input wire clk, reset,
  input wire cfg_valid, input wire [77:0] cfg,
  output wire cfg_ready, cfg_applied, cfg_rejected,
  input wire [16*(W+4)-1:0] mesh_tx_data,
  input wire [15:0] mesh_tx_valid, mesh_rx_ready,
  output wire [15:0] mesh_tx_ready, mesh_rx_valid,
  output wire [16*W-1:0] mesh_rx_data,
  input wire [16*W-1:0] aux_tx_data,
  input wire [15:0] aux_tx_valid, aux_rx_ready,
  output wire [15:0] aux_tx_ready, aux_rx_valid,
  output wire [16*W-1:0] aux_rx_data
);
  mesh16 #(.W(W)) base(clk,reset,mesh_tx_data,mesh_tx_valid,mesh_rx_ready,
    mesh_tx_ready,mesh_rx_valid,mesh_rx_data);
  aux13 #(.W(W)) bypass(clk,reset,cfg_valid,cfg,cfg_ready,cfg_applied,cfg_rejected,
    aux_tx_data,aux_tx_valid,aux_rx_ready,aux_tx_ready,aux_rx_valid,aux_rx_data);
endmodule

