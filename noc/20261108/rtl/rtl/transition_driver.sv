`timescale 1ns/1ps
// Hardware-executable model of the host control program, not an allocator.
// The CPU would run these barriers after computing the input configuration.
module transition_driver #(parameter integer TIMEOUT=20000)(
    input wire clk,rst_n,start,
    input wire [15:0] next_epoch,
    input wire [107:0] next_cs,
    input wire [79:0] next_tx,next_rx,
    output reg [255:0] request,
    output wire request_valid,
    input wire request_ready,
    input wire [255:0] response,
    input wire response_valid,
    output wire response_ready,
    output wire done,failed,
    output reg [3:0] phase,
    output reg [31:0] ignored_responses,
    output reg [31:0] count_rounds,credit_rounds
);
    localparam IDLE=0,LOAD=1,STOP=2,COUNTS=3,CREDITS=4,CERT=5,COMMIT=6,ARM=7,RUN=8,DONE=9,ERROR=10;
    reg [15:0] epoch,current_epoch;
    reg [107:0] saved_cs;
    reg [79:0] saved_tx,saved_rx;
    integer sent,received,timer;
    reg [40:0] seen;
    reg [67:0] sum_a,sum_w;
    reg all_idle;
    integer number,node,target,kind,opcode,state,csid;
    reg [47:0] command;
    assign done=phase==DONE;
    assign failed=phase==ERROR;
    assign request_valid=(phase>=LOAD&&phase<=RUN)&&(sent<number);
    assign response_ready=phase!=IDLE;
    always @* begin
        number=(phase==LOAD||phase==COMMIT)?41:16;
        node=sent;target=sent;kind=3;opcode=0;state=0;csid=0;
        if(phase==LOAD||phase==COMMIT) begin
            opcode=phase==LOAD?0:2;
            if(sent<9) begin
                csid=sent;node=4*(sent/3)+sent%3;target=sent;kind=0;
                if(phase==LOAD) state=saved_cs[sent*12+:12];
            end else if(sent<25) begin
                node=sent-9;target=node;kind=1;
                if(phase==LOAD) state=saved_tx[node*5+:5];
            end else begin
                node=sent-25;target=node;kind=2;
                if(phase==LOAD) state=saved_rx[node*5+:5];
            end
        end else case(phase)
            STOP:opcode=0;
            COUNTS:opcode=1;
            CREDITS:begin opcode=1;state=1;end
            CERT:opcode=2;
            ARM:opcode=3;
            RUN:begin opcode=3;state=1;end
        endcase
        command=(48'd7<<45)|(node*48'd1<<41)|(opcode*48'd1<<39)|(kind*48'd1<<37)|
                (target*48'd1<<33)|(epoch*48'd1<<17)|(state*48'd1<<5);
        request={command,208'd0};
    end
    integer reply_index,reply_node,reply_kind,reply_target,reply_opcode,expected_op,expected_subtype,owner;
    reg header_match;
    always @* begin
        reply_node=response[219:216];reply_kind=response[246:245];reply_target=response[244:241];
        reply_opcode=response[248:247];reply_index=-1;owner=0;expected_op=0;expected_subtype=0;
        if(phase==LOAD||phase==COMMIT) begin
            expected_op=phase==LOAD?0:2;
            if(reply_kind==0 && reply_target<9) begin
                reply_index=reply_target;owner=4*(reply_target/3)+reply_target%3;
            end else if(reply_kind==1) begin reply_index=9+reply_target;owner=reply_target;end
            else if(reply_kind==2) begin reply_index=25+reply_target;owner=reply_target;end
        end else begin
            if(reply_kind==3 && reply_target==reply_node) reply_index=reply_node;
            owner=reply_node;
            case(phase)
                STOP:expected_op=0;
                COUNTS:expected_op=1;
                CREDITS:begin expected_op=1;expected_subtype=1;end
                CERT:expected_op=2;
                ARM:expected_op=3;
                RUN:begin expected_op=3;expected_subtype=1;end
            endcase
        end
        header_match=response[255:253]==6 && response[252:249]==0 && response[240:225]==epoch &&
            reply_opcode==expected_op && response[221:220]==expected_subtype && reply_node==owner &&
            reply_index>=0 && reply_index<number;
    end
    task new_phase(input [3:0] next);
        begin phase<=next;sent<=0;received<=0;seen<=0;sum_a<=0;sum_w<=0;all_idle<=1;end
    endtask
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            phase<=IDLE;epoch<=0;current_epoch<=0;saved_cs<=0;saved_tx<=0;saved_rx<=0;
            sent<=0;received<=0;seen<=0;timer<=0;sum_a<=0;sum_w<=0;all_idle<=1;
            ignored_responses<=0;count_rounds<=0;credit_rounds<=0;
        end else if(start&&(phase==IDLE||phase==DONE)) begin
            if(next_epoch<=current_epoch) phase<=ERROR;
            else begin
                epoch<=next_epoch;saved_cs<=next_cs;saved_tx<=next_tx;saved_rx<=next_rx;timer<=0;
                count_rounds<=0;credit_rounds<=0;new_phase(LOAD);
            end
        end else if(phase>=LOAD&&phase<=RUN) begin
            timer<=timer+1;
            if(request_valid&&request_ready) sent<=sent+1;
            if(response_valid&&response_ready) begin
                if(!header_match) ignored_responses<=ignored_responses+1;
                else if(seen[reply_index]) ignored_responses<=ignored_responses+1;
                else if(response[215:213]!=0 || (reply_kind==3&&response[147])) phase<=ERROR;
                else begin
                    seen[reply_index]<=1;received<=received+1;
                    if(phase==COUNTS) begin
                        if(!response[144] || response[143:128]!=current_epoch) phase<=ERROR;
                        sum_a<=sum_a+response[63:0];sum_w<=sum_w+response[127:64];
                    end
                    if(phase==CREDITS) all_idle<=all_idle&&response[144]&&response[145]&&response[146];
                    if(received+1==number) begin
                        case(phase)
                            LOAD:new_phase(STOP);
                            STOP:new_phase(COUNTS);
                            COUNTS:begin
                                count_rounds<=count_rounds+1;
                                if(!response[144] || response[143:128]!=current_epoch ||
                                   sum_w+response[127:64]>sum_a+response[63:0]) phase<=ERROR;
                                else if(sum_w+response[127:64]==sum_a+response[63:0]) new_phase(CREDITS);
                                else new_phase(COUNTS);
                            end
                            CREDITS:begin
                                credit_rounds<=credit_rounds+1;
                                if(all_idle&&response[144]&&response[145]&&response[146]) new_phase(CERT);
                                else new_phase(CREDITS);
                            end
                            CERT:new_phase(COMMIT);
                            COMMIT:new_phase(ARM);
                            ARM:new_phase(RUN);
                            RUN:begin current_epoch<=epoch;new_phase(DONE);end
                        endcase
                    end
                end
            end
            if(timer>=TIMEOUT) phase<=ERROR;
        end
    end
endmodule
