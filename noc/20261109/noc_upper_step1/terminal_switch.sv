module terminal_switch #(parameter integer W=256)(
    input wire [11:0] active_cfg,
    input wire [4*W-1:0] in_data,
    input wire [3:0] in_valid, downstream_credit,
    output reg [4*W-1:0] out_data,
    output reg [3:0] out_valid, upstream_credit,
    output reg cfg_legal
);
    integer o,i;
    integer selected [0:3];
    reg [2:0] field;
    reg [3:0] used;
    always @* begin
        cfg_legal=1;used=0;out_data=0;out_valid=0;upstream_credit=0;
        field=0;i=0;
        for(o=0;o<4;o=o+1) begin
            selected[o]=-1;
            field=(active_cfg>>(3*o))&7;
            if(field!=0) begin
                if(!field[2] || field[1:0]==3) cfg_legal=0;
                else begin
                    i=(field[1:0]>=o) ? field[1:0]+1 : field[1:0];
                    selected[o]=i;
                    if(used[i]) cfg_legal=0;
                    used[i]=1;
                end
            end
        end
        if(cfg_legal) for(o=0;o<4;o=o+1) begin
            if(selected[o]>=0) begin
                out_data[o*W+:W]=in_data[selected[o]*W+:W];
                out_valid[o]=in_valid[selected[o]];
                upstream_credit[selected[o]]=downstream_credit[o];
            end
        end
    end
endmodule
