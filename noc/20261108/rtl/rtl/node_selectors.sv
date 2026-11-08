// Nine fixed CS bundles; configuration selects one physically adjacent CS.
module node_selectors #(parameter integer NODE_ID=0, W=256)(
    input wire [4:0] tx_cfg, rx_cfg,
    input wire [W-1:0] tx_data,
    input wire tx_valid,
    input wire [8:0] cs_credit,
    output reg [9*W-1:0] to_cs_data,
    output reg [8:0] to_cs_valid,
    output reg tx_credit,
    input wire [9*W-1:0] from_cs_data,
    input wire [8:0] from_cs_valid,
    input wire rx_credit,
    output reg [W-1:0] rx_data,
    output reg rx_valid,
    output reg [8:0] to_cs_credit,
    output wire tx_legal, rx_legal,
    output reg unexpected_rx
);
    integer j;
    function automatic legal(input [4:0] value);
        integer c,r,col;
        begin
            c=value[3:0];r=c/3;col=c%3;
            legal=(value==0) || (value[4] && c<9 &&
                (NODE_ID/4==r || NODE_ID/4==r+1) &&
                (NODE_ID%4==col || NODE_ID%4==col+1));
        end
    endfunction
    assign tx_legal=legal(tx_cfg);
    assign rx_legal=legal(rx_cfg);
    always @* begin
        to_cs_data=0;to_cs_valid=0;tx_credit=0;
        rx_data=0;rx_valid=0;to_cs_credit=0;unexpected_rx=0;
        for(j=0;j<9;j=j+1) begin
            if(tx_legal && tx_cfg[4] && tx_cfg[3:0]==j) begin
                to_cs_data[j*W+:W]=tx_data;to_cs_valid[j]=tx_valid;tx_credit=cs_credit[j];
            end
            if(rx_legal && rx_cfg[4] && rx_cfg[3:0]==j) begin
                rx_data=from_cs_data[j*W+:W];rx_valid=from_cs_valid[j];to_cs_credit[j]=rx_credit;
            end else if(from_cs_valid[j]) unexpected_rx=1;
        end
    end
endmodule
