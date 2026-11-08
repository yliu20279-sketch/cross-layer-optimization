`timescale 1ns/1ps
module aux_mesh(
    input wire clk,rst_n,
    input wire [4095:0] inject_data,
    input wire [15:0] inject_valid,
    output wire [15:0] inject_ready,
    output wire [4095:0] eject_data,
    output wire [15:0] eject_valid,
    input wire [15:0] eject_ready,
    output wire [4095:0] aux_data,
    output wire [15:0] aux_valid,
    input wire [15:0] aux_ready,
    output reg [31:0] buffered_flits,
    output reg [15:0] pending_aux_gateways,
    input wire hold_aux_prefix
);
    wire [1279:0] ri[0:15];
    wire [1535:0] ro[0:15];
    wire [4:0] iv[0:15],ir[0:15];
    wire [5:0] ov[0:15],orr[0:15];
    wire [31:0] count[0:15];
    wire [15:0] pending[0:15];
    genvar n;
    generate for(n=0;n<16;n=n+1) begin:nodes
        aux_xy_router #(.NODE_ID(n)) router(clk,rst_n,ri[n],iv[n],ir[n],ro[n],ov[n],orr[n],count[n],pending[n]);
        assign ri[n][0+:256]=inject_data[n*256+:256];assign iv[n][0]=inject_valid[n];assign inject_ready[n]=ir[n][0];
        assign eject_data[n*256+:256]=ro[n][0+:256];assign eject_valid[n]=ov[n][0];assign orr[n][0]=eject_ready[n];
        assign aux_data[n*256+:256]=ro[n][1280+:256];assign aux_valid[n]=ov[n][5];assign orr[n][5]=aux_ready[n];
        if(n>=4) begin
            assign ri[n][256+:256]=ro[n-4][768+:256];
            if(n==4) assign iv[n][1]=ov[n-4][3]&&!(hold_aux_prefix&&ro[0][1021+:3]==4);
            else assign iv[n][1]=ov[n-4][3];
            assign orr[n][1]=ir[n-4][3];
        end else begin assign ri[n][256+:256]=0;assign iv[n][1]=0;assign orr[n][1]=0;end
        if(n%4<3) begin
            assign ri[n][512+:256]=ro[n+1][1024+:256];assign iv[n][2]=ov[n+1][4];assign orr[n][2]=ir[n+1][4];
        end else begin assign ri[n][512+:256]=0;assign iv[n][2]=0;assign orr[n][2]=0;end
        if(n<12) begin
            assign ri[n][768+:256]=ro[n+4][256+:256];assign iv[n][3]=ov[n+4][1];
            if(n==0) assign orr[n][3]=ir[n+4][1]&&!(hold_aux_prefix&&ro[0][1021+:3]==4);
            else assign orr[n][3]=ir[n+4][1];
        end else begin assign ri[n][768+:256]=0;assign iv[n][3]=0;assign orr[n][3]=0;end
        if(n%4>0) begin
            assign ri[n][1024+:256]=ro[n-1][512+:256];assign iv[n][4]=ov[n-1][2];assign orr[n][4]=ir[n-1][2];
        end else begin assign ri[n][1024+:256]=0;assign iv[n][4]=0;assign orr[n][4]=0;end
    end endgenerate
    integer j;
    always @* begin
        buffered_flits=0;pending_aux_gateways=0;
        for(j=0;j<16;j=j+1) begin buffered_flits=buffered_flits+count[j];pending_aux_gateways=pending_aux_gateways|pending[j];end
    end
endmodule
