module tb;
  localparam W=256, DEPTH=4;
  reg clk=0;
  always #5 clk=~clk;
  reg [4*W-1:0] data=0;
  reg [3:0] inject=0, returned=0, tx=0, rx=0;
  reg [11:0] enable=0, sel=0;
  wire [4*W-1:0] delivered;
  wire [3:0] arrived, credit, leaked;
  diagonal_top dut(data,inject,returned,tx,rx,enable,sel,delivered,arrived,credit,leaked);

  function automatic [W-1:0] payload(input integer id, source);
    payload = {32'hca123456, id, ~id, source, 32'h01234567,
               32'h89abcdef, id ^ 32'h55aa55aa, 32'hfedcba98};
  endfunction

  task automatic run(input integer src, dst, total, stall_cycles);
    integer sent, popped, received, head, tail, used, balance, cycle;
    reg [W-1:0] fifo [0:DEPTH-1];
    reg push, pop;
    begin
      sent=0; popped=0; received=0; head=0; tail=0; used=0; balance=DEPTH;
      for (cycle=0;cycle<total+stall_cycles+DEPTH+8;cycle=cycle+1) begin
        @(negedge clk);
        inject=0; returned=0; data=0;
        push=sent<total && balance>0;
        pop=cycle>=stall_cycles && used>0;
        inject[src]=push;
        returned[dst]=pop;
        data[src*W+:W]=payload(sent,src);
        @(posedge clk);
        if (leaked !== 4'b0 || arrived !== (push ? (4'b1 << dst) : 4'b0)
            || credit !== (pop ? (4'b1 << src) : 4'b0))
          $fatal(1,"route failure cycle=%0d arrived=%b credit=%b leaked=%b",cycle,arrived,credit,leaked);
        if (pop) begin
          if (fifo[head] !== payload(popped,src)) $fatal(1,"FIFO order/payload mismatch");
          head=(head+1)%DEPTH;
          popped=popped+1;
        end
        if (arrived[dst]) begin
          if (used==DEPTH && !pop) $fatal(1,"FIFO overflow");
          if (delivered[dst*W+:W] !== payload(received,src)) $fatal(1,"flit mismatch");
          fifo[tail]=delivered[dst*W+:W];
          tail=(tail+1)%DEPTH;
          received=received+1;
        end
        sent=sent+int'(push);
        used=used+int'(arrived[dst])-int'(pop);
        balance=balance-int'(push)+int'(credit[src]);
        if (balance<0 || balance>DEPTH || balance+used!=DEPTH) $fatal(1,"credit conservation");
        if (cycle<stall_cycles && cycle>=DEPTH && (balance!=0 || push))
          $fatal(1,"source did not stop on exhausted credits");
      end
      if (sent!=total || received!=total || popped!=total || used!=0 || balance!=DEPTH)
        $fatal(1,"failed to drain");
      $display("PASS src=%0d dst=%0d sent=%0d received=%0d popped=%0d credits=%0d stall=%0d",
               src,dst,sent,received,popped,balance,stall_cycles);
    end
  endtask

  initial begin
    @(posedge clk);
    if (arrived !== 0 || credit !== 0 || leaked !== 0) $fatal(1,"disabled fabric is not idle");
    @(negedge clk);
    // 11.B <- D, 12.B <- A, 10.D <- A
    enable=(1<<10)|(1<<7)|(1<<5); sel=(1<<10);
    tx=4'b1000; rx=4'b0010;
    run(3,1,1,0);
    run(3,1,17,10);
    @(negedge clk);
    // Reverse via the other half of the ring: 10.B <- D, 9.B <- A, 11.D <- A.
    enable=(1<<4)|(1<<1)|(1<<11); sel=(1<<4);
    tx=4'b0010; rx=4'b1000;
    run(1,3,1,0);
    run(1,3,17,10);
    // Exercise the remaining vertical interfaces in both directions.
    @(negedge clk);
    enable=(1<<0)|(1<<3)|(1<<8); sel=(1<<0)|(1<<8);
    tx=4'b0001; rx=4'b0100;
    run(0,2,17,10);
    @(negedge clk);
    enable=(1<<6)|(1<<9)|(1<<2); sel=(1<<6)|(1<<2);
    tx=4'b0100; rx=4'b0001;
    run(2,0,17,10);
    $display("PASS_STEP1");
    $finish;
  end
  initial #100000 $fatal(1,"watchdog");
endmodule




