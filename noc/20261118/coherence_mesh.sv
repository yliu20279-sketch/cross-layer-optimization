module coherence_router #(parameter W=259, ID=0)(
  input wire clk, reset,
  input wire [5*(W+4)-1:0] in_flit,
  input wire [4:0] in_valid,
  input wire [9:0] out_credit,
  output wire [9:0] in_credit,
  output reg [4:0] out_valid,
  output wire [5*(W+4)-1:0] out_flit
);
  localparam F=W+4;
  wire [F-1:0] queued [0:9];
  wire [9:0] full;
  wire [9:0] pop;
  wire [9:0] transfer [0:4];
  reg [3:0] first [0:4];
  reg [F-1:0] output_data [0:4];
  function automatic [2:0] route(input [3:0] destination);
    if(destination[1:0] > ID%4) route=0;
    else if(destination[1:0] < ID%4) route=1;
    else if(destination[3:2] > ID/4) route=2;
    else if(destination[3:2] < ID/4) route=3;
    else route=4;
  endfunction
  // W-2 is kind[0], the GetS/DataS virtual-network bit.
  for(genvar p=0;p<5;p=p+1) begin: inputs
    for(genvar v=0;v<2;v=v+1) begin: virtual_network
      localparam INDEX=p*2+v;
      localparam VN=v;
      wire [F-1:0] data;
      assign queued[INDEX]=data;
      noc_slot #(.W(F)) queue(clk,reset,in_flit[p*F+:F],
        in_valid[p] && in_flit[p*F+W-2]==VN,pop[INDEX],
        in_credit[INDEX],data,full[INDEX]);
    end
  end
  for(genvar p=0;p<5;p=p+1) begin: outputs
    wire output_ready=!out_valid[p] ||
      (output_data[p][W-2] ? out_credit[p*2+1] : out_credit[p*2]);
    wire [9:0] request,grant;
    wire [F-1:0] selected [0:10];
    assign selected[0]='0;
    for(genvar q=0;q<10;q=q+1) begin: candidates
      assign request[q]=full[q] && route(queued[q][W+:4])==p;
      reg selected_q;
      always @* begin
        selected_q=request[q];
        for(integer t=0;t<10;t=t+1)
          if(request[t] && ((t>=first[p])==(q>=first[p]) ? t<q : t>=first[p]))
            selected_q=0;
      end
      assign grant[q]=selected_q;
      assign selected[q+1]=selected[q] | (queued[q] & {F{grant[q]}});
      assign transfer[p][q]=grant[q] && output_ready && !reset;
    end
    assign out_flit[p*F+:F]=output_data[p];
    always @(posedge clk) begin
      if(reset) begin
        first[p]<=0;
        out_valid[p]<=0;
        output_data[p]<=0;
      end else if(output_ready) begin
        out_valid[p]<=|grant;
        if(|grant) begin
          output_data[p]<=selected[10];
          for(integer q=0;q<10;q=q+1)
            if(grant[q]) first[p]<=q==9 ? 4'd0 : 4'(q+1);
        end
      end
    end
  end
  for(genvar q=0;q<10;q=q+1) begin: dequeue
    assign pop[q]=transfer[0][q] | transfer[1][q] | transfer[2][q] |
                  transfer[3][q] | transfer[4][q];
  end
endmodule

module coherence_mesh #(parameter W=259)(
  input wire clk,reset,
  input wire [16*(W+4)-1:0] tx_data,
  input wire [15:0] tx_valid,rx_ready,
  output wire [31:0] tx_credit,
  output wire [15:0] rx_valid,
  output wire [16*W-1:0] rx_data
);
  localparam F=W+4;
  wire [5*F-1:0] in_flit [0:15],out_flit [0:15];
  wire [4:0] iv [0:15],ov [0:15];
  wire [9:0] credit [0:15],ready [0:15];
  for(genvar n=0;n<16;n=n+1) begin: routers
    for(genvar p=0;p<4;p=p+1) begin: links
      localparam PEER=p==0 ? n+1 : p==1 ? n-1 : p==2 ? n+4 : n-4;
      localparam OPP=p^1;
      localparam CONNECTED=p==0 ? n%4!=3 : p==1 ? n%4!=0 :
                           p==2 ? n/4!=3 : n/4!=0;
      if(CONNECTED) begin
        assign in_flit[n][p*F+:F]=out_flit[PEER][OPP*F+:F];
        assign iv[n][p]=ov[PEER][OPP];
        assign ready[n][p*2+:2]=credit[PEER][OPP*2+:2];
      end else begin
        assign in_flit[n][p*F+:F]=0;
        assign iv[n][p]=0;
        assign ready[n][p*2+:2]=0;
      end
    end
    assign in_flit[n][4*F+:F]=tx_data[n*F+:F];
    assign iv[n][4]=tx_valid[n];
    assign tx_credit[2*n+:2]=credit[n][8+:2];
    assign rx_data[n*W+:W]=out_flit[n][4*F+:W];
    assign rx_valid[n]=ov[n][4];
    assign ready[n][8+:2]={2{rx_ready[n]}};
    coherence_router #(.W(W),.ID(n)) router(
      clk,reset,in_flit[n],iv[n],ready[n],credit[n],ov[n],out_flit[n]);
  end
endmodule
