module tb;
  localparam W=256;
  localparam [11:0] OLD=(1<<10)|(1<<7)|(1<<5), OLD_SEL=1<<10;
  localparam [11:0] NEW=(1<<9)|(1<<0)|(1<<5), NEW_SEL=(1<<9)|(1<<5);
  localparam [11:0] REVERSE=(1<<4)|(1<<1)|(1<<11), REVERSE_SEL=1<<4;
  reg clk=0;
  always #5 clk=~clk;
  reg reset=1, load=0, commit=0;
  reg [15:0] epoch=0;
  reg [11:0] en0=0, sel0=0, en1=0, sel1=0;
  reg [3:0] tx0=0, rx0=0, tx1=0, rx1=0, ack=0;
  wire [11:0] en, sel;
  wire [3:0] tx, rx, drained, inject, pop, fault;
  wire stop, reject, applied, resumed;
  reg [3:0] request=0, consume=0;
  reg [107:0] local_cfg=0;
  wire [35:0] valid, credit;
  wire [36*W-1:0] data_in, data_out;
  wire [35:0] in_valid, returned;
  wire [8:0] local_legal;
  integer sent [0:3], got [0:3];
  integer seq_base=100;
  integer expected_src [0:3];
  wire [35:0] exercised=(36'b1<<0)|(36'b1<<11)|(36'b1<<32)|(36'b1<<24);
  function automatic [W-1:0] payload(input integer source, id);
    payload={32'hca123456,source,id,~id,32'h01234567,32'h89abcdef,32'h55aa55aa,32'hfedcba98};
  endfunction

  path_commit manager(clk,reset,load,commit,epoch,en0,sel0,en1,sel1,
    tx0,rx0,tx1,rx1,drained,ack,en,sel,tx,rx,stop,reject,applied,resumed);
  full_fabric fabric(data_in,in_valid,returned,local_cfg,en,sel,tx,rx,8'h0c,8'h0c,
    data_out,valid,credit,local_legal);
  for(genvar i=0;i<36;i=i+1) begin: lanes
    localparam S=i==0 ? 0 : i==11 ? 1 : i==32 ? 2 : i==24 ? 3 : -1;
    if(S>=0) begin: live
      wire [W-1:0] popped;
      credit_endpoint ep(clk,reset,stop,request[S],consume[S],valid[i],credit[i],
        data_out[i*W+:W],inject[S],pop[S],drained[S],popped,fault[S]);
      assign data_in[i*W+:W]=payload(S,seq_base+sent[S]);
      assign in_valid[i]=inject[S];
      assign returned[i]=pop[S];
      always @(posedge clk) if(!reset) begin
        if(inject[S]) sent[S]<=sent[S]+1;
        if(pop[S]) begin
          if(popped!==payload(expected_src[S],seq_base+got[S]))
            $fatal(1,"wrong data, order or destination at site %0d",S);
          got[S]<=got[S]+1;
        end
      end
    end else begin: idle
      assign data_in[i*W+:W]=0;
      assign in_valid[i]=0;
      assign returned[i]=0;
    end
  end
  always @(posedge clk) if(!reset) begin
    if ((valid & ~exercised)!==0 || (credit & ~exercised)!==0 ||
        fault!==0 || local_legal!==9'h1ff)
      $fatal(1,"unexpected destination, credit or endpoint fault");
    if(stop && inject!==0) $fatal(1,"injection during stop");
  end

  task tick;
    begin @(posedge clk); @(negedge clk); end
  endtask
  task command(input integer is_load, e, expect_reject);
    begin
      epoch=e; load=is_load!=0; commit=is_load==0;
      tick;
      if(reject!== (expect_reject!=0)) $fatal(1,"command rejection mismatch epoch=%0d",e);
      load=0; commit=0;
    end
  endtask
  task confirm_all;
    begin
      tick;
      if(!applied || !stop) $fatal(1,"missing apply/stop");
      ack=4'hf; tick; ack=0;
      if(!resumed || stop) $fatal(1,"missing resume");
    end
  endtask
  task clear_scoreboard;
    begin
      for(integer i=0;i<4;i=i+1) begin sent[i]=0; got[i]=0; end
      expected_src[0]=-1; expected_src[1]=3; expected_src[2]=-1; expected_src[3]=1;
    end
  endtask

  initial begin
    if($test$plusargs("trace")) begin
      $dumpfile("STEP2.vcd");
      $dumpvars(1,tb);
    end
    clear_scoreboard;
    tick; reset=0;
    en0=OLD; sel0=OLD_SEL; tx0=8; rx0=2;
    command(1,1,0); command(0,1,0); confirm_all;
    en0=OLD|(1<<9)|(1<<2); sel0=OLD_SEL|(1<<9)|(1<<2); rx0=3;
    command(1,2,1);
    if(en!==OLD || stop) $fatal(1,"replication modified active circuit");
    $display("PASS reject unicast replication");
    en0=OLD; sel0=OLD_SEL; rx0=2;
    en1=(1<<1)|(1<<10)|(1<<8); sel1=1<<1; tx1=1; rx1=4; #1; if(!manager.legal0 || !manager.legal1) $fatal(1,"shared-link fixture invalid");
    command(1,2,1);
    if(en!==OLD || stop) $fatal(1,"shared link modified active circuit");
    en1=(1<<9)|(1<<2); sel1=en1; tx1=8; rx1=1; #1; if(!manager.legal0 || !manager.legal1) $fatal(1,"shared-TX fixture invalid");
    command(1,2,1);
    if(en!==OLD || stop) $fatal(1,"conflict modified active circuit");
    $display("PASS reject shared upper link and shared vertical port");
    en1=0; sel1=0; tx1=0; rx1=0;
    en0=12'h249; sel0=0; tx0=0; rx0=0;
    command(1,2,1);
    $display("PASS reject directed combinational ring");
    en0=OLD; sel0=OLD_SEL; tx0=8; rx0=0;
    command(1,2,1);
    $display("PASS reject malformed route encoding");
    local_cfg[48+:3]=3'b111; #1;
    if(local_legal[4]!==0 || valid[16+:4]!==0 || credit[16+:4]!==0)
      $fatal(1,"illegal lower SEL did not fail closed");
    local_cfg=0;
    $display("PASS lower CS illegal SEL fails closed");

    // Fill destination while no credits are allowed to return.
    request=8;
    repeat(8) tick;
    if(sent[3]!=4 || got[1]!=0 || drained[1] || drained[3])
      $fatal(1,"did not create genuine outstanding data and credit");
    en0=NEW; sel0=NEW_SEL; rx0=2;
    command(1,16'h102,0);
    command(0,16'h103,1);
    if(en!==OLD || stop) $fatal(1,"wrong epoch changed active path");
    $display("PASS reject wrong epoch");
    command(0,16'h102,0);
    repeat(5) begin
      tick;
      if(en!==OLD || !stop || applied || sent[3]!=4)
        $fatal(1,"old route changed before drain");
    end
    consume=2;
    repeat(4) begin
      tick;
      if(en!==OLD || !stop || applied) $fatal(1,"premature apply");
    end
    if(got[1]!=4 || drained!==4'hf) $fatal(1,"old route failed to drain");
    tick;
    if(en!==NEW || !applied || !stop) $fatal(1,"new route not applied after drain");
    ack=7; tick; ack=0;
    repeat(5) begin
      tick;
      if(!stop || resumed || sent[3]!=4) $fatal(1,"resumed before last ack");
    end
    ack=8; tick; ack=0;
    if(stop || !resumed) $fatal(1,"resume after final ack failed");
    repeat(6) tick;
    request=0; repeat(6) tick;
    if(sent[3]!=10 || got[1]!=10 || drained!==4'hf) $fatal(1,"switch data loss");
    $display("PASS live switch old_flits=4 new_flits=6, missing ack stalls injection");

    // Two disjoint old-direction circuits coexist, with independent credits.
    en0=OLD; sel0=OLD_SEL; rx0=2;
    en1=REVERSE; sel1=REVERSE_SEL; tx1=2; rx1=8;
    command(1,16'h104,0); command(0,16'h104,0); confirm_all;
    request=10; consume=10;
    repeat(6) tick;
    request=0; repeat(6) tick;
    if(sent[3]!=16 || got[1]!=16 || sent[1]!=6 || got[3]!=6 || drained!==4'hf)
      $fatal(1,"concurrent circuit mismatch");
    $display("PASS concurrent disjoint routes 6 flits each");

    request=8; consume=0;
    repeat(3) tick;
    if(sent[3]!=19 || got[1]!=16 || drained[1] || drained[3])
      $fatal(1,"reset not tested with queued data");
    reset=1; tick;
    if(en!==0 || tx!==0 || rx!==0 || drained!==4'hf || valid!==0 || credit!==0)
      $fatal(1,"reset did not clear configuration/FIFO/credits");
    request=0; clear_scoreboard; seq_base=200;
    reset=0; consume=15;
    repeat(5) tick;
    if(got[1]!=0 || drained!==4'hf) $fatal(1,"ghost flit or credit");
    en1=0; sel1=0; tx1=0; rx1=0;
    command(1,16'h105,0); command(0,16'h105,0); confirm_all;
    request=8; tick; request=0; repeat(5) tick;
    if(sent[3]!=1 || got[1]!=1 || drained!==4'hf) $fatal(1,"reset recovery failed");
    $display("PASS destructive global reset flushed 3 queued flits, fresh traffic passed");
    $display("PASS_STEP2");
    $finish;
  end
  initial #10000 $fatal(1,"watchdog");
endmodule





