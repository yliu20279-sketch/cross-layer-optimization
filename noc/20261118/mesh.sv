module noc_slot #(parameter W=256)(
  input wire clk, reset,
  input wire [W-1:0] in_data,
  input wire in_valid, out_ready,
  output wire in_ready,
  output reg [W-1:0] out_data,
  output reg out_valid
);
  // Registered occupancy cuts both the data and the backpressure paths.
  assign in_ready=!reset && !out_valid;
  always @(posedge clk) begin
    if(reset) begin
      out_valid<=0;
      out_data<=0;
    end else if(in_ready && in_valid) begin
      out_valid<=1;
      out_data<=in_data;
    end else if(out_ready) out_valid<=0;
  end
endmodule

module mesh_router #(parameter W=256, ID=0)(
  input wire clk, reset,
  input wire [5*(W+4)-1:0] in_flit,
  input wire [4:0] in_valid, out_ready,
  output wire [4:0] in_ready,
  output reg [4:0] out_valid,
  output reg [5*(W+4)-1:0] out_flit
);
  // Ports E, W, N (+row), S (-row), local.
  localparam F=W+4;
  wire [F-1:0] queued [0:4];
  wire [4:0] full;
  reg [4:0] pop;
  reg [2:0] next_first [0:4], first [0:4];
  reg [4:0] locked, next_locked;
  integer o, k;
  reg [3:0] i;
  function automatic [2:0] route(input [3:0] d);
    if(d[1:0]>(ID%4)) route=0;
    else if(d[1:0]<(ID%4)) route=1;
    else if(d[3:2]>(ID/4)) route=2;
    else if(d[3:2]<(ID/4)) route=3;
    else route=4;
  endfunction
  for(genvar p=0;p<5;p=p+1) begin: queues
    noc_slot #(.W(F)) q(clk,reset,in_flit[p*F+:F],in_valid[p],pop[p],
      in_ready[p],queued[p],full[p]);
    always @(posedge clk)
      if(reset) begin first[p]<=0; locked[p]<=0; end else begin first[p]<=next_first[p]; locked[p]<=next_locked[p]; end
  end
  wire [4:0] transfer [0:4];
  for(genvar p=0;p<5;p=p+1) begin: output_port
    wire [4:0] request, grant;
    wire [F-1:0] chosen [0:5];
    assign chosen[0]='0;
    for(genvar q=0;q<5;q=q+1) begin: input_port
      assign request[q]=full[q] && route(queued[q][W+:4])==p;
      reg select_q;
      always @* begin
        select_q=request[q];
        if(locked[p]) select_q=request[q] && first[p]==q;
        else for(integer t=0;t<5;t=t+1)
          if(request[t] && ((t>=first[p])==(q>=first[p]) ? t<q : t>=first[p]))
            select_q=0;
      end
      assign grant[q]=select_q;
      assign transfer[p][q]=grant[q] && out_ready[p];
      assign chosen[q+1]=chosen[q] | (queued[q] & {F{grant[q]}});
    end
    always @* begin
      out_valid[p]=|grant;
      out_flit[p*F+:F]=chosen[5];
      next_first[p]=first[p];
      next_locked[p]=locked[p];
      for(integer q=0;q<5;q=q+1)
        if(grant[q]) begin
          next_first[p]=out_ready[p] ? (q==4 ? 3'd0 : 3'(q+1)) : 3'(q);
          next_locked[p]=!out_ready[p];
        end
    end
  end
  for(genvar q=0;q<5;q=q+1) begin: dequeue
    always @* pop[q]=transfer[0][q] | transfer[1][q] | transfer[2][q] |
                     transfer[3][q] | transfer[4][q];
  end
endmodule

module mesh16 #(parameter W=256)(
  input wire clk, reset,
  input wire [16*(W+4)-1:0] tx_data,
  input wire [15:0] tx_valid, rx_ready,
  output wire [15:0] tx_ready, rx_valid,
  output wire [16*W-1:0] rx_data
);
  localparam F=W+4;
  wire [5*F-1:0] in_flit [0:15], out_flit [0:15];
  wire [4:0] iv [0:15], ir [0:15], ov [0:15], rd [0:15];
  for(genvar n=0;n<16;n=n+1) begin: routers
    for(genvar p=0;p<4;p=p+1) begin: links
      localparam PEER=p==0 ? n+1 : p==1 ? n-1 : p==2 ? n+4 : n-4;
      localparam OPP=p^1;
      localparam CONNECTED=p==0 ? n%4!=3 : p==1 ? n%4!=0 : p==2 ? n/4!=3 : n/4!=0;
      if(CONNECTED) begin
        assign in_flit[n][p*F+:F]=out_flit[PEER][OPP*F+:F];
        assign iv[n][p]=ov[PEER][OPP];
        assign rd[n][p]=ir[PEER][OPP];
      end else begin
        assign in_flit[n][p*F+:F]=0;
        assign iv[n][p]=0;
        assign rd[n][p]=0;
      end
    end
    assign in_flit[n][4*F+:F]=tx_data[n*F+:F];
    assign iv[n][4]=tx_valid[n];
    assign tx_ready[n]=ir[n][4];
    assign rx_data[n*W+:W]=out_flit[n][4*F+:W];
    assign rx_valid[n]=ov[n][4];
    assign rd[n][4]=rx_ready[n];
    mesh_router #(.W(W),.ID(n)) r(clk,reset,in_flit[n],iv[n],rd[n],ir[n],ov[n],out_flit[n]);
  end
endmodule



