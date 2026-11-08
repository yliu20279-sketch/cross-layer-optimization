`timescale 1ns/1ps
module tb_transition;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,start=0;
    reg [15:0] next_epoch=1;
    reg [107:0] qcs=0;
    reg [79:0] qtx=0,qrx=0;
    wire [255:0] request,net_response;
    wire req_valid,req_ready,net_valid,driver_ready,done,failed;
    wire [3:0] phase;
    wire [31:0] ignored,count_rounds,credit_rounds;
    reg inject_stale=0;
    wire [255:0] stale_response={3'b110,4'd0,2'd1,2'd3,4'd0,16'd1,12'h080,5'd0,208'd0};
    transition_driver #(.TIMEOUT(6000)) driver(clk,rst_n,start,next_epoch,qcs,qtx,qrx,request,req_valid,req_ready,
        inject_stale?stale_response:net_response,inject_stale||net_valid,driver_ready,done,failed,phase,ignored,count_rounds,credit_rounds);
    reg [4095:0] app_data=0;
    reg [15:0] app_valid=0,sink_ready=0;
    reg hold_credit=0,hold_prefix=0;
    wire [15:0] app_ready,write_valid,write_aux,frozen,gateway_idle,faults;
    wire [4095:0] write_data;
    wire [1023:0] accepted,written;
    wire [255:0] epochs;
    wire [191:0] cs_configs;
    wire [79:0] tx_configs,rx_configs;
    wire [31:0] buffered;
    wire [15:0] pending_aux_gateways;
    drain_network network(clk,rst_n,request,req_valid,req_ready,net_response,net_valid,driver_ready&&!inject_stale,
        app_data,app_valid,app_ready,sink_ready,hold_credit,hold_prefix,write_data,write_valid,write_aux,
        frozen,gateway_idle,faults,accepted,written,epochs,cs_configs,tx_configs,rx_configs,buffered,pending_aux_gateways);
    integer seq[0:15];
    reg [8191:0] pending=0;
    reg [255:0] expected[0:8191];
    integer target[0:8191];
    integer n,id,cycle=0,injected=0,retired=0,aux_in=0,aux_out=0;
    integer trace;
    integer count_wait=0,credit_wait=0,prefix_wait=0,tail_finishes=0,ordinary_frozen=0;
    reg [67:0] total_a,total_w;
    reg monitor=0;
    integer pause_writes_until=0;
    integer last_for_src[0:15];
    function [255:0] payload(input integer src,index);
        integer g,d;
        reg [31:0] word;
        reg [255:0] value;
        begin
            g=src^4;d=g^1;word=32'h1a200000+src*512+index;value={8{word}};
            value[255:253]=src==15?5:4;value[252:249]=src==15?0:g;
            value[248:245]=src==15?0:d;value[244:241]=src;value[240:225]=0;
            value[224:193]=src*512+index;
            value[192]=src==15 || index%3==0;value[191]=src==15 || index%3==2;
            payload=value;
        end
    endfunction
    task configuration(input integer which);
        integer c,node,row,col;
        begin
            qcs=0;qtx=0;qrx=0;
            if(which==1) begin
                qcs[0*12+:12]=12'hda4;qcs[2*12+:12]=12'hda4;
                qcs[6*12+:12]=12'hda4;qcs[8*12+:12]=12'hda4;
            end else begin
                qcs[0*12+:12]=12'h024;qcs[2*12+:12]=12'h024;
                qcs[3*12+:12]=12'hda4;qcs[5*12+:12]=12'hda4;
                qcs[6*12+:12]=12'hd80;qcs[8*12+:12]=12'hd80;
            end
            for(node=0;node<16;node=node+1) begin
                row=node/4;col=node%4;
                if(which==1) c=(row<2?0:6)+(col<2?0:2);
                else c=(row==0?0:(row==3?6:3))+(col<2?0:2);
                qtx[node*5+:5]=16+c;qrx[node*5+:5]=16+c;
            end
        end
    endtask
    always @* begin
        total_a=0;total_w=0;
        for(integer j=0;j<16;j=j+1) begin
            total_a=total_a+accepted[j*64+:64];total_w=total_w+written[j*64+:64];
        end
    end
    always @(negedge clk) begin
        if(rst_n&&monitor) begin
            for(integer j=0;j<16;j=j+1) begin
                app_valid[j]=seq[j]<192;
                app_data[j*256+:256]=payload(j,seq[j]);
                sink_ready[j]=(cycle>=pause_writes_until)&&((cycle+j*2)%7==0);
            end
        end
    end
    reg [255:0] assembled;
    always @(posedge clk) begin
        if(rst_n&&monitor) begin
            cycle=cycle+1;
            for(integer j=0;j<16;j=j+1) begin
                if(app_valid[j]&&app_ready[j]) begin
                    id=j*512+seq[j];assembled=app_data[j*256+:256];
                    if(j!=15) assembled[240:225]=epochs[j*16+:16];
                    if(pending[id]) $fatal(1,"duplicate source admission");
                    expected[id]=assembled;target[id]=j==15?0:((j^4)^1);pending[id]=1;
                    seq[j]=seq[j]+1;injected=injected+1;if(j!=15) aux_in=aux_in+1;
                    if(j==15&&frozen[j]&&phase>=2&&phase<=7) ordinary_frozen=ordinary_frozen+1;
                end
                if(write_valid[j]&&sink_ready[j]) begin
                    id=write_data[j*256+193+:32];
                    if(id<0||id>=8192||!pending[id]||target[id]!=j||expected[id]!==write_data[j*256+:256]) $fatal(1,"lost/duplicate/corrupt/misrouted data id=%0d dest=%0d",id,j);
                    if(id%512<=last_for_src[id/512]) $fatal(1,"per-source reorder");
                    last_for_src[id/512]=id%512;
                    pending[id]=0;retired=retired+1;if(write_aux[j]) aux_out=aux_out+1;
                end
            end
            if(phase==3&&total_a>total_w) count_wait=count_wait+1;
            if(phase==4&&gateway_idle!=16'hffff) credit_wait=credit_wait+1;
            // Inspect actual occupied Mesh FIFOs, and match each packet's own
            // forwarding node to its idle state (not an unrelated idle gateway).
            if(phase>=2&&phase<=3&&total_a>total_w&&|(pending_aux_gateways&gateway_idle)) begin
                prefix_wait=prefix_wait+1;
                $fdisplay(trace,"PREFIX_WAIT t=%0t phase=%0d pending_gateways=%h idle_gateways=%h A=%0d W=%0d",$time,phase,pending_aux_gateways,gateway_idle,total_a,total_w);
            end
            if(req_valid&&req_ready&&request[246:245]!=3&&request[248:247]==2)
                if(frozen!=16'hffff||gateway_idle!=16'hffff||total_a!=total_w) $fatal(1,"unsafe COMMIT");
            if(faults!=0) $fatal(1,"network protocol/data fault %h",faults);
        end
    end
    generate for(genvar j=0;j<15;j=j+1) begin:tail_monitors
        always @(posedge clk) if(rst_n&&monitor&&network.nodes[j].endpoint.freeze_request&&network.nodes[j].endpoint.in_packet&&app_valid[j]&&app_ready[j]&&app_data[j*256+191])
            tail_finishes=tail_finishes+1;
    end endgenerate
    integer guard,hold_cycles;
    reg fail_mode;
    reg [191:0] old_cs;
    initial begin
        fail_mode=$test$plusargs("FAIL_MODE");
        $dumpfile(fail_mode?"build/timeout.vcd":"build/transition.vcd");
        $dumpvars(0,phase,frozen,gateway_idle,pending_aux_gateways,total_a,total_w,cs_configs,epochs,hold_credit,hold_prefix,sink_ready);
        trace=$fopen(fail_mode?"build/timeout_trace.log":"build/transition_trace.log","w");
        for(n=0;n<16;n=n+1) begin seq[n]=0;last_for_src[n]=-1;end
        repeat(3) @(negedge clk);rst_n=1;monitor=1;
        configuration(1);start=1;
        @(negedge clk);start=0;
        guard=0;
        while(!done&&!failed) begin @(negedge clk);guard=guard+1;if(guard>8000) $fatal(1,"bootstrap timeout");end
        if(failed) $fatal(1,"bootstrap failed phase=%0d",phase);
        repeat(40) @(negedge clk);
        old_cs=cs_configs;configuration(2);next_epoch=2;start=1;
        @(negedge clk);start=0;
        while(phase!=2&&!failed) @(negedge clk);
        if(failed) $fatal(1,"failed before STOP");
        // Delay an actual data flit on link 0->4. Gateway 4 can drain its
        // previous FIFO/credits while this already admitted old prefix remains.
        hold_prefix=1;repeat(80) @(negedge clk);hold_prefix=0;
        guard=0;
        while(!(frozen==16'hffff&&total_a>total_w)) begin
            @(negedge clk);guard=guard+1;
            if(failed||guard>5000) $fatal(1,"no in-flight data at freeze completion");
        end
        pause_writes_until=cycle+160;sink_ready=0;
        // Catch the final real reverse credit after all old data reached buffer.
        guard=0;
        while(!(frozen==16'hffff&&total_a==total_w&&total_a>0&&gateway_idle!=16'hffff)) begin
            @(negedge clk);guard=guard+1;
            if(failed||guard>5000) $fatal(1,"did not reach final-credit window phase=%0d",phase);
        end
        hold_credit=1;
        while(phase!=4&&!failed) @(negedge clk);
        if(failed) $fatal(1,"failed before credit barrier");
        // A late old-epoch success may not satisfy the current credit barrier.
        inject_stale=1;@(negedge clk);inject_stale=0;
        if(fail_mode) begin
            while(!failed) @(negedge clk);
            if(frozen!=16'hffff||cs_configs!==old_cs||done) $fatal(1,"timeout changed config or resumed");
            hold_credit=0;
            repeat(150) @(negedge clk);
            if(!failed||frozen!=16'hffff||cs_configs!==old_cs) $fatal(1,"timeout was not fail-closed");
            $display("PASS timeout frozen=16 old_config_retained=1 ignored_stale=%0d credit_wait_cycles=%0d",ignored,credit_wait);
            $finish;
        end
        repeat(120) begin
            @(negedge clk);
            if(phase!=4||cs_configs!==old_cs) $fatal(1,"submitted before final credit returned");
        end
        hold_credit=0;
        guard=0;
        while(!done&&!failed) begin @(negedge clk);guard=guard+1;if(guard>8000) $fatal(1,"transition timeout");end
        if(failed||ignored<1) $fatal(1,"transition/stale filtering failed");
        guard=0;
        while(retired<3072) begin @(negedge clk);guard=guard+1;if(guard>20000) $fatal(1,"data drain timeout in=%0d out=%0d",injected,retired);end
        repeat(20) @(negedge clk);
        if(injected!=3072||retired!=3072||aux_in!=aux_out||pending!=0||gateway_idle!=16'hffff||count_wait==0||credit_wait==0||prefix_wait==0||tail_finishes==0||ordinary_frozen==0)
            $fatal(1,"coverage/conservation missing counts=%0d credit=%0d prefix=%0d tail=%0d normal=%0d",count_wait,credit_wait,prefix_wait,tail_finishes,ordinary_frozen);
        for(n=0;n<16;n=n+1) if(epochs[n*16+:16]!=2) $fatal(1,"new epoch missing");
        $display("PASS transition injected=%0d retired=%0d aux=%0d count_wait=%0d credit_wait=%0d prefix_wait=%0d tail_finishes=%0d normal_during_freeze=%0d ignored_stale=%0d",injected,retired,aux_out,count_wait,credit_wait,prefix_wait,tail_finishes,ordinary_frozen,ignored);
        $finish;
    end
    always @(posedge clk) if(rst_n) begin
        if(req_valid&&req_ready) $fdisplay(trace,"REQ t=%0t phase=%0d node=%0d op=%0d kind=%0d target=%0d epoch=%0d state=%h",$time,phase,request[252:249],request[248:247],request[246:245],request[244:241],request[240:225],request[224:213]);
        if(net_valid&&driver_ready&&!inject_stale) $fdisplay(trace,"RSP t=%0t phase=%0d node=%0d op=%0d kind=%0d target=%0d epoch=%0d status=%0d body=%h",$time,phase,net_response[219:216],net_response[248:247],net_response[246:245],net_response[244:241],net_response[240:225],net_response[215:213],net_response[147:0]);
    end
endmodule
