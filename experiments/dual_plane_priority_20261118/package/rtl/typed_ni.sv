module typed_ni #(parameter int ID=0,DEPTH=2,CLIENTS=4,DUAL_MODE=1,TYPE_PRIORITY=0)(
 input logic clk,reset,
 input logic [CLIENTS-1:0] client_valid,client_first,
 input logic [3:0] client_op[CLIENTS],client_dst[CLIENTS],client_cs[CLIENTS],
 input logic [31:0] client_id[CLIENTS],client_txn[CLIENTS],
 input logic [15:0] client_bytes[CLIENTS],client_version[CLIENTS],
 input logic [255:0] client_data[CLIENTS],input logic [CLIENTS-1:0] client_circuit,
 output logic [CLIENTS-1:0] client_ready,
 input logic pause_cs,input logic [15:0] installed_version,
 input logic retire_valid,input logic [31:0] retire_txn,
 output logic pause_ack,cs_busy,source_busy,output logic [31:0] errors,
 output logic m_valid,c_valid,cs_valid,
 output noc_pkg::flit_t m_flit,c_flit,cs_flit,output logic [3:0] cs_attachment,
 input logic [3:0] m_credit,c_credit,input logic cs_ready,
 input logic [2:0] rx_valid,input noc_pkg::flit_t rx_flit[3],
 output logic [3:0] rx_credit[3],
 output logic ep_valid,output noc_pkg::flit_t ep_flit,input logic [3:0] ep_ready,
 output logic ctl_valid,output noc_pkg::flit_t ctl_flit,input logic ctl_ready,
 output logic [3:0] pending_dst[4]
);
 // Node coordinates are fixed wires; share one core implementation across tiles.
 typed_ni_core #(.DEPTH(DEPTH),.CLIENTS(CLIENTS),.DUAL_MODE(DUAL_MODE),.TYPE_PRIORITY(TYPE_PRIORITY)) impl(.node_id(4'(ID)),.*);
endmodule

module typed_ni_core #(parameter int DEPTH=2,CLIENTS=4,DUAL_MODE=1,TYPE_PRIORITY=0)(
 input logic [3:0] node_id,
 input logic clk,reset,
 input logic [CLIENTS-1:0] client_valid,client_first,
 input logic [3:0] client_op[CLIENTS],client_dst[CLIENTS],client_cs[CLIENTS],
 input logic [31:0] client_id[CLIENTS],client_txn[CLIENTS],
 input logic [15:0] client_bytes[CLIENTS],client_version[CLIENTS],
 input logic [255:0] client_data[CLIENTS],input logic [CLIENTS-1:0] client_circuit,
 output logic [CLIENTS-1:0] client_ready,
 input logic pause_cs,input logic [15:0] installed_version,
 input logic retire_valid,input logic [31:0] retire_txn,
 output logic pause_ack,cs_busy,source_busy,output logic [31:0] errors,
 output logic m_valid,c_valid,cs_valid,
 output noc_pkg::flit_t m_flit,c_flit,cs_flit,output logic [3:0] cs_attachment,
 input logic [3:0] m_credit,c_credit,input logic cs_ready,
 input logic [2:0] rx_valid,input noc_pkg::flit_t rx_flit[3],
 output logic [3:0] rx_credit[3],
 output logic ep_valid,output noc_pkg::flit_t ep_flit,input logic [3:0] ep_ready,
 output logic ctl_valid,output noc_pkg::flit_t ctl_flit,input logic ctl_ready,
 output logic [3:0] pending_dst[4]
);
 import noc_pkg::*;
 localparam int SW=FW+5;
 logic [SW-1:0] sf[4],sd[4];logic se[4],sfull[4],spush[4],spop[4];
 logic [$clog2(DEPTH+1)-1:0] sc[4];
 logic [15:0] remaining[CLIENTS];logic [1:0] cls[CLIENTS];
 logic admitted_cs[CLIENTS],packet[CLIENTS];logic [3:0] attach[CLIENTS];
 logic [CLIENTS-1:0] bad;
 logic [1:0] tx_first;logic [$clog2(CLIENTS)-1:0] source_first[4],source_owner[4];logic source_locked[4];
 logic [1:0] rx_first,rx_path_first[4],rx_owner[4];logic rx_locked[4];
 flit_t rf[3][4];logic rempty[3][4],rfull[3][4],rpush[3][4],rpop[3][4];
 logic [$clog2(DEPTH+1)-1:0] rc[3][4];
 int tx_selected,rx_selected,rx_selected_v;
 logic [3:0] cs_packets;
 logic [15:0] request_valid,response_started;logic [31:0] request_txn[16];logic [3:0] request_peer[16];
 int free_request,retire_slot,reply_slot;logic reply_bad,discard_response;int error_events;
 always_comb begin
  free_request=-1;retire_slot=-1;
  for(int k=0;k<16;k++)begin
   if(!request_valid[k]&&free_request<0)free_request=k;
   if(request_valid[k]&&request_txn[k]==retire_txn)retire_slot=k;
  end
 end
 logic [3:0] send_dst[4];
 assign cs_attachment=sf[0][FW+:4];
 for(genvar v=0;v<4;v++)assign pending_dst[v]=sf[v][257]?sf[v][251:248]:send_dst[v];
 always_comb begin
  cs_busy=cs_packets!=0;source_busy=0;
  for(int v=0;v<4;v++)source_busy|=!se[v];
  for(int c=0;c<CLIENTS;c++)begin cs_busy|=packet[c]&&admitted_cs[c];source_busy|=packet[c];end
 end
 for(genvar v=0;v<4;v++)begin:src
  noc_fifo #(.WIDTH(SW),.DEPTH(DEPTH)) f(clk,reset,spush[v],spop[v],sd[v],sf[v],sfull[v],se[v],sc[v]);
 end
 for(genvar path=0;path<3;path++)for(genvar v=0;v<4;v++)begin:recv
  localparam bit USED=DUAL_MODE==1?(path==0?(v==0||v==3):path==1?(v==1||v==2):v==0):DUAL_MODE==0?path==0:path<2;
  if(USED)begin
   assign rx_credit[path][v]=!reset&&!rfull[path][v];
   assign rpush[path][v]=rx_valid[path]&&rx_flit[path][259:258]==v&&rx_credit[path][v];
   noc_fifo #(.WIDTH(FW),.DEPTH(DEPTH)) f(clk,reset,rpush[path][v],rpop[path][v],rx_flit[path],rf[path][v],rfull[path][v],rempty[path][v],rc[path][v]);
  end else begin assign rx_credit[path][v]=0;assign rpush[path][v]=0;assign rf[path][v]='0;assign rfull[path][v]=1;assign rempty[path][v]=1;assign rc[path][v]=0;end
 end
 always_comb begin
  client_ready=0;bad=0;
  for(int v=0;v<4;v++)begin
   spush[v]=0;sd[v]='0;
   for(int ct=0;ct<CLIENTS;ct++)begin
    automatic int c=source_locked[v]?source_owner[v]:(source_first[v]+ct)%CLIENTS;
    automatic int cl=packet[c]?int'(cls[c]):vn_of(client_op[c]);
    automatic logic route=packet[c]?admitted_cs[c]:client_circuit[c]&&client_op[c]==MOE_DATA;
    automatic logic blocked=!packet[c]&&route&&(pause_cs||client_version[c]!=installed_version);
    automatic logic duplicate_request=0;
    automatic logic [255:0] data;
    automatic logic tail;
    data=client_data[c];tail=remaining[c]<=32;
    if(!packet[c])begin
     data=header(client_op[c],node_id,client_dst[c],client_id[c],client_txn[c],client_bytes[c]);
     if(client_op[c]==CONFIG||client_op[c]==CONFIG_ACK)data[163:0]=client_data[c][163:0];
     if(client_op[c]==GETS)data[63:0]=client_data[c][63:0];
     if(route)data[15:0]=client_version[c];
     tail=client_bytes[c]==0;
    end
    if(client_valid[c]&&cl<0)begin client_ready[c]=!reset;bad[c]=!reset;end
    for(int k=0;k<16;k++)duplicate_request|=request_valid[k]&&request_txn[k]==client_txn[c];
    if(!packet[c]&&client_op[c]==GETS)begin
     blocked|=free_request<0;
     if(client_valid[c]&&(duplicate_request||client_bytes[c]!=0))begin client_ready[c]=!reset;bad[c]=!reset;blocked=1;end
    end
    if(client_valid[c]&&cl==v&&!sfull[v]&&!spush[v]&&!blocked&&!reset)begin
     client_ready[c]=1;spush[v]=1;
     sd[v]={route,(packet[c]?attach[c]:client_cs[c]),frame(data,v,!packet[c],tail)};
    end
   end
  end
  m_valid=0;c_valid=0;cs_valid=0;m_flit='0;c_flit='0;cs_flit='0;tx_selected=-1;
  for(int v=0;v<4;v++)spop[v]=0;
  for(int vt=0;vt<4;vt++)begin
   automatic int v=TYPE_PRIORITY?3-vt:(tx_first+vt)%4;
   automatic logic circuit=sf[v][FW+4];
   automatic logic ready=circuit?cs_ready:((v==0||v==3)?m_credit[v]:c_credit[v]);
   if(!se[v]&&ready&&tx_selected<0&&!reset)begin
    tx_selected=v;spop[v]=1;
    if(circuit)begin cs_valid=1;cs_flit=sf[v][FW-1:0];end
    else if(v==0||v==3)begin m_valid=1;m_flit=sf[v][FW-1:0];end
    else begin c_valid=1;c_flit=sf[v][FW-1:0];end
   end
  end
  ep_valid=0;ep_flit='0;ctl_valid=0;ctl_flit='0;rx_selected=-1;rx_selected_v=-1;reply_slot=-1;reply_bad=0;
  for(int p=0;p<3;p++)for(int v=0;v<4;v++)rpop[p][v]=0;
  for(int vt=0;vt<4;vt++)begin
   automatic int v=TYPE_PRIORITY?3-vt:(rx_first+vt)%4;
   for(int pt=0;pt<3;pt++)begin
    automatic int p=rx_locked[v]?rx_owner[v]:(rx_path_first[v]+pt)%3;
    automatic logic control=rf[p][v][257]&&(rf[p][v][255:252]==CONFIG||rf[p][v][255:252]==CONFIG_ACK);
    automatic int matched=-1;
    automatic logic response_head=rf[p][v][257]&&v==2;
    automatic logic invalid_response=0;
    for(int k=0;k<16;k++)if(request_valid[k]&&!response_started[k]&&request_txn[k]==rf[p][v][195:164]&&request_peer[k]==rf[p][v][247:244])matched=k;
    invalid_response=response_head&&(matched<0||rf[p][v][255:252]!=DATAS||rf[p][v][211:196]!=64);
    if(rx_selected<0&&!rempty[p][v]&&(control?ctl_ready:invalid_response||v==2&&discard_response||ep_ready[v])&&!reset)begin
     rx_selected=p;rx_selected_v=v;rpop[p][v]=1;
     if(v==2)begin reply_slot=matched;reply_bad=invalid_response;end
     if(control)begin ctl_valid=1;ctl_flit=rf[p][v];end
     else if(!(invalid_response||v==2&&discard_response))begin ep_valid=1;ep_flit=rf[p][v];end
    end
   end
  end
  error_events=$countones(bad)+int'(reply_bad)+int'(retire_valid&&(retire_slot<0||!response_started[retire_slot]));
 end
 always_ff @(posedge clk)begin
  if(reset)begin
   errors<=0;pause_ack<=0;tx_first<=0;rx_first<=0;cs_packets<=0;request_valid<=0;response_started<=0;discard_response<=0;
   for(int k=0;k<16;k++)begin request_txn[k]<=0;request_peer[k]<=0;end
   for(int c=0;c<CLIENTS;c++)begin remaining[c]<=0;cls[c]<=0;packet[c]<=0;admitted_cs[c]<=0;attach[c]<=0;end
   for(int v=0;v<4;v++)begin source_first[v]<=0;source_owner[v]<=0;source_locked[v]<=0;rx_path_first[v]<=0;rx_owner[v]<=0;rx_locked[v]<=0;send_dst[v]<=0;end
  end else begin
   pause_ack<=pause_cs;
   if(error_events)errors<=errors+32'(error_events);
   if(retire_valid&&retire_slot>=0&&response_started[retire_slot])begin request_valid[retire_slot]<=0;response_started[retire_slot]<=0;end
   for(int c=0;c<CLIENTS;c++)if(client_ready[c]&&client_valid[c]&&!bad[c])begin
    automatic int v=packet[c]?int'(cls[c]):vn_of(client_op[c]);
    assert(client_first[c]==!packet[c])else $fatal(1,"client packet framing");
    if(!packet[c])begin
     cls[c]<=2'(v);remaining[c]<=client_bytes[c];packet[c]<=client_bytes[c]!=0;
     admitted_cs[c]<=client_circuit[c]&&client_op[c]==MOE_DATA;attach[c]<=client_cs[c];
     if(client_op[c]==GETS)begin
      assert(free_request>=0)else $fatal(1,"GetS without reserved response context");
      request_valid[free_request]<=1;response_started[free_request]<=0;
      request_txn[free_request]<=client_txn[c];request_peer[free_request]<=client_dst[c];
     end
    end else begin remaining[c]<=remaining[c]<=32?0:remaining[c]-32;packet[c]<=remaining[c]>32;end
    if((!packet[c]&&client_bytes[c]==0)||(packet[c]&&remaining[c]<=32))begin
     source_locked[v]<=0;source_first[v]<=$clog2(CLIENTS)'((c+1)%CLIENTS);
    end else begin source_locked[v]<=1;source_owner[v]<=$clog2(CLIENTS)'(c);end
   end
   // Count CS packet headers enqueued and packet tails admitted to the fabric.
   case({spush[0]&&sd[0][FW+4]&&sd[0][257],spop[0]&&sf[0][FW+4]&&sf[0][256]})
    2'b10:cs_packets<=cs_packets+1'b1;2'b01:cs_packets<=cs_packets-1'b1;default:;
   endcase
   if(tx_selected>=0)begin
    tx_first<=tx_selected==3?0:2'(tx_selected+1);
    if(sf[tx_selected][257])send_dst[tx_selected]<=sf[tx_selected][251:248];
   end
   if(rx_selected>=0)begin
    if(rx_selected_v==2)begin
     if(rf[rx_selected][2][257])begin
      discard_response<=reply_bad;
      if(!reply_bad)response_started[reply_slot]<=1;
     end
     if(rf[rx_selected][2][256])discard_response<=0;
    end
    rx_first<=rx_selected_v==3?0:2'(rx_selected_v+1);
    if(rf[rx_selected][rx_selected_v][256])begin rx_locked[rx_selected_v]<=0;rx_path_first[rx_selected_v]<=2'((rx_selected+1)%3);end
    else begin rx_locked[rx_selected_v]<=1;rx_owner[rx_selected_v]<=2'(rx_selected);end
   end
  end
 end
endmodule
