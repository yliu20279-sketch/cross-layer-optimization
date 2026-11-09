module route_guard (
  input wire [11:0] en, sel,
  input wire [3:0] tx, rx,
  output reg legal
);
  integer s, o, i, pass, parent, input_port;
  reg [11:0] reachable;
  reg [2:0] used;
  always @* begin
    legal=1;
    reachable=0;
    for(s=0;s<4;s=s+1) begin
      used=0;
      for(o=0;o<3;o=o+1) begin
        i=3*s+o;
        input_port=sel[i] ? (o==2 ? 1 : 2) : (o==0 ? 1 : 0);
        if(en[i]) begin
          if(used[input_port]) legal=0;
          used[input_port]=1;
        end
      end
      if(used[2]!=tx[s] || en[3*s+2]!=rx[s]) legal=0;
    end
    // A valid circuit starts at a vertical injection. Every enabled output
    // must be reachable from one, and every used horizontal link must continue.
    for(pass=0;pass<12;pass=pass+1)
      for(s=0;s<4;s=s+1)
        for(o=0;o<3;o=o+1) begin
          i=3*s+o;
          input_port=sel[i] ? (o==2 ? 1 : 2) : (o==0 ? 1 : 0);
          parent=input_port==0 ? 3*((s+1)%4)+1 : 3*((s+3)%4);
          if(en[i] && (input_port==2 ? tx[s] : reachable[parent]))
            reachable[i]=1;
        end
    if(reachable!=en) legal=0;
    for(s=0;s<4;s=s+1)
      for(o=0;o<2;o=o+1) begin
        parent=o==0 ? (s+1)%4 : (s+3)%4;
        used=0;
        for(i=0;i<3;i=i+1) begin
          input_port=sel[3*parent+i] ? (i==2 ? 1 : 2) : (i==0 ? 1 : 0);
          if(en[3*parent+i]) used[input_port]=1;
        end
        if(en[3*s+o]!=used[1-o]) legal=0;
      end
  end
endmodule

module path_commit (
  input wire clk, reset, load, commit,
  input wire [15:0] epoch,
  input wire [11:0] en0, sel0, en1, sel1,
  input wire [3:0] tx0, rx0, tx1, rx1,
  input wire [3:0] drained, ack,
  output reg [11:0] active_en, active_sel,
  output reg [3:0] active_tx, active_rx,
  output wire stop,
  output reg reject, applied, resumed
);
  wire legal0, legal1;
  route_guard g0(en0,sel0,tx0,rx0,legal0);
  route_guard g1(en1,sel1,tx1,rx1,legal1);
  wire conflict=(|(en0&en1)) || (|(tx0&tx1)) || (|(rx0&rx1));
  localparam IDLE=0, DRAIN=1, CONFIRM=2;
  reg [1:0] phase;
  reg pending;
  reg [15:0] pending_epoch;
  reg [11:0] pen, psel;
  reg [3:0] ptx, prx, seen;
  assign stop=reset || phase!=IDLE;
  always @(posedge clk) begin
    reject<=0;
    applied<=0;
    resumed<=0;
    if(reset) begin
      active_en<=0; active_sel<=0; active_tx<=0; active_rx<=0;
      phase<=IDLE; pending<=0; pending_epoch<=0;
      pen<=0; psel<=0; ptx<=0; prx<=0; seen<=0;
    end else begin
      if(load && commit) reject<=1;
      else if(load) begin
        if(phase!=IDLE || !legal0 || !legal1 || conflict) reject<=1;
        else begin
          pending<=1; pending_epoch<=epoch;
          pen<=en0|en1; psel<=(sel0&en0)|(sel1&en1);
          ptx<=tx0|tx1; prx<=rx0|rx1;
        end
      end else if(commit) begin
        if(phase!=IDLE || !pending || epoch!=pending_epoch) reject<=1;
        else phase<=DRAIN;
      end
      if(phase==DRAIN && (&drained)) begin
        active_en<=pen; active_sel<=psel; active_tx<=ptx; active_rx<=prx;
        pending<=0; applied<=1; phase<=CONFIRM; seen<=0;
      end
      if(phase==CONFIRM) begin
        seen<=seen|ack;
        if(&(seen|ack)) begin
          phase<=IDLE;
          resumed<=1;
        end
      end
    end
  end
endmodule
