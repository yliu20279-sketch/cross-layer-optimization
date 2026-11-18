module experiment_top #(parameter int DUAL=1,DEPTH=2,TYPE_PRIORITY=0)(
 input logic clk,reset,input logic [1:0] hiband_mode,output logic hiband_mode_ready,
 input logic [2:0] client_valid[16],client_first[16],client_circuit[16],
 input logic [3:0] client_op[16][3],client_dst[16][3],client_cs[16][3],
 input logic [31:0] client_id[16][3],client_txn[16][3],
 input logic [15:0] client_bytes[16][3],client_version[16][3],
 input logic [255:0] client_data[16][3],output logic [2:0] client_ready[16],
 input logic [15:0] retire_valid,input logic [31:0] retire_txn[16],
 output logic [15:0] rx_valid,output noc_pkg::flit_t rx_flit[16],input logic [3:0] rx_ready[16],
 input logic host_valid,input logic [3:0] host_dst,host_target,
 input logic [2:0] host_action,input logic [5:0] host_state,
 input logic [15:0] host_version,input logic [31:0] host_id,output logic host_ready,
 input logic seq_start,input logic [77:0] seq_plan,input logic [15:0] seq_version,
 output logic seq_ready,seq_done,seq_error,
 output logic ack_valid,ack_ok,input logic ack_ready,
 output logic [31:0] ack_id,output logic [2:0] ack_action,output logic [15:0] ack_version,
 output logic [15:0] paused,pause_ack,output logic cs_idle,network_idle,
 output logic [15:0] active_version,installed_version[16],
 output logic [31:0] protocol_errors,configuration_errors,
 output logic [63:0] m_flits,c_flits,cs_flits,config_flits,
 output logic [15:0] egress_valid,output noc_pkg::flit_t egress_flit[16],output logic [1:0] egress_path[16]
);
 import noc_pkg::*;
 logic [3:0] cv[16],cf[16],cc[16],cr[16];
 logic [3:0] op[16][4],dst[16][4],attachment[16][4];
 logic [31:0] pid[16][4],txn[16][4];logic [15:0] bytes[16][4],vers[16][4];logic [255:0] data[16][4];
 logic [15:0] mv,cvnet,sv,mrv,crv,srv,mbusyNI,sbusyNI;
 flit_t mf[16],cfl[16],sf[16],mrf[16],crf[16],srf[16],mesh_tx[16];
 logic [3:0] mc[16],ccc[16],mrc[16],crc[16],nirc[16][3],global_credit[16],local_credit[16];
 logic [3:0] pending_dst[16][4];logic [15:0] local_tx_valid;flit_t local_tx[16];
 logic [2:0] global_lanes,local_lanes;
 logic [1:0] active_hiband_mode;
 assign hiband_mode_ready=active_hiband_mode==hiband_mode;
 always_ff @(posedge clk)begin
  if(reset)active_hiband_mode<=0;
  else if(DUAL==2&&network_idle)active_hiband_mode<=hiband_mode;
 end
 logic [3:0] sc[16];logic [15:0] sr,srr,mesh_valid;
 logic [2:0] niv[16];flit_t nif[16][3];
 logic [15:0] ctl_valid;flit_t ctl_flit[16];logic [15:0] ctl_ready;
 logic [31:0] ni_errors[16];logic mesh_busy,cmesh_busy,fabric_busy,fabric_ready,fabric_legal,commit;
 logic [77:0] shadow;logic [12:0] stage_valid;logic [15:0] stage_version[13];
 logic [15:0] ack_pending;logic [31:0] response_id[16],response_status[16];logic [163:0] response_fields[16];
 logic host_busy,all_installed,all_staged;
 logic sequence_busy,sequence_ready,command_valid,command_ready;
 logic [3:0] command_dst,command_target;logic [2:0] command_action;
 logic [5:0] command_state;logic [15:0] command_version;logic [31:0] command_id;
 logic internal_ready,request_valid;logic [3:0] request_dst,request_target;logic [2:0] request_action;
 logic [5:0] request_state;logic [15:0] request_version;logic [31:0] request_id;
 assign seq_ready=sequence_ready&&!host_busy&&!host_valid;
 assign request_valid=sequence_busy?command_valid:host_valid;
 assign request_dst=sequence_busy?command_dst:host_dst;assign request_target=sequence_busy?command_target:host_target;
 assign request_action=sequence_busy?command_action:host_action;assign request_state=sequence_busy?command_state:host_state;
 assign request_version=sequence_busy?command_version:host_version;assign request_id=sequence_busy?command_id:host_id;
 assign command_ready=sequence_busy&&internal_ready;
 configuration_sequencer sequencer(clk,reset,seq_start&&seq_ready,seq_plan,seq_version,sequence_ready,sequence_busy,seq_done,seq_error,
  cs_idle,pause_ack,command_valid,command_ready,command_dst,command_target,command_action,command_state,command_version,command_id,
  ack_valid&&ack_ready,ack_ok,ack_id);
 function automatic int owner_of(input int c);
  if(c<9)return 4*(c/3)+c%3;
  case(c)9:return 0;10:return 2;11:return 8;12:return 10;default:return -1;endcase
 endfunction
 function automatic logic [31:0] status(input int n,input flit_t f);
  automatic int action=f[163:161],target=f[160:157];
  automatic logic [15:0] version=f[150:135];
  case(action)
   0:return 0;
   1:begin
    if(target>12||owner_of(target)!=n)return 3;
    if(!(&paused)||!(&pause_ack))return 1;
    if(!cs_idle)return 2;
    if(version!=active_version+16'd1)return 4;
    return 0;
   end
   2:begin
    if(n!=0)return 3;
    if(!(&paused)||!(&pause_ack))return 1;
    if(!cs_idle)return 2;
    if(!all_staged||version!=active_version+16'd1)return 4;
    if(!fabric_legal)return 5;
    return 0;
   end
   3:if(version!=active_version)return 4;else if(!paused[n])return 1;else return 0;
   4:if(version!=active_version||!all_installed)return 4;else return 0;
   default:return 6;
  endcase
 endfunction
 always_comb begin
  all_installed=1;all_staged=&stage_valid;protocol_errors=0;
  for(int n=0;n<16;n++)begin all_installed&=installed_version[n]==active_version;protocol_errors+=ni_errors[n];end
  for(int s=0;s<13;s++)all_staged&=stage_version[s]==active_version+16'd1;
  cs_idle=!fabric_busy&&!(|sbusyNI);
  network_idle=!mesh_busy&&!cmesh_busy&&cs_idle&&!(|mbusyNI)&&!(|ack_pending)&&!host_busy&&!sequence_busy;
 end
 for(genvar n=0;n<16;n++)begin:control_credit
  assign ctl_ready[n]=!ack_pending[n]&&(n!=0||ack_ready);
  assign client_ready[n]=cr[n][2:0];
 end
 assign internal_ready=!ack_pending[0]&&!host_busy&&cr[0][3];
 assign host_ready=!sequence_busy&&internal_ready;
 always_comb begin
  ack_valid=0;ack_ok=0;ack_id=0;ack_action=0;ack_version=0;commit=0;
  for(int n=0;n<16;n++)begin
   if(ctl_valid[n]&&ctl_flit[n][255:252]==CONFIG_ACK&&n==0)begin
    ack_valid=1;ack_id=ctl_flit[n][243:212];ack_ok=ctl_flit[n][195:164]==0;
    ack_action=ctl_flit[n][163:161];ack_version=ctl_flit[n][150:135];
   end
   if(ctl_valid[n]&&ctl_ready[n]&&ctl_flit[n][255:252]==CONFIG&&ctl_flit[n][163:161]==2&&status(n,ctl_flit[n])==0)commit=1;
  end
 end
 always_comb begin
  for(int n=0;n<16;n++)begin
   cv[n]=0;cf[n]=0;cc[n]=0;
   for(int c=0;c<3;c++)begin
    cv[n][c]=client_valid[n][c];cf[n][c]=client_first[n][c];cc[n][c]=client_circuit[n][c];
    op[n][c]=client_op[n][c];dst[n][c]=client_dst[n][c];attachment[n][c]=client_cs[n][c];
    pid[n][c]=client_id[n][c];txn[n][c]=client_txn[n][c];bytes[n][c]=client_bytes[n][c];vers[n][c]=client_version[n][c];data[n][c]=client_data[n][c];
   end
   cv[n][3]=ack_pending[n];cf[n][3]=1;cc[n][3]=0;op[n][3]=CONFIG_ACK;dst[n][3]=0;attachment[n][3]=0;
   pid[n][3]=response_id[n];txn[n][3]=response_status[n];bytes[n][3]=0;vers[n][3]=0;data[n][3]='0;data[n][3][163:0]=response_fields[n];
   if(n==0&&!ack_pending[n]&&!host_busy)begin
    cv[n][3]=request_valid;op[n][3]=CONFIG;dst[n][3]=request_dst;pid[n][3]=request_id;txn[n][3]=0;
    data[n][3][163:161]=request_action;data[n][3][160:157]=request_target;
    data[n][3][156:151]=request_state;data[n][3][150:135]=request_version;
   end
  end
 end
 always_comb begin
  case(active_hiband_mode)
   0:begin global_lanes=4;local_lanes=0;end
   1:begin global_lanes=2;local_lanes=2;end
   2:begin global_lanes=1;local_lanes=3;end
   default:begin global_lanes=0;local_lanes=4;end
  endcase
 end
 function automatic logic near(input int n,input logic [3:0] target);
  automatic int dx=(n%4)-int'(target[1:0]),dy=n/4-int'(target[3:2]);
  // Four contiguous ranks form an NA, matching the published trace groups.
  return (dx<0?-dx:dx)+(dy<0?-dy:dy)<=1&&n/4==int'(target[3:2]);
 endfunction
 if(DUAL==2)begin:hiband
  wire [15:0] hv[2],hrv[2];flit_t hf[2][16],hrf[2][16];wire [3:0] hc[2][16],hrc[2][16];
  assign hv[0]=mesh_valid;assign hv[1]=local_tx_valid;assign mrv=hrv[0];assign crv=hrv[1];assign cmesh_busy=0;
  for(genvar n=0;n<16;n++)begin
   assign hf[0][n]=mesh_tx[n];assign hf[1][n]=local_tx[n];assign mrf[n]=hrf[0][n];assign crf[n]=hrf[1][n];
   assign global_credit[n]=hc[0][n];assign local_credit[n]=hc[1][n];assign hrc[0][n]=mrc[n];assign hrc[1][n]=crc[n];
  end
  hiband_fabric #(.DEPTH(DEPTH),.TYPE_PRIORITY(TYPE_PRIORITY)) fabric(clk,reset,global_lanes,hv,hf,hc,hrv,hrf,hrc,mesh_busy);
  for(genvar n=0;n<16;n++)for(genvar v=0;v<4;v++)begin:credit
   assign mc[n][v]=near(n,pending_dst[n][v])&&local_lanes!=0?local_credit[n][v]:global_credit[n][v];
   assign ccc[n][v]=mc[n][v];
  end
 end else begin:normal_m
  typed_mesh #(.DEPTH(DEPTH),.ACTIVE_VN(DUAL==1?9:15),.TYPE_PRIORITY(TYPE_PRIORITY)) m(clk,reset,mesh_valid,mesh_tx,mc,mrv,mrf,mrc,mesh_busy,3'd4);
 end
 if(DUAL==1)begin:c_plane
  typed_mesh #(.DEPTH(DEPTH),.ACTIVE_VN(6),.TYPE_PRIORITY(TYPE_PRIORITY)) c(clk,reset,cvnet,cfl,ccc,crv,crf,crc,cmesh_busy,3'd4);
 end else begin:shared
  if(DUAL==0)begin
   assign crv=0;assign cmesh_busy=0;
   for(genvar n=0;n<16;n++)begin assign ccc[n]=mc[n];assign crf[n]='0;end
  end
 end
 if(DUAL==1)begin:with_cs
  cs_fabric cs(clk,reset,commit,shadow,fabric_legal,fabric_ready,fabric_busy,sv,sf,sc,sr,srv,srf,srr);
 end else begin:no_cs
  assign fabric_legal=0;assign fabric_ready=1;assign fabric_busy=0;assign sr=0;assign srv=0;
  for(genvar n=0;n<16;n++)assign srf[n]='0;
 end
 for(genvar n=0;n<16;n++)begin:node
  assign egress_valid[n]=mv[n]||cvnet[n]||sv[n];
  assign egress_flit[n]=mv[n]?mf[n]:cvnet[n]?cfl[n]:sf[n];
  assign egress_path[n]=sv[n]?2:cvnet[n]&&DUAL==1?1:0;
  wire local_route=DUAL==2&&local_lanes!=0&&near(n,pending_dst[n][mv[n]?int'(mf[n][259:258]):int'(cfl[n][259:258])]);
  assign mesh_valid[n]=(mv[n]||(DUAL!=1&&cvnet[n]))&&!local_route;
  assign local_tx_valid[n]=(mv[n]||cvnet[n])&&local_route;
  assign mesh_tx[n]=mv[n]?mf[n]:cfl[n];assign local_tx[n]=mesh_tx[n];
  assign niv[n]={srv[n],crv[n],mrv[n]};assign nif[n][0]=mrf[n];assign nif[n][1]=crf[n];assign nif[n][2]=srf[n];
  assign mrc[n]=nirc[n][0];assign crc[n]=nirc[n][1];assign srr[n]=nirc[n][2][0];
  typed_ni #(.ID(n),.DEPTH(DEPTH),.DUAL_MODE(DUAL),.TYPE_PRIORITY(TYPE_PRIORITY)) ni(clk,reset,cv[n],cf[n],op[n],dst[n],attachment[n],pid[n],txn[n],bytes[n],vers[n],data[n],cc[n],cr[n],
   paused[n],installed_version[n],retire_valid[n],retire_txn[n],pause_ack[n],sbusyNI[n],mbusyNI[n],ni_errors[n],
   mv[n],cvnet[n],sv[n],mf[n],cfl[n],sf[n],sc[n],mc[n],ccc[n],sr[n],niv[n],nif[n],nirc[n],
   rx_valid[n],rx_flit[n],rx_ready[n],ctl_valid[n],ctl_flit[n],ctl_ready[n],pending_dst[n]);
 end
 always_ff @(posedge clk)begin
  if(reset)begin
   paused<=0;active_version<=0;shadow<=0;stage_valid<=0;ack_pending<=0;host_busy<=0;configuration_errors<=0;
   m_flits<=0;c_flits<=0;cs_flits<=0;config_flits<=0;
   for(int n=0;n<16;n++)begin installed_version[n]<=0;response_id[n]<=0;response_status[n]<=0;response_fields[n]<=0;end
   for(int s=0;s<13;s++)stage_version[s]<=0;
  end else begin
   if(request_valid&&internal_ready)host_busy<=1;
   if(ack_valid&&ack_ready)host_busy<=0;
   m_flits<=m_flits+$countones(mv)+(DUAL!=1?$countones(cvnet):0);
   c_flits<=c_flits+(DUAL==1?$countones(cvnet):0);cs_flits<=cs_flits+$countones(sv);
   for(int n=0;n<16;n++)begin
    if(cv[n][3]&&cr[n][3]&&ack_pending[n])ack_pending[n]<=0;
    if(ctl_valid[n]&&ctl_ready[n]&&ctl_flit[n][255:252]==CONFIG)begin
     automatic int action=ctl_flit[n][163:161],target=ctl_flit[n][160:157];
     automatic logic [15:0] version=ctl_flit[n][150:135];
     automatic logic [31:0] result=status(n,ctl_flit[n]);
     assert(ctl_flit[n][257:256]==2'b11)else $fatal(1,"configuration command must be a single flit");
     ack_pending[n]<=1;response_id[n]<=ctl_flit[n][243:212];response_status[n]<=result;response_fields[n]<=ctl_flit[n][163:0];
     config_flits<=config_flits+1;
     if(result!=0)configuration_errors<=configuration_errors+1;
     else case(action)
      0:paused[n]<=1;
      1:begin shadow[target*6+:6]<=ctl_flit[n][156:151];stage_valid[target]<=1;stage_version[target]<=version;end
      2:begin active_version<=version;stage_valid<=0;end
      3:installed_version[n]<=version;
      4:paused[n]<=0;
      default:;
     endcase
    end
   end
  end
 end
endmodule
