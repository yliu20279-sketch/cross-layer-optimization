`timescale 1ns/1ps
// Five input FIFOs. Outputs 0..4=L/N/E/S/W; output 5 is AUX when enabled.
// CS receive traffic terminates at the NI, so there is no AUX input here.
module aux_xy_router #(
    parameter integer NODE_ID=5,DEPTH=2,ENABLE_AUX=1,DEBUG=1
)(
    input wire clk,rst_n,
    input wire [1279:0] in_data,
    input wire [4:0] in_valid,
    output reg [4:0] in_ready,
    output reg [(5+ENABLE_AUX)*256-1:0] out_data,
    output reg [4+ENABLE_AUX:0] out_valid,
    input wire [4+ENABLE_AUX:0] out_ready,
    output reg [31:0] buffered_flits,
    output reg [15:0] pending_aux_gateways
);
    localparam OUTS=5+ENABLE_AUX;
    localparam PTR_W=DEPTH>1?$clog2(DEPTH):1;
    localparam COUNT_W=$clog2(DEPTH+1);
    reg [255:0] fifo[0:5*DEPTH-1];
    reg [PTR_W-1:0] rd[0:4],wr[0:4];
    reg [COUNT_W-1:0] count[0:4];
    reg [2:0] rr[0:OUTS-1],held[0:OUTS-1];
    reg [OUTS-1:0] locked;
    integer chosen[0:OUTS-1],route[0:4];
    reg [4:0] pop,push;
    integer p,o,t,candidate,a,b,index;
    function integer next_port(input [255:0] flit);
        integer dest,x,y;
        begin
            dest=flit[252:249];x=dest%4;y=dest/4;
            if(x>NODE_ID%4) next_port=2;
            else if(x<NODE_ID%4) next_port=4;
            else if(y>NODE_ID/4) next_port=3;
            else if(y<NODE_ID/4) next_port=1;
            else if(ENABLE_AUX && flit[255:253]==4) next_port=5;
            else next_port=0;
        end
    endfunction
    always @* begin
        out_data=0;out_valid=0;in_ready=0;pop=0;push=0;candidate=0;
        buffered_flits=0;pending_aux_gateways=0;index=0;a=0;b=0;
        for(p=0;p<5;p=p+1) begin
            route[p]=-1;
            if(count[p]!=0) route[p]=next_port(fifo[p*DEPTH+rd[p]]);
        end
        for(o=0;o<OUTS;o=o+1) begin
            chosen[o]=-1;
            if(locked[o]) chosen[o]=held[o];
            else for(t=0;t<5;t=t+1) begin
                candidate=(rr[o]<5?rr[o]:0)+t;
                if(candidate>=5) candidate=candidate-5;
                if(chosen[o]<0 && count[candidate]!=0 && route[candidate]==o) chosen[o]=candidate;
            end
            if(chosen[o]>=0) begin
                out_valid[o]=1;
                out_data[o*256+:256]=fifo[chosen[o]*DEPTH+rd[chosen[o]]];
                if(out_ready[o]) pop[chosen[o]]=1;
            end
        end
        for(p=0;p<5;p=p+1) begin
            in_ready[p]=(count[p]<DEPTH)||pop[p];push[p]=in_valid[p]&&in_ready[p];
        end
        if(DEBUG) for(a=0;a<5;a=a+1) begin
            buffered_flits=buffered_flits+count[a];
            for(b=0;b<DEPTH;b=b+1) if(b<count[a]) begin
                index=a*DEPTH+(rd[a]+b)%DEPTH;
                if(fifo[index][255:253]==4) pending_aux_gateways[fifo[index][252:249]]=1;
            end
        end
    end
    integer j;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            for(j=0;j<5;j=j+1) begin rd[j]<=0;wr[j]<=0;count[j]<=0;end
            locked<=0;
            for(j=0;j<OUTS;j=j+1) begin rr[j]<=0;held[j]<=0;end
        end else begin
            for(j=0;j<5;j=j+1) begin
                if(push[j]) begin fifo[j*DEPTH+wr[j]]<=in_data[j*256+:256];wr[j]<=wr[j]==DEPTH-1?0:wr[j]+1;end
                if(pop[j]) rd[j]<=rd[j]==DEPTH-1?0:rd[j]+1;
                case({push[j],pop[j]})
                    2'b10:count[j]<=count[j]+1;
                    2'b01:count[j]<=count[j]-1;
                    default:count[j]<=count[j];
                endcase
            end
            for(j=0;j<OUTS;j=j+1) begin
                locked[j]<=out_valid[j]&&!out_ready[j];
                if(out_valid[j]&&!out_ready[j]) held[j]<=chosen[j];
                if(out_valid[j]&&out_ready[j]) rr[j]<=chosen[j]==4?0:chosen[j]+1;
            end
        end
    end
endmodule
