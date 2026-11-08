`timescale 1ns/1ps
// Local fixture: gateway node 2 -> CS1 (NE->SW) -> NI of node 5.
// No Mesh routers or global drain controller are modeled in this fixture.
module tb_integration;
  reg clk=0;always #5 clk=~clk;
  reg rst_n=0;
  reg [2:0] req=0,rsp_ready=7;
  reg [255:0] flit[0:2];
  wire [2:0] ready,rsp;
  wire [2:0] status[0:2];
  reg frozen=1,drained=1;
  wire [11:0] cs_cfg;
  wire [4:0] tx_cfg,rx_cfg;
  ni_config_agent #(.NODE_ID(1)) owner(.clk(clk),.rst_n(rst_n),.req_valid(req[0]),.req_ready(ready[0]),.req_flit(flit[0]),.aux_frozen(frozen),.global_drained(drained),.rsp_valid(rsp[0]),.rsp_ready(rsp_ready[0]),.rsp_status(status[0]),.cs_cfg(cs_cfg));
  ni_config_agent #(.NODE_ID(2)) tx_control(.clk(clk),.rst_n(rst_n),.req_valid(req[1]),.req_ready(ready[1]),.req_flit(flit[1]),.aux_frozen(frozen),.global_drained(drained),.rsp_valid(rsp[1]),.rsp_ready(rsp_ready[1]),.rsp_status(status[1]),.tx_cfg(tx_cfg));
  ni_config_agent #(.NODE_ID(5)) rx_control(.clk(clk),.rst_n(rst_n),.req_valid(req[2]),.req_ready(ready[2]),.req_flit(flit[2]),.aux_frozen(frozen),.global_drained(drained),.rsp_valid(rsp[2]),.rsp_ready(rsp_ready[2]),.rsp_status(status[2]),.rx_cfg(rx_cfg));
  reg [255:0] src_data=0;
  reg src_valid=0;
  wire src_credit;
  wire [9*256-1:0] tx_branches;
  wire [8:0] tx_valid,rx_credit_branches;
  wire [1023:0] sw_in,sw_out;
  wire [3:0] sw_vin,sw_vout,sw_crin,sw_crout;
  wire sw_legal;
  wire [255:0] aux_data;
  wire aux_valid,aux_credit,aux_ready;
  node_selectors #(.NODE_ID(2)) tx_select(.tx_cfg(tx_cfg),.rx_cfg(5'd0),.tx_data(src_data),.tx_valid(src_valid),.cs_credit({7'd0,sw_crout[1],1'b0}),.to_cs_data(tx_branches),.to_cs_valid(tx_valid),.tx_credit(src_credit),.from_cs_data(2304'd0),.from_cs_valid(9'd0),.rx_credit(1'b0));
  assign sw_in={512'd0,tx_branches[256+:256],256'd0};
  assign sw_vin={2'd0,tx_valid[1],1'b0};
  assign sw_crin={1'b0,rx_credit_branches[1],2'd0};
  terminal_switch sw(cs_cfg,sw_in,sw_vin,sw_crin,sw_out,sw_vout,sw_crout,sw_legal);
  node_selectors #(.NODE_ID(5)) rx_select(.tx_cfg(5'd0),.rx_cfg(rx_cfg),.tx_data(256'd0),.tx_valid(1'b0),.cs_credit(9'd0),.from_cs_data({1792'd0,sw_out[512+:256],256'd0}),.from_cs_valid({7'd0,sw_vout[2],1'b0}),.rx_credit(aux_credit),.rx_data(aux_data),.rx_valid(aux_valid),.to_cs_credit(rx_credit_branches));
  reg [255:0] mesh_data=0;
  reg mesh_valid=0,write_ready=0;
  wire mesh_ready,write_valid,write_aux,aux_empty;
  wire [255:0] write_data;
  wire [31:0] mc,ac;
  ni_receive rx_queues(clk,rst_n,mesh_data,aux_data,mesh_valid,aux_valid,mesh_ready,aux_ready,aux_credit,write_data,write_valid,write_aux,write_ready,aux_empty,mc,ac);
  function [255:0] payload(input integer stream,id);
    reg [31:0] word;
    begin word=(stream==1?32'ha0000000:32'hb0000000)+id;payload={8{word}};end
  endfunction
  task command(input integer agent,kind,ep,state,op,expect_status);
    integer nodeid,target;
    reg [47:0] c;
    begin
      case(agent) 0:nodeid=1;1:nodeid=2;2:nodeid=5;endcase
      target=kind==0?1:nodeid;
      c=(48'd7<<45)|(nodeid*48'd1<<41)|(op*48'd1<<39)|(kind*48'd1<<37)|(target*48'd1<<33)|(ep*48'd1<<17)|(state*48'd1<<5);
      @(negedge clk);flit[agent]={c,208'd0};req[agent]=1;
      @(posedge clk);#1;
      if(!rsp[agent] || status[agent]!==expect_status[2:0]) $fatal(1,"integration configuration failed agent=%0d status=%0d",agent,status[agent]);
      @(negedge clk);req[agent]=0;
      @(posedge clk);#1;
    end
  endtask
  integer sent,msent,received,mreceived,credits,cy,round;
  integer credit_pulses,total_credits=0,total_aux=0,total_mesh=0;
  task stream_round(input integer num);
    begin
      sent=0;msent=0;received=0;mreceived=0;credits=4;credit_pulses=0;cy=0;
      while(sent<256 || received<256 || mreceived<256 || credits!=4) begin
        @(negedge clk);
        src_valid=(sent<256 && credits>0);src_data=payload(1,sent+num*1000);
        mesh_valid=(msent<256);mesh_data=payload(2,msent+num*1000);
        write_ready=(cy%13>=5);#1;
        if(aux_valid && !aux_ready) $fatal(1,"credit overflow");
        if(write_valid && write_ready) begin
          if(write_aux) begin
            if(write_data!==payload(1,received+num*1000)) $fatal(1,"aux loss/reorder");
            received=received+1;
          end else begin
            if(write_data!==payload(2,mreceived+num*1000)) $fatal(1,"mesh loss/reorder");
            mreceived=mreceived+1;
          end
        end
        if(src_credit) credit_pulses=credit_pulses+1;
        credits=credits+src_credit-src_valid;
        if(credits<0 || credits>4) $fatal(1,"credit conservation");
        if(src_valid) sent=sent+1;
        if(mesh_valid && mesh_ready) msent=msent+1;
        @(posedge clk);#1;
        cy=cy+1;if(cy>4000) $fatal(1,"integration timeout");
      end
      @(negedge clk);src_valid=0;mesh_valid=0;write_ready=1;
      if(credit_pulses!=256 || mc!=0 || ac!=0) $fatal(1,"final conservation");
      total_credits=total_credits+credit_pulses;total_aux=total_aux+received;total_mesh=total_mesh+mreceived;
    end
  endtask
  initial begin
    $dumpfile("build/integration.vcd");$dumpvars(0,tb_integration);
    flit[0]=0;flit[1]=0;flit[2]=0;
    repeat(2) @(negedge clk);rst_n=1;
    // NE input to SW output, no other active output.
    command(0,0,1,12'h140,0,0);command(1,1,1,17,0,0);command(2,2,1,17,0,0);
    if(cs_cfg!=0 || tx_cfg!=0 || rx_cfg!=0) $fatal(1,"LOAD modified active state");
    drained=0;command(0,0,1,0,2,6);
    if(cs_cfg!=0) $fatal(1,"unsafe COMMIT accepted");
    drained=1;
    command(0,0,1,0,2,0);command(1,1,1,0,2,0);command(2,2,1,0,2,0);
    stream_round(0);
    // Prepare the next version, but keep old route until safe COMMIT.
    command(0,0,2,0,0,0);command(1,1,2,0,0,0);command(2,2,2,0,0,0);
    drained=0;command(0,0,2,0,2,6);
    if(cs_cfg!=12'h140 || tx_cfg!=17 || rx_cfg!=17) $fatal(1,"pending configuration leaked");
    stream_round(1);
    drained=1;
    command(0,0,2,0,2,0);command(1,1,2,0,2,0);command(2,2,2,0,2,0);
    if(cs_cfg!=0 || tx_cfg!=0 || rx_cfg!=0) $fatal(1,"disable failed");
    src_valid=1;src_data=payload(1,9999);#1;
    if(aux_valid || (|tx_valid)) $fatal(1,"disabled path emitted traffic");
    $display("PASS integration aux_flits=%0d mesh_flits=%0d returned_credits=%0d",total_aux,total_mesh,total_credits);
    $finish;
  end
endmodule
