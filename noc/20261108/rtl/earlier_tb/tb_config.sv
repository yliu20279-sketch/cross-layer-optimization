`timescale 1ns/1ps
module tb_config;
  reg clk=0;always #5 clk=~clk;
  reg rst_n=0;
  reg [15:0] rv=0,rr=0,fr=0,dr=0;
  reg [255:0] flit[0:15];
  wire [15:0] ready,valid;
  wire [2:0] status[0:15];
  wire [156:0] snap[0:15];
  reg [156:0] expected[0:15];
  genvar g;
  generate for(g=0;g<16;g=g+1) begin:agents
    ni_config_agent #(.NODE_ID(g)) dut(
      .clk(clk),.rst_n(rst_n),.req_valid(rv[g]),.req_ready(ready[g]),.req_flit(flit[g]),
      .aux_frozen(fr[g]),.global_drained(dr[g]),.rsp_valid(valid[g]),.rsp_ready(rr[g]),
      .rsp_status(status[g]),.state_snapshot(snap[g]),.cs_cfg(),.tx_cfg(),.rx_cfg(),
      .pending_states(),.pending_epochs(),.active_epochs(),.pending_valids());
  end endgenerate
  integer fd,rc,n,f,d,h,s,i,j,rows=0,held=0;
  reg [255:0] packet;
  reg [156:0] es;
  initial begin
    for(i=0;i<16;i=i+1) begin flit[i]=0;expected[i]=0;end
    repeat(2) @(negedge clk);rst_n=1;
    fd=$fopen("vectors/config.txt","r");if(!fd) $fatal(1,"missing config vectors");
    while(!$feof(fd)) begin
      rc=$fscanf(fd,"%h %h %h %h %h %h %h\n",n,packet,f,d,h,s,es);
      if(rc!=7) $fatal(1,"bad config vector row=%0d rc=%0d",rows,rc);
      @(negedge clk);
      if(!ready[n]) $fatal(1,"receiver not ready");
      rv[n]=1;flit[n]=packet;fr[n]=f;dr[n]=d;rr[n]=0;
      @(posedge clk);#1;
      expected[n]=es;
      if(!valid[n] || status[n]!==s[2:0]) $fatal(1,"status row=%0d node=%0d got=%0d expected=%0d",rows,n,status[n],s);
      for(i=0;i<16;i=i+1) if(snap[i]!==expected[i])
        $fatal(1,"state row=%0d node=%0d got=%h expected=%h",rows,i,snap[i],expected[i]);
      // Poison requests during response backpressure must not modify state.
      for(j=0;j<h;j=j+1) begin
        @(negedge clk);flit[n]=0;rv[n]=1;#1;
        if(ready[n]) $fatal(1,"request accepted while response blocked");
        @(posedge clk);#1;
        if(!valid[n] || status[n]!==s[2:0] || snap[n]!==expected[n]) $fatal(1,"backpressure corruption");
        held=held+1;
      end
      @(negedge clk);rv[n]=0;rr[n]=1;
      @(posedge clk);#1;if(valid[n]) $fatal(1,"response not retired");
      @(negedge clk);rr[n]=0;
      rows=rows+1;
    end
    $fclose(fd);
    // Reset must also clear committed high versions and pending state.
    rst_n=0;#1;
    for(i=0;i<16;i=i+1) if(snap[i]!==0 || valid[i]!==0) $fatal(1,"reset mismatch");
    $display("PASS config transactions=%0d stalled_response_cycles=%0d nodes=16",rows,held);
    $finish;
  end
endmodule
