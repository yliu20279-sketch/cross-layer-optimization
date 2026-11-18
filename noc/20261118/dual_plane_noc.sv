module dual_plane_noc #(parameter W=256, ENHANCED=1)(
  input wire clk,reset,
  input wire cfg_valid,
  input wire [77:0] cfg,
  output wire cfg_ready,cfg_applied,cfg_rejected,
  input wire [16*(W+4)-1:0] tx_data,
  input wire [31:0] tx_kind,
  input wire [15:0] tx_valid,tx_last,use_circuit,
  input wire [63:0] tx_cs,
  input wire [15:0] response_storage_ready,response_tx_reserved,
  input wire [15:0] rx_ready,
  output wire [15:0] tx_ready,rx_valid,
  output wire [16*W-1:0] rx_data,
  output wire [31:0] rx_kind,
  output wire [15:0] rx_last
);
  localparam P=W+3,F=P+4,Q=F+5;
  wire [16*F-1:0] m_tx,c_tx,base_tx;
  wire [16*P-1:0] m_rx,c_rx,base_rx;
  wire [15:0] m_valid,m_ready,m_rx_valid,m_rx_ready,m_use;
  wire [15:0] c_valid,c_ready,c_rx_valid,c_rx_ready;
  wire [15:0] base_valid,base_ready,base_rx_valid,base_rx_ready;
  wire [63:0] m_cs;
  wire [15:0] circuit_pending;
  if(ENHANCED) begin: dual_plane
    wire [31:0] c_credit;
    wire network_cfg_ready;
    wire endpoints_drained=!(|circuit_pending);
    assign cfg_ready=network_cfg_ready && endpoints_drained;
    noc_paired #(.W(P),.ENHANCED(1)) moe(
      clk,reset,cfg_valid && endpoints_drained,cfg,network_cfg_ready,cfg_applied,cfg_rejected,
      m_tx,m_valid,m_rx_ready,m_use,m_cs,m_ready,m_rx_valid,m_rx);
    coherence_mesh #(.W(P)) coherence(
      clk,reset,c_tx,c_valid,c_rx_ready,c_credit,c_rx_valid,c_rx);
    for(genvar n=0;n<16;n=n+1) begin: credits
      assign c_ready[n]=c_tx[n*F+P-2] ? c_credit[2*n+1] : c_credit[2*n];
    end
    assign base_ready=0;
    assign base_rx_valid=0;
    assign base_rx=0;
  end else begin: single_plane
    noc_paired #(.W(P),.ENHANCED(0)) shared_mesh(
      clk,reset,cfg_valid,cfg,cfg_ready,cfg_applied,cfg_rejected,
      base_tx,base_valid,base_rx_ready,16'b0,64'b0,
      base_ready,base_rx_valid,base_rx);
    assign m_ready=0;
    assign m_rx_valid=0;
    assign m_rx=0;
    assign c_ready=0;
    assign c_rx_valid=0;
    assign c_rx=0;
  end

  for(genvar n=0;n<16;n=n+1) begin: ni
    // 00 MoE data, 01 MoE control, 10 GetS, 11 DataS.
    reg packet_active;
    reg [1:0] packet_kind;
    reg [3:0] packet_destination,packet_cs;
    reg packet_circuit;
    wire [1:0] kind=packet_active ? packet_kind : tx_kind[n*2+:2];
    wire [3:0] destination=packet_active ? packet_destination : tx_data[n*(W+4)+W+:4];
    wire circuit=packet_active ? packet_circuit : use_circuit[n];
    wire [3:0] cs=packet_active ? packet_cs : tx_cs[n*4+:4];
    wire [1:0] queue_id=kind[1] ? (kind[0] ? 2'd2 : 2'd1) : 2'd0;
    wire [Q-1:0] queued [0:2];
    wire [2:0] full,space,pop;
    wire reservation_ready=kind!=2'b10 ||
      (response_storage_ready[n] && response_tx_reserved[n]);
    wire admitted=reservation_ready &&
      !(ENHANCED && cfg_valid && !packet_active && circuit && !kind[1]);
    wire [Q-1:0] incoming={cs,circuit,destination,kind,tx_last[n],tx_data[n*(W+4)+:W]};
    assign tx_ready[n]=admitted && space[queue_id];
    for(genvar q=0;q<3;q=q+1) begin: transmit_queues
      localparam INDEX=q;
      wire [Q-1:0] data;
      assign queued[INDEX]=data;
      noc_slot #(.W(Q)) queue(clk,reset,incoming,
        tx_valid[n] && admitted && queue_id==INDEX,pop[INDEX],space[INDEX],data,full[INDEX]);
    end
    always @(posedge clk) begin
      if(reset) begin
        packet_active<=0;
        packet_kind<=0;
        packet_destination<=0;
        packet_cs<=0;
        packet_circuit<=0;
      end else if(tx_valid[n] && tx_ready[n]) begin
        packet_active<=!tx_last[n];
        if(!packet_active) begin
          packet_kind<=kind;
          packet_destination<=destination;
          packet_cs<=cs;
          packet_circuit<=circuit;
        end
      end
    end
    reg c_prefer_response,c_locked,c_locked_response;
    wire choose_response=c_locked ? c_locked_response :
      full[2] && (c_prefer_response || !full[1]);
    wire [Q-1:0] coherence=choose_response ? queued[2] : queued[1];
    assign c_tx[n*F+:F]=coherence[0+:F];
    assign c_valid[n]=full[1] || full[2];
    assign m_tx[n*F+:F]=queued[0][0+:F];
    assign m_use[n]=queued[0][F];
    assign m_cs[n*4+:4]=queued[0][F+1+:4];
    assign m_valid[n]=full[0];
    assign circuit_pending[n]=(full[0] && queued[0][F]) ||
      (packet_active && packet_circuit && !packet_kind[1]);
    reg baseline_prefer_c,baseline_locked,baseline_locked_c;
    wire baseline_choose_c=baseline_locked ? baseline_locked_c :
      (full[1] || full[2]) && (baseline_prefer_c || !full[0]);
    assign base_tx[n*F+:F]=baseline_choose_c ? coherence[0+:F] : queued[0][0+:F];
    assign base_valid[n]=|full;
    wire coherence_sent=ENHANCED ? c_valid[n] && c_ready[n] :
      base_valid[n] && base_ready[n] && baseline_choose_c;
    assign pop[0]=ENHANCED ? m_valid[n] && m_ready[n] :
      base_valid[n] && base_ready[n] && !baseline_choose_c;
    assign pop[1]=coherence_sent && !choose_response;
    assign pop[2]=coherence_sent && choose_response;
    always @(posedge clk) begin
      if(reset) begin
        c_prefer_response<=0;
        c_locked<=0;
        c_locked_response<=0;
        baseline_prefer_c<=0;
        baseline_locked<=0;
        baseline_locked_c<=0;
      end else begin
        if(base_valid[n] && !base_ready[n]) begin
          baseline_locked<=1;
          baseline_locked_c<=baseline_choose_c;
        end else baseline_locked<=0;
        if(c_valid[n] && !coherence_sent) begin
          c_locked<=1;
          c_locked_response<=choose_response;
        end else c_locked<=0;
        if(coherence_sent) c_prefer_response<=!choose_response;
        if(base_valid[n] && base_ready[n]) baseline_prefer_c<=!baseline_choose_c;
      end
    end
    // A single endpoint receive service arbitrates M and C fairly.
    reg prefer_c;
    wire select_c=c_rx_valid[n] && (prefer_c || !m_rx_valid[n]);
    wire [P-1:0] selected=ENHANCED ?
      (select_c ? c_rx[n*P+:P] : m_rx[n*P+:P]) : base_rx[n*P+:P];
    wire available=ENHANCED ? m_rx_valid[n] || c_rx_valid[n] : base_rx_valid[n];
    wire slot_ready;
    wire [P-1:0] received;
    assign m_rx_ready[n]=slot_ready && !select_c;
    assign c_rx_ready[n]=slot_ready && select_c;
    assign base_rx_ready[n]=slot_ready;
    noc_slot #(.W(P)) receive_slot(clk,reset,selected,available,rx_ready[n],
      slot_ready,received,rx_valid[n]);
    assign rx_data[n*W+:W]=received[0+:W];
    assign rx_last[n]=received[W];
    assign rx_kind[n*2+:2]=received[W+1+:2];
    always @(posedge clk)
      if(reset) prefer_c<=0;
      else if(slot_ready && available) prefer_c<=!select_c;
  end
endmodule
