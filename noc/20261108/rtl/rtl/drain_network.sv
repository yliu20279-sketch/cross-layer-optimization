`timescale 1ns/1ps
// Functional protocol fixture: one shared Mesh for control and data prefixes,
// nine real CS selection modules, bounded destination queues and returned credits.
module drain_network(
    input wire clk,rst_n,
    input wire [255:0] host_request,
    input wire host_valid,
    output wire host_ready,
    output wire [255:0] host_response,
    output wire response_valid,
    input wire response_ready,
    input wire [4095:0] app_data,
    input wire [15:0] app_valid,
    output wire [15:0] app_ready,
    input wire [15:0] sink_ready,
    input wire hold_credit_returns,
    input wire hold_aux_prefix,
    output wire [4095:0] write_data,
    output wire [15:0] write_valid,write_aux,
    output wire [15:0] frozen,gateway_idle,faults,
    output wire [1023:0] accepted,written,
    output wire [255:0] data_epochs,
    output wire [191:0] cs_configs,
    output wire [79:0] tx_configs,rx_configs,
    output wire [31:0] mesh_buffered,
    output wire [15:0] pending_aux_gateways
);
    wire [4095:0] inject,eject,replies,control_injection,admit_data,router_aux_data;
    wire [15:0] router_aux_valid;
    wire [15:0] iv,ir,ev,er,rv,rr,control_iv,control_ir,control_ready,admit_valid,admit_ready;
    wire [15:0] mesh_ready,aux_ready,aux_empty,aux_credit;
    wire [4095:0] aux_data;
    wire [15:0] aux_valid,gateway_valid,gateway_ready,raw_credit;
    wire [2303:0] to_cs_data[0:15],from_cs_data[0:15];
    wire [8:0] to_cs_valid[0:15],from_cs_valid[0:15],to_cs_credit[0:15],from_cs_credit[0:15];
    wire [1023:0] switch_data[0:8],switch_out[0:8];
    wire [3:0] switch_valid[0:8],switch_out_valid[0:8],switch_credit[0:8],switch_return[0:8];
    wire [8:0] switch_legal;
    wire host_packet=eject[255:253]==6;
    assign host_response=eject[255:0];
    assign response_valid=ev[0]&&host_packet;
    wire [255:0] host_mux;
    wire host_mux_valid,host_mux_ready;
    merge_two host_merge(clk,rst_n,host_request,replies[255:0],host_valid,rv[0],host_ready,rr[0],host_mux,host_mux_valid,host_mux_ready);
    assign control_injection[255:0]=host_mux;assign control_iv[0]=host_mux_valid;assign host_mux_ready=control_ir[0];
    aux_mesh mesh(.clk(clk),.rst_n(rst_n),.inject_data(inject),.inject_valid(iv),.inject_ready(ir),
        .eject_data(eject),.eject_valid(ev),.eject_ready(er),
        .aux_data(router_aux_data),.aux_valid(router_aux_valid),.aux_ready(gateway_ready),
        .buffered_flits(mesh_buffered),.pending_aux_gateways(pending_aux_gateways),.hold_aux_prefix(hold_aux_prefix));
    genvar n,c,o;
    generate for(c=0;c<9;c=c+1) begin:cs
        localparam OWNER=4*(c/3)+c%3;
        terminal_switch sw(cs_configs[OWNER*12+:12],switch_data[c],switch_valid[c],switch_credit[c],switch_out[c],switch_out_valid[c],switch_return[c],switch_legal[c]);
        for(o=0;o<4;o=o+1) begin:corners
            localparam N=OWNER+4*(o/2)+o%2;
            assign switch_data[c][o*256+:256]=to_cs_data[N][c*256+:256];
            assign switch_valid[c][o]=to_cs_valid[N][c];
            assign switch_credit[c][o]=to_cs_credit[N][c];
        end
    end
    for(n=0;n<16;n=n+1) begin:nodes
        wire [2:0] typ=eject[n*256+253+:3];
        wire is_control=(typ!=5 && !(n==0 && typ==6));
        wire cfg_valid=ev[n]&&is_control;
        wire cfg_ready;
        wire [255:0] data_out;
        wire write_a;
        wire [31:0] mesh_count,aux_count;
        integer credits;
        reg credit_fault;
        // A stallable reverse pipeline is used for the directed final-credit test.
        // It delays real credit events; it never fabricates a returned credit.
        integer credit_queued;
        wire credit_deliver=!hold_credit_returns&&(credit_queued!=0);
        assign gateway_ready[n]=(credits>0)&&tx_configs[n*5+4];
        assign gateway_valid[n]=router_aux_valid[n]&&gateway_ready[n];
        assign gateway_idle[n]=(credits==4)&&(credit_queued==0)&&!router_aux_valid[n];
        assign er[n]=(n==0 && typ==6)?response_ready:(typ==5?mesh_ready[n]:cfg_ready);
        always @(posedge clk or negedge rst_n) begin
            if(!rst_n) begin credits<=4;credit_queued<=0;credit_fault<=0;end
            else begin
                credits<=credits+credit_deliver-gateway_valid[n];
                credit_queued<=credit_queued+raw_credit[n]-credit_deliver;
                if(credits+credit_deliver-gateway_valid[n]<0 || credits+credit_deliver-gateway_valid[n]>4 ||
                   credit_queued+raw_credit[n]-credit_deliver<0 || (aux_valid[n]&&!aux_ready[n]) ||
                   (ev[n]&&typ==4)) credit_fault<=1;
            end
        end
        managed_endpoint #(.NODE_ID(n)) endpoint(
            .clk(clk),.rst_n(rst_n),.control_in(eject[n*256+:256]),.control_valid(cfg_valid),.control_ready(cfg_ready),
            .control_out(replies[n*256+:256]),.reply_valid(rv[n]),.reply_ready(rr[n]),
            .source_data(app_data[n*256+:256]),.source_valid(app_valid[n]),.source_ready(app_ready[n]),
            .admit_valid(admit_valid[n]),.admit_ready(admit_ready[n]),
            .admit_data(admit_data[n*256+:256]),
            .write_aux(write_valid[n]&&sink_ready[n]&&write_aux[n]),.write_data(write_data[n*256+:256]),
            .gateway_idle(gateway_idle[n]),.aux_empty(aux_empty[n]),.data_fault(credit_fault||!( &switch_legal)),
            .cs_cfg(cs_configs[n*12+:12]),.tx_cfg(tx_configs[n*5+:5]),.rx_cfg(rx_configs[n*5+:5]),
            .frozen(frozen[n]),.fault(faults[n]),.accepted_count(accepted[n*64+:64]),.written_count(written[n*64+:64]),.data_epoch(data_epochs[n*16+:16]));
        if(n>0) begin
            assign control_injection[n*256+:256]=replies[n*256+:256];
            assign control_iv[n]=rv[n];assign rr[n]=control_ir[n];
        end
        merge_two injection_merge(clk,rst_n,control_injection[n*256+:256],admit_data[n*256+:256],control_iv[n],admit_valid[n],
            control_ir[n],admit_ready[n],inject[n*256+:256],iv[n],ir[n]);
        node_selectors #(.NODE_ID(n)) selectors(
            .tx_cfg(tx_configs[n*5+:5]),.rx_cfg(rx_configs[n*5+:5]),
            .tx_data(router_aux_data[n*256+:256]),.tx_valid(gateway_valid[n]),.cs_credit(from_cs_credit[n]),
            .to_cs_data(to_cs_data[n]),.to_cs_valid(to_cs_valid[n]),.tx_credit(raw_credit[n]),
            .from_cs_data(from_cs_data[n]),.from_cs_valid(from_cs_valid[n]),.rx_credit(aux_credit[n]),
            .rx_data(aux_data[n*256+:256]),.rx_valid(aux_valid[n]),.to_cs_credit(to_cs_credit[n]),
            .tx_legal(),.rx_legal(),.unexpected_rx());
        ni_receive receive_queues(clk,rst_n,eject[n*256+:256],aux_data[n*256+:256],ev[n]&&typ==5,aux_valid[n],
            mesh_ready[n],aux_ready[n],aux_credit[n],write_data[n*256+:256],write_valid[n],write_aux[n],sink_ready[n],aux_empty[n],mesh_count,aux_count);
        for(c=0;c<9;c=c+1) begin:branches
            if((n/4==c/3 || n/4==c/3+1)&&(n%4==c%3 || n%4==c%3+1)) begin
                localparam CORNER=2*(n/4-c/3)+(n%4-c%3);
                assign from_cs_data[n][c*256+:256]=switch_out[c][CORNER*256+:256];
                assign from_cs_valid[n][c]=switch_out_valid[c][CORNER];
                assign from_cs_credit[n][c]=switch_return[c][CORNER];
            end else begin
                assign from_cs_data[n][c*256+:256]=0;assign from_cs_valid[n][c]=0;assign from_cs_credit[n][c]=0;
            end
        end
    end endgenerate
endmodule
