`timescale 1ns/1ps
module managed_endpoint #(
    parameter integer NODE_ID=0,
    parameter [63:0] COUNTER_LIMIT=64'hffffffffffffffff
)(
    input wire clk,rst_n,
    input wire [255:0] control_in,
    input wire control_valid,
    output wire control_ready,
    output wire [255:0] control_out,
    output wire reply_valid,
    input wire reply_ready,
    input wire [255:0] source_data,
    input wire source_valid,
    output wire source_ready,
    output wire admit_valid,
    output reg [255:0] admit_data,
    input wire admit_ready,
    input wire write_aux,
    input wire [255:0] write_data,
    input wire gateway_idle,aux_empty,data_fault,
    output wire [11:0] cs_cfg,
    output wire [4:0] tx_cfg,rx_cfg,
    output wire frozen,
    output reg fault,
    output reg [63:0] accepted_count,written_count,
    output reg [15:0] data_epoch
);
    localparam [3:0] SELF=NODE_ID;
    localparam HAS_CS=(NODE_ID/4<3 && NODE_ID%4<3);
    reg freeze_request,in_packet,offered,certificate,armed;
    reg [15:0] transition_epoch;
    reg stop_wait,management_valid;
    reg [47:0] stop_header,agent_header;
    reg [255:0] management_reply;
    wire management_ready,agent_ready,agent_reply_valid,agent_reply_ready;
    wire [2:0] agent_status;
    wire [47:0] active_epochs;
    wire [2:0] pending_valids;
    wire [47:0] command=control_in[255:208];
    wire is_management=command[38:37]==3;
    wire is_aux=source_data[255:253]==4;
    wire gate_open=!is_aux || (!fault && (!freeze_request||in_packet||offered));
    assign admit_valid=source_valid&&gate_open;
    assign source_ready=admit_ready&&gate_open;
    wire accepted=source_valid&&source_ready&&is_aux;
    assign frozen=freeze_request&&!in_packet&&!offered;
    // Epoch is a source-NI header field. A head held outside the stopped NI
    // need not carry the previous epoch into the newly configured network.
    always @* begin admit_data=source_data;if(is_aux) admit_data[240:225]=data_epoch;end
    assign control_ready=is_management?(!management_valid&&!stop_wait):agent_ready;
    wire accept_control=control_valid&&control_ready;
    wire [11:0] agent_reply_state={5'd0,SELF,agent_status};
    wire [255:0] agent_reply={3'b110,4'd0,agent_header[40:17],agent_reply_state,5'd0,208'd0};
    ni_config_agent #(.NODE_ID(NODE_ID)) agent(
        .clk(clk),.rst_n(rst_n),.req_flit(control_in),.req_valid(control_valid&&!is_management),.req_ready(agent_ready),
        .aux_frozen(frozen),.global_drained(certificate&&gateway_idle&&aux_empty&&!fault),
        .rsp_valid(agent_reply_valid),.rsp_ready(agent_reply_ready),.rsp_status(agent_status),
        .cs_cfg(cs_cfg),.tx_cfg(tx_cfg),.rx_cfg(rx_cfg),.active_epochs(active_epochs),.pending_valids(pending_valids),
        .state_snapshot(),.pending_states(),.pending_epochs());
    merge_two response_merge(clk,rst_n,agent_reply,management_reply,agent_reply_valid,management_valid,
        agent_reply_ready,management_ready,control_out,reply_valid,reply_ready);
    function [255:0] management_response(input [47:0] header,input [2:0] status);
        reg [255:0] value;
        reg [11:0] state;
        begin
            state={3'd0,header[6:5],SELF,status};
            value={3'b110,4'd0,header[40:17],state,5'd0,208'd0};
            value[63:0]=accepted_count;value[127:64]=written_count;
            value[143:128]=data_epoch;value[144]=frozen;
            value[145]=gateway_idle;value[146]=aux_empty;value[147]=fault;
            management_response=value;
        end
    endfunction
    reg [2:0] result;
    always @* begin
        result=0;
        if(command[47:45]!=7 || command[4:0]!=0 || control_in[207:0]!=0) result=1;
        else if(command[44:41]!=SELF || command[36:33]!=SELF) result=2;
        else if(command[40:39]==0) begin
            if(command[16:5]!=0) result=4;
            else if(command[32:17]<transition_epoch ||
                    (command[32:17]==transition_epoch && !freeze_request)) result=5;
        end else if(command[32:17]!=transition_epoch) result=5;
        else if(!frozen || fault) result=6;
        else case(command[40:39])
            1:if(command[16:5]>1) result=4;
            2:if(command[16:5]!=0) result=4;else if(!gateway_idle||!aux_empty) result=6;
            3:begin
                if(command[16:5]>1) result=4;
                else if(!certificate) result=6;
                // During RUN, earlier released sources may already use this
                // node as gateway/destination in the fully armed new epoch.
                else if(command[16:5]==0 && !(armed&&data_epoch==transition_epoch) && (!gateway_idle || !aux_empty)) result=6;
                else if(command[16:5]==0 &&
                    (active_epochs[31:16]!=transition_epoch || active_epochs[47:32]!=transition_epoch ||
                    (HAS_CS && active_epochs[15:0]!=transition_epoch) || pending_valids!=0)) result=5;
                else if(command[16:5]==1 && (!armed || data_epoch!=transition_epoch)) result=5;
            end
        endcase
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            freeze_request<=1;in_packet<=0;offered<=0;certificate<=0;armed<=0;transition_epoch<=0;data_epoch<=0;
            accepted_count<=0;written_count<=0;fault<=0;stop_wait<=0;management_valid<=0;
            stop_header<=0;agent_header<=0;management_reply<=0;
        end else begin
            if(data_fault) fault<=1;
            offered<=admit_valid&&!admit_ready&&is_aux;
            if(management_valid&&management_ready) management_valid<=0;
            if(accepted) begin
                accepted_count<=accepted_count+1;
                in_packet<=!source_data[191];
                if(accepted_count==COUNTER_LIMIT ||
                    (!in_packet&&!source_data[192]) || (in_packet&&source_data[192])) fault<=1;
            end
            if(write_aux) begin
                written_count<=written_count+1;
                if(written_count==COUNTER_LIMIT || write_data[240:225]!=data_epoch ||
                   write_data[248:245]!=SELF || write_data[255:253]!=4) fault<=1;
            end
            if(stop_wait&&frozen) begin
                management_reply<=management_response(stop_header,0);management_valid<=1;stop_wait<=0;
            end
            if(accept_control) begin
                if(!is_management) agent_header<=command;
                else if(result!=0) begin
                    management_reply<=management_response(command,result);management_valid<=1;
                end else case(command[40:39])
                    0:begin
                        freeze_request<=1;certificate<=0;armed<=0;
                        transition_epoch<=command[32:17];stop_header<=command;stop_wait<=1;
                    end
                    1:begin management_reply<=management_response(command,0);management_valid<=1;end
                    2:begin certificate<=1;management_reply<=management_response(command,0);management_valid<=1;end
                    3:begin
                        if(command[16:5]==0) begin
                            if(!armed || data_epoch!=transition_epoch) begin
                                data_epoch<=transition_epoch;accepted_count<=0;written_count<=0;
                            end
                            armed<=1;
                        end else begin freeze_request<=0;armed<=0;certificate<=0;end
                        management_reply<=management_response(command,0);management_valid<=1;
                    end
                endcase
            end
        end
    end
endmodule
