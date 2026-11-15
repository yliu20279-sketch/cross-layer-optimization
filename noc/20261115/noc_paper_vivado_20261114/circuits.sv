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
  input wire [15:0] tx_valid,
  input wire [63:0] tx_cs,
  input wire [15:0] rx_ready,
  output wire [15:0] tx_ready, rx_valid,
  output wire [16*W-1:0] rx_data
);
  // Endpoint IDs 0..15; switch peers are encoded as 16 + 5*CS + port.
  // Lower port order: NW, NE, SW, SE, U. Upper order follows the figure table.
  function automatic integer peer(input integer port_id);
    if(port_id<45 && port_id%5<4) begin
      peer=4*(port_id/15)+(port_id/5)%3+
           (port_id%5>=2 ? 4 : 0)+(port_id%5)%2;
    end else case(port_id)
      4: peer=63;
      14: peer=68;
      34: peer=73;
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
  wire [4:0] iv [0:12], ir [0:12], ov [0:12], rd [0:12];
  wire [5*W-1:0] idata [0:12];
  wire [W-1:0] odata [0:12];
  wire [4:0] candidate_in [0:12], candidate_out [0:12];
  wire [4:0] input_ok [0:12], output_ok [0:12];
  wire [12:0] reached [0:13];
  wire [12:0] legal_switch;
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
  wire legal=&legal_switch;
  always @(posedge clk) begin
    cfg_applied<=0; cfg_rejected<=0;
    if(reset) active<=0;
    else if(cfg_valid && cfg_ready) begin
      if(legal) begin active<=cfg; cfg_applied<=1; end
      else cfg_rejected<=1;
    end
  end

  wire [35:0] grant;
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
        assign iv[s][p]=tx_valid[P] && tx_cs[4*P+:4]==s && !cfg_valid;
        assign idata[s][p*W+:W]=tx_data[P*W+:W];
        assign rd[s][p]=rx_ready[P] && grant[4*s+p];
      end else begin
        localparam T=(P-16)/5, Q=(P-16)%5;
        assign iv[s][p]=ov[T][Q];
        assign idata[s][p*W+:W]=odata[T];
        assign rd[s][p]=ir[T][Q];
      end
    end
  end
  // A stable receive slot in the parent NI captures the winning attachment.
  // Attachment arbitration uses static switch-ID priority.
  for(genvar n=0;n<16;n=n+1) begin: endpoint
    wire [35:0] incoming, selected_tx;
    wire [W-1:0] chosen_data [0:36];
    assign chosen_data[0]='0;
    assign rx_valid[n]=|incoming;
    assign tx_ready[n]=!cfg_valid && (|selected_tx);
    assign rx_data[n*W+:W]=chosen_data[36];
    for(genvar k=0;k<36;k=k+1) begin: attachment
      localparam S=k/4, P=k%4;
      if(peer(5*S+P)==n) begin: connected
        assign incoming[k]=ov[S][P];
        assign selected_tx[k]=ir[S][P] && tx_cs[4*n+:4]==S;
        if(k==0) assign grant[k]=incoming[k];
        else assign grant[k]=incoming[k] && !(|incoming[k-1:0]);
        assign chosen_data[k+1]=chosen_data[k] | (odata[S] & {W{grant[k]}});
      end else begin: disconnected
        assign incoming[k]=0;
        assign selected_tx[k]=0;
        assign chosen_data[k+1]=chosen_data[k];
      end
    end
  end
endmodule
