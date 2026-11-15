`timescale 1ns/1ps
module tb;
  localparam W=256, F=260;
  reg clk=0, reset=1;
  always #5 clk=~clk;
  reg cfg_valid=0;
  reg [77:0] cfg=0;
  wire cfg_ready, applied, rejected;
  reg [16*F-1:0] tx_data=0;
  reg [15:0] tx_valid=0, rx_ready=0, use_circuit=0;
  reg [63:0] tx_cs=0;
  wire [15:0] tx_ready, rx_valid;
  wire [16*W-1:0] rx_data;
  noc_paired dut(clk,reset,cfg_valid,cfg,cfg_ready,applied,rejected,
    tx_data,tx_valid,rx_ready,use_circuit,tx_cs,tx_ready,rx_valid,rx_data);

  function automatic [5:0] conn(input integer i,o);
    conn={1'b1,3'(o),2'(i<o ? i : i-1)};
  endfunction
  task tick;
    @(posedge clk); @(negedge clk);
  endtask
  task submit(input [77:0] image, input bit good);
    cfg=image; cfg_valid=1;
    if(!cfg_ready) $fatal(1,"config unexpectedly busy");
    tick;
    if(applied!==good || rejected!==!good) $fatal(1,"invalid configuration response");
    cfg_valid=0;
  endtask
  task send(input integer src,dst,cs,input [W-1:0] data);
    use_circuit[src]=cs>=0;
    tx_cs[4*src+:4]=4'(cs);
    tx_data[F*src+:F]={4'(dst),data};
    tx_valid[src]=1;
    @(posedge clk);
    while(tx_ready[src]!==1) @(posedge clk);
    @(negedge clk); tx_valid[src]=0;
  endtask
  task receive_one(input integer dst,input [W-1:0] data);
    while(!rx_valid[dst]) @(negedge clk);
    repeat(3) begin
      if(rx_valid!==(16'b1<<dst) || rx_data[W*dst+:W]!==data)
        $fatal(1,"destination, payload or stability mismatch at %0d",dst);
      tick;
    end
    rx_ready[dst]=1; tick; rx_ready[dst]=0;
    if(rx_valid!==0) $fatal(1,"duplicate");
  endtask

  function automatic integer lower(input integer station);
    case(station)
      0: lower=0;
      1: lower=2;
      2: lower=8;
      default: lower=6;
    endcase
  endfunction
  function automatic integer upper(input integer station);
    upper=station<2 ? station+9 : 14-station;
  endfunction
  function automatic integer northwest(input integer sw);
    northwest=(sw/3)*4+sw%3;
  endfunction
  reg [77:0] diagonal, local_pair, cycle_cfg, upper_path;
  integer src,dst,cs,i,j;
  initial begin
    tick; reset=0;
    for(src=0;src<16;src=src+1)
      for(dst=0;dst<16;dst=dst+1) begin
        send(src,dst,-1,256'(1+src*16+dst));
        receive_one(dst,256'(1+src*16+dst));
      end
    $display("PASS 256 Mesh source/destination pairs");
    for(cs=0;cs<9;cs=cs+1)
      for(i=0;i<4;i=i+1)
        for(j=0;j<4;j=j+1) if(i!=j) begin
          local_pair=0; local_pair[cs*6+:6]=conn(i,j);
          submit(local_pair,1);
          src=(cs/3)*4+cs%3+4*(i/2)+i%2;
          dst=(cs/3)*4+cs%3+4*(j/2)+j%2;
          send(src,dst,cs,256'hcafe); receive_one(dst,256'hcafe);
        end
    $display("PASS 108 local ordered CS pairs");
    for(integer direction=1;direction<=3;direction=direction+2)
      for(integer from=0;from<4;from=from+1)
        for(integer dest=0;dest<4;dest=dest+1) if(from!=dest) begin
          upper_path=0;
          upper_path[6*lower(from)+:6]=conn(0,4);
          upper_path[6*lower(dest)+:6]=conn(4,0);
          for(integer at=from;at!=dest;at=(at+direction)%4) begin
            integer cw;
            cw=at%2;
            upper_path[6*upper(at)+:6]=direction==1 ?
              conn(at==from ? 2 : 1-cw,cw) : conn(at==from ? 2 : cw,1-cw);
          end
          upper_path[6*upper(dest)+:6]=conn(direction==1 ? 1-dest%2 : dest%2,2);
          submit(upper_path,1);
          send(northwest(lower(from)),northwest(lower(dest)),lower(from),256'h1357);
          receive_one(northwest(lower(dest)),256'h1357);
        end
    $display("PASS 24 directed upper-ring routes across both orientations");
    diagonal=0;
    diagonal[6*0+:6]=conn(0,4);
    diagonal[6*9+:6]=conn(2,0);
    diagonal[6*10+:6]=conn(0,1);
    diagonal[6*12+:6]=conn(1,2);
    diagonal[6*8+:6]=conn(4,3);
    // Add the two N5 attachments in Fig. 4(b) to the diagonal.
    diagonal[6*1+:6]=conn(2,3);
    diagonal[6*3+:6]=conn(1,3);
    submit(diagonal,1);
    send(0,15,0,256'hffff);
    send(5,6,1,256'h56);
    send(5,9,3,256'h59);
    while((rx_valid & 16'h8240)!=16'h8240) tick;
    if(rx_valid!==16'h8240 || rx_data[15*W+:W]!==256'hffff ||
       rx_data[6*W+:W]!==256'h56 || rx_data[9*W+:W]!==256'h59)
      $fatal(1,"Fig. 4 concurrent circuits or shared-NI tags");
    rx_ready='1; tick; rx_ready=0;
    cycle_cfg=0;
    cycle_cfg[6*9+:6]=conn(1,0); cycle_cfg[6*10+:6]=conn(0,1);
    cycle_cfg[6*12+:6]=conn(1,0); cycle_cfg[6*11+:6]=conn(0,1);
    submit(cycle_cfg,0);
    send(0,15,0,256'h1234);
    send(0,15,0,256'h5678);
    while(!rx_valid[15]) tick;
    cfg=0; cfg_valid=1;
    repeat(10) begin
      tick;
      if(cfg_ready || applied || rx_data[15*W+:W]!==256'h1234)
        $fatal(1,"early update or stalled output changed");
    end
    rx_ready[15]=1; tick; rx_ready[15]=0;
    while(!rx_valid[15]) tick;
    if(rx_data[15*W+:W]!==256'h5678) $fatal(1,"in-flight flit lost");
    while(!applied) tick;
    cfg_valid=0; rx_ready='1; tick;
    $display("PASS Fig. 4 three circuits, cycle rejection and drain before commit");
    $display("PASS_PAPER_NOC");
    $finish;
  end
  initial #200000 $fatal(1,"watchdog");
endmodule

