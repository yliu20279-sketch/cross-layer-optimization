`timescale 1ns/1ps
module tb_dual;
  parameter ENHANCED=1;
  localparam W=256,F=260,MAX_ID=100000;
  reg clk=0,reset=1;
  always #5 clk=~clk;
  reg cfg_valid=0;
  reg [77:0] cfg=0;
  wire cfg_ready,cfg_applied,cfg_rejected;
  reg [16*F-1:0] tx_data=0;
  reg [31:0] tx_kind=0;
  reg [15:0] tx_valid=0,tx_last='1,use_circuit=0,rx_ready='1;
  reg [63:0] tx_cs=0;
  reg [15:0] response_storage_ready='1,response_tx_reserved='1;
  wire [15:0] tx_ready,rx_valid,rx_last;
  wire [16*W-1:0] rx_data;
  wire [31:0] rx_kind;
  dual_plane_noc #(.ENHANCED(ENHANCED)) dut(
    clk,reset,cfg_valid,cfg,cfg_ready,cfg_applied,cfg_rejected,
    tx_data,tx_kind,tx_valid,tx_last,use_circuit,tx_cs,
    response_storage_ready,response_tx_reserved,rx_ready,
    tx_ready,rx_valid,rx_data,rx_kind,rx_last);
  integer sent=0,received=0,next_id=1,seed=641103;
  integer expected_dest [0:MAX_ID];
  integer expected_kind [0:MAX_ID];
  reg expected_last [0:MAX_ID],seen [0:MAX_ID];
  reg source_active [0:15];
  reg [1:0] source_kind [0:15];
  reg [3:0] source_dest [0:15];
  reg [15:0] blocked=0;
  reg [15:0] accepted=0;
  reg [16*(W+3)-1:0] stable_output=0;
  integer cycles=0;
  if(ENHANCED) begin: coherence_checks
    for(genvar n=0;n<16;n=n+1) begin: node
      for(genvar q=0;q<10;q=q+1) begin: bank
        localparam INDEX=q;
        localparam VN=q%2;
        always @(posedge clk)
          if(!reset && dut.dual_plane.coherence.routers[n].router.full[INDEX] &&
            dut.dual_plane.coherence.routers[n].router.queued[INDEX][257]!==1'(VN))
            $fatal(1,"coherence virtual-network bank mismatch node=%0d bank=%0d",n,INDEX);
      end
    end
  end
  always @(posedge clk) begin: check
    integer id,dest,kind;
    cycles=cycles+1;
    if($test$plusargs("progress") && cycles%1000==0)
      $display("PROGRESS cycle=%0d sent=%0d received=%0d valid=%h ready=%h rx=%h",
        cycles,sent,received,tx_valid,tx_ready,rx_valid);
    if(cycles>150000) $fatal(1,"watchdog sent %0d received %0d",sent,received);
    if(reset) begin
      accepted=0;
      blocked=0;
      for(integer n=0;n<16;n=n+1) source_active[n]=0;
    end else begin
      accepted=tx_valid & tx_ready;
      for(integer n=0;n<16;n=n+1) begin
        if(blocked[n] &&
          (!rx_valid[n] || {rx_kind[n*2+:2],rx_last[n],rx_data[n*W+:W]} !==
           stable_output[n*(W+3)+:W+3])) $fatal(1,"unstable RX %0d",n);
        blocked[n]=rx_valid[n] && !rx_ready[n];
        stable_output[n*(W+3)+:W+3]={rx_kind[n*2+:2],rx_last[n],rx_data[n*W+:W]};
        if(tx_valid[n] && tx_ready[n]) begin
          id=tx_data[n*F+:32];
          if(id<=0 || id>=MAX_ID || expected_dest[id]!=-1) $fatal(1,"bad TX ID %0d",id);
          dest=source_active[n] ? source_dest[n] : tx_data[n*F+W+:4];
          kind=source_active[n] ? source_kind[n] : tx_kind[n*2+:2];
          expected_dest[id]=dest;
          expected_kind[id]=kind;
          expected_last[id]=tx_last[n];
          source_active[n]=!tx_last[n];
          source_dest[n]=dest;
          source_kind[n]=kind;
          sent=sent+1;
        end
        if(rx_valid[n] && rx_ready[n]) begin
          id=rx_data[n*W+:32];
          if(id<=0 || id>=MAX_ID) $fatal(1,"RX ID out of range");
          if(expected_dest[id]!=n || seen[id] || expected_kind[id]!=rx_kind[n*2+:2] ||
             expected_last[id]!==rx_last[n] ||
             rx_data[n*W+:W]!==256'(id))
            $fatal(1,"loss/duplicate/class/payload mismatch id=%0d dst=%0d kind=%0d",id,n,rx_kind[n*2+:2]);
          seen[id]=1;
          received=received+1;
        end
      end
    end
  end
  task tick;
    @(posedge clk);
    @(negedge clk);
  endtask
  task drain;
    tx_valid=0;
    rx_ready='1;
    while(received!=sent) tick;
    repeat(6) tick;
    if(rx_valid) $fatal(1,"extra data after drain");
  endtask
  task send(input integer src,dest,kind,input bit last,input integer cs);
    tx_data[src*F+:F]={4'(dest),256'(next_id)};
    next_id=next_id+1;
    tx_kind[src*2+:2]=2'(kind);
    tx_last[src]=last;
    use_circuit[src]=cs>=0;
    tx_cs[src*4+:4]=4'(cs);
    tx_valid[src]=1;
    @(posedge clk);
    while(!tx_ready[src]) @(posedge clk);
    @(negedge clk);
    tx_valid[src]=0;
  endtask
  function automatic [5:0] conn(input integer i,o);
    conn={1'b1,3'(o),2'(i<o ? i : i-1)};
  endfunction
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
  task configure(input [77:0] image,input bit good);
    while(!cfg_ready) tick;
    cfg=image;
    cfg_valid=1;
    tick;
    if(cfg_applied!==good || cfg_rejected!==!good) $fatal(1,"configuration ack");
    cfg_valid=0;
  endtask
  reg [77:0] image;
  integer src,dst,kind;
  initial begin
    for(integer id=0;id<=MAX_ID;id=id+1) begin
      expected_dest[id]=-1;
      expected_kind[id]=-1;
      seen[id]=0;
    end
    tick;
    reset=0;
    for(kind=0;kind<4;kind=kind+1)
      for(src=0;src<16;src=src+1)
        for(dst=0;dst<16;dst=dst+1) begin
          send(src,dst,kind,1,-1);
          drain;
        end
    $display("PASS_ALL_CLASSES_1024_PAIRS arm=%0d",ENHANCED);
    // Body metadata deliberately differs. The first flit pins the packet route.
    for(kind=0;kind<4;kind=kind+1) begin
      send(0,15,kind,0,-1);
      send(0,3,3-kind,0,-1);
      send(0,7,3-kind,1,-1);
      drain;
    end
    $display("PASS_PACKET_PLANE_AND_DESTINATION_PINNING");
    response_storage_ready[0]=0;
    tx_kind[0+:2]=2;
    tx_valid[0]=1;
    repeat(5) begin tick; if(tx_ready[0]) $fatal(1,"missing response reservation"); end
    tx_valid[0]=0;
    response_storage_ready[0]=1;
    response_tx_reserved[0]=0;
    tx_valid[0]=1;
    repeat(5) begin tick; if(tx_ready[0]) $fatal(1,"missing TX reservation"); end
    tx_valid[0]=0;
    response_tx_reserved[0]=1;
    $display("PASS_GETS_RESERVATION_GATES");
    if(ENHANCED) begin
      for(integer cs=0;cs<9;cs=cs+1)
        for(integer i=0;i<4;i=i+1)
          for(integer j=0;j<4;j=j+1) if(i!=j) begin
            image=0;
            image[cs*6+:6]=conn(i,j);
            configure(image,1);
            src=(cs/3)*4+cs%3+4*(i/2)+i%2;
            dst=(cs/3)*4+cs%3+4*(j/2)+j%2;
            send(src,dst,0,1,cs);
            drain;
          end
      $display("PASS_108_LOWER_CS_PATHS");
      for(integer direction=1;direction<=3;direction=direction+2)
        for(integer from=0;from<4;from=from+1)
          for(integer dest=0;dest<4;dest=dest+1) if(from!=dest) begin
            image=0;
            image[6*lower(from)+:6]=conn(0,4);
            image[6*lower(dest)+:6]=conn(4,0);
            for(integer at=from;at!=dest;at=(at+direction)%4) begin
              integer cw;
              cw=at%2;
              image[6*upper(at)+:6]=direction==1 ?
                conn(at==from ? 2 : 1-cw,cw) : conn(at==from ? 2 : cw,1-cw);
            end
            image[6*upper(dest)+:6]=conn(direction==1 ? 1-dest%2 : dest%2,2);
            configure(image,1);
            send((lower(from)/3)*4+lower(from)%3,
                 (lower(dest)/3)*4+lower(dest)%3,0,1,lower(from));
            drain;
          end
      $display("PASS_24_UPPER_CS_PATHS");
      image=0;
      image[6*0+:6]=conn(0,4);
      image[6*9+:6]=conn(2,0);
      image[6*10+:6]=conn(0,1);
      image[6*12+:6]=conn(1,2);
      image[6*8+:6]=conn(4,3);
      configure(image,1);
      send(0,15,0,0,0);
      send(0,15,1,1,8);
      drain;
      $display("PASS_UPPER_CS_PACKET_ROUTE_PINNING");
      image=0;
      image[6*9+:6]=conn(1,0);
      image[6*10+:6]=conn(0,1);
      image[6*12+:6]=conn(1,0);
      image[6*11+:6]=conn(0,1);
      configure(image,0);
      configure(0,1);
      $display("PASS_CYCLE_REJECTION");
      image=0;
      image[6*3+:6]=conn(1,2);
      configure(image,1);
      send(5,8,0,0,3);
      cfg=0;
      cfg_valid=1;
      repeat(6) begin
        tick;
        if(cfg_ready || cfg_applied) $fatal(1,"config crossed incomplete packet");
      end
      send(0,15,2,1,-1);
      send(1,14,3,1,-1);
      send(2,13,1,1,-1);
      send(5,15,1,1,0);
      while(!cfg_applied) tick;
      cfg_valid=0;
      drain;
      $display("PASS_PACKET_DRAIN_AND_COHERENCE_DURING_RECONFIGURATION");
    end
    // Simultaneous randomized traffic with finite queues and receive stalls.
    use_circuit=0;
    for(integer cycle=0;cycle<4000;cycle=cycle+1) begin
      rx_ready=16'($random(seed));
      for(integer n=0;n<16;n=n+1) begin
        if(!tx_valid[n] || accepted[n]) begin
          tx_valid[n]=($random(seed)&3)!=0;
          if(tx_valid[n]) begin
            tx_data[n*F+:F]={4'($random(seed)),256'(next_id)};
            next_id=next_id+1;
            tx_kind[n*2+:2]=2'($random(seed));
            tx_last[n]=1;
          end
        end
      end
      tick;
    end
    // Finish only offers that were blocked in the last random cycle.
    tx_valid=tx_valid & ~accepted;
    rx_ready='1;
    while(tx_valid) begin
      tick;
      tx_valid=tx_valid & ~accepted;
    end
    drain;
    $display("PASS_RANDOM_BACKPRESSURE sent=%0d received=%0d arm=%0d",sent,received,ENHANCED);
    $display("PASS_DUAL_PLANE_RTL");
    $finish;
  end
endmodule
