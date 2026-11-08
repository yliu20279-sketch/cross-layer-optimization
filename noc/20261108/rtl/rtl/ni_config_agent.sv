// New compact-format NI control block. Does not modify the legacy 64-bit module.
// All pending and active registers below are inside the receiving NI.
module ni_config_agent #(
    parameter integer NODE_ID = 0
) (
    input wire clk, rst_n,
    input wire req_valid,
    output wire req_ready,
    input wire [255:0] req_flit,
    input wire aux_frozen, global_drained,
    output reg rsp_valid,
    input wire rsp_ready,
    output reg [2:0] rsp_status,
    output wire [11:0] cs_cfg,
    output wire [4:0] tx_cfg, rx_cfg,
    output wire [35:0] pending_states,
    output wire [47:0] pending_epochs, active_epochs,
    output wire [2:0] pending_valids,
    output wire [156:0] state_snapshot
);
    localparam integer OWN_CS = 3*(NODE_ID/4)+(NODE_ID%4);
    localparam integer HAS_CS = (NODE_ID/4<3 && NODE_ID%4<3);
    localparam [2:0] OK=0, FRAME=1, TARGET=2, OPCODE=3, STATE=4, EPOCH=5, BUSY=6;
    wire [47:0] cmd = req_flit[255:208];
    wire [2:0] typ = cmd[47:45];
    wire [3:0] dst = cmd[44:41];
    wire [1:0] op = cmd[40:39], kind = cmd[38:37];
    wire [3:0] target = cmd[36:33];
    wire [15:0] epoch = cmd[32:17];
    wire [11:0] state = cmd[16:5];
    reg [11:0] pending [0:2];
    reg [11:0] active [0:2];
    reg [15:0] pending_ep [0:2];
    reg [15:0] active_ep [0:2];
    reg [2:0] pending_valid;
    reg [2:0] result;
    integer bank;
    integer k;
    assign req_ready = !rsp_valid || rsp_ready;
    assign cs_cfg=active[0];
    assign tx_cfg=active[1][4:0];
    assign rx_cfg=active[2][4:0];
    assign pending_states={pending[2],pending[1],pending[0]};
    assign pending_epochs={pending_ep[2],pending_ep[1],pending_ep[0]};
    assign active_epochs={active_ep[2],active_ep[1],active_ep[0]};
    assign pending_valids=pending_valid;
    assign state_snapshot={pending_valid,pending_epochs,pending_states,active_epochs,rx_cfg,tx_cfg,cs_cfg};

    function automatic cs_legal(input [11:0] value);
        integer o, chosen, ordinal;
        reg [3:0] used;
        reg [2:0] f;
        begin
            cs_legal=1;used=0;
            for(o=0;o<4;o=o+1) begin
                f=(value>>(3*o))&7;
                if(f!=0) begin
                    if(!f[2] || f[1:0]==3) cs_legal=0;
                    else begin
                        ordinal=f[1:0];
                        chosen=ordinal>=o ? ordinal+1 : ordinal;
                        if(used[chosen]) cs_legal=0;
                        used[chosen]=1;
                    end
                end
            end
        end
    endfunction
    function automatic selector_legal(input [11:0] value);
        integer c, r, col;
        begin
            c=value[3:0];r=c/3;col=c%3;
            selector_legal=(value==0) ||
                (value[11:5]==0 && value[4] && c<9 &&
                 (NODE_ID/4==r || NODE_ID/4==r+1) &&
                 (NODE_ID%4==col || NODE_ID%4==col+1));
        end
    endfunction

    always @* begin
        bank=kind;
        result=OK;
        if(typ!=7 || req_flit[207:0]!=0 || cmd[4:0]!=0) result=FRAME;
        else if(dst!=NODE_ID || kind==3 ||
                (kind==0 && (!HAS_CS || target!=OWN_CS)) ||
                (kind!=0 && target!=NODE_ID)) result=TARGET;
        else if(op!=0 && op!=2) result=OPCODE;
        else if(op==0) begin
            if((kind==0 && !cs_legal(state)) ||
               (kind!=0 && !selector_legal(state))) result=STATE;
            else if(epoch<=active_ep[bank] ||
                    (pending_valid[bank] && epoch!=pending_ep[bank])) result=EPOCH;
        end else begin
            if(state!=0) result=STATE;
            else if(!pending_valid[bank] || epoch!=pending_ep[bank]) result=EPOCH;
            else if(!aux_frozen || !global_drained) result=BUSY;
        end
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            rsp_valid<=0;rsp_status<=OK;pending_valid<=0;
            for(k=0;k<3;k=k+1) begin
                pending[k]<=0;active[k]<=0;pending_ep[k]<=0;active_ep[k]<=0;
            end
        end else begin
            if(rsp_valid && rsp_ready) rsp_valid<=0;
            if(req_valid && req_ready) begin
                rsp_valid<=1;rsp_status<=result;
                if(result==OK) begin
                    if(op==0) begin
                        pending[bank]<=state;pending_ep[bank]<=epoch;pending_valid[bank]<=1;
                    end else begin
                        active[bank]<=pending[bank];active_ep[bank]<=pending_ep[bank];pending_valid[bank]<=0;
                    end
                end
            end
        end
    end
endmodule
