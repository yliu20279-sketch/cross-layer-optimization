`timescale 1ns/1ps
module tb_aux_router;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;
    reg [1279:0] din=0;
    reg [4:0] vin=0;
    reg [5:0] ready=63;
    wire [4:0] ir,baseline_ir;
    wire [1535:0] dout;
    wire [1279:0] baseline_data;
    wire [5:0] valid;
    wire [4:0] baseline_valid;
    wire [31:0] count;
`ifdef MAPPED_ROUTER
    router_aux_top router(.clk(clk),.rst_n(rst_n),.in_data(din),.in_valid(vin),.in_ready(ir),
        .out_data(dout),.out_valid(valid),.out_ready(ready));
    router_local_top baseline(.clk(clk),.rst_n(rst_n),.in_data(din),.in_valid(vin),.in_ready(baseline_ir),
        .out_data(baseline_data),.out_valid(baseline_valid),.out_ready(ready[4:0]));
`else
    aux_xy_router #(.NODE_ID(5)) router(.clk(clk),.rst_n(rst_n),.in_data(din),.in_valid(vin),.in_ready(ir),
        .out_data(dout),.out_valid(valid),.out_ready(ready),.buffered_flits(count),.pending_aux_gateways());
    aux_xy_router #(.NODE_ID(5),.ENABLE_AUX(0)) baseline(.clk(clk),.rst_n(rst_n),.in_data(din),.in_valid(vin),.in_ready(baseline_ir),
        .out_data(baseline_data),.out_valid(baseline_valid),.out_ready(ready[4:0]),.buffered_flits(),.pending_aux_gateways());
`endif
    function [255:0] packet(input integer typ,dest,tag);
        reg [31:0] word;
        reg [255:0] value;
        begin word=32'h8145ab00+tag;value={8{word}};value[255:253]=typ;value[252:249]=dest;value[31:0]=tag;packet=value;end
    endfunction
    task reset;
        begin @(negedge clk);rst_n=0;vin=0;ready=63;din=0;repeat(2) @(negedge clk);rst_n=1;end
    endtask
    task inject(input integer portid,input [255:0] p);
        integer timeout;
        begin
            @(negedge clk);din[portid*256+:256]=p;vin=1<<portid;
            timeout=0;
            @(posedge clk);
            while(!ir[portid]) begin @(posedge clk);timeout=timeout+1;if(timeout>20) $fatal(1,"router injection timeout");end
            @(negedge clk);vin=0;
        end
    endtask
    integer routes[0:15];
    integer p,d,typ,portid,cases=0,k,bitid;
    reg [255:0] expected,held;
    initial begin
        routes[0]=4;routes[1]=1;routes[2]=2;routes[3]=2;
        routes[4]=4;routes[5]=0;routes[6]=2;routes[7]=2;
        routes[8]=4;routes[9]=3;routes[10]=2;routes[11]=2;
        routes[12]=4;routes[13]=3;routes[14]=2;routes[15]=2;
        reset;
        // Distinct input queues, independent local and auxiliary output arbiters.
        @(negedge clk);vin=5'b10010;
        din[256+:256]=packet(7,5,1);din[1024+:256]=packet(4,5,2);
        @(posedge clk);#1;
        if(valid!==6'b100001 || dout[0+:256]!==packet(7,5,1) || dout[1280+:256]!==packet(4,5,2)) $fatal(1,"Local/AUX are not simultaneous independent outputs");
        if(baseline_valid!==5'b00001) $fatal(1,"baseline did not serialize on local output");
        @(negedge clk);vin=0;
        @(posedge clk);#1;
        if(valid!=0 || baseline_valid!==1 || baseline_data[0+:256]!==packet(4,5,2)) $fatal(1,"parallel/baseline completion mismatch");
        reset;
        ready[5]=0;
        inject(4,packet(4,5,20));held=packet(4,5,20);
        for(k=0;k<8;k=k+1) begin
            inject(1,packet(7,5,100+k));#1;
            if(!valid[0] || !valid[5] || dout[0+:256]!==packet(7,5,100+k) || dout[1280+:256]!==held) $fatal(1,"blocked AUX impeded another input's local packet");
            @(posedge clk);#1;
            if(valid[0] || !valid[5] || dout[1280+:256]!==held) $fatal(1,"AUX stability/local retirement mismatch");
        end
        @(negedge clk);ready[5]=1;
        @(posedge clk);#1;if(valid!=0) $fatal(1,"AUX did not complete");
        // A single input FIFO is still head-of-line blocked; no invented VC.
        reset;ready[5]=0;
        inject(4,packet(4,5,30));inject(4,packet(7,5,31));
        repeat(3) begin #1;if(valid[0] || !valid[5]) $fatal(1,"same-input FIFO was bypassed without hardware");@(negedge clk);end
        ready[5]=1;@(posedge clk);#1;
        if(!valid[0] || dout[0+:256]!==packet(7,5,31)) $fatal(1,"same-input ordering mismatch");
        @(posedge clk);#1;
        reset;
        for(p=0;p<5;p=p+1) for(d=0;d<16;d=d+1) for(typ=4;typ<=5;typ=typ+1) begin
            portid=(d==5&&typ==4)?5:routes[d];expected=packet(typ,d,p*32+d*2+typ-4);
            inject(p,expected);#1;
            if(valid!==(6'b1<<portid) || dout[portid*256+:256]!==expected) $fatal(1,"route/bit mismatch input=%0d dest=%0d type=%0d",p,d,typ);
            @(posedge clk);#1;
            if(valid!=0) $fatal(1,"lost/double dequeue");
`ifndef MAPPED_ROUTER
            if(count!=0) $fatal(1,"nonempty RTL FIFO after retirement");
`endif
            cases=cases+1;
        end
        // Walk all payload bit positions for each input and both destination exits.
        for(p=0;p<5;p=p+1) for(typ=4;typ<=5;typ=typ+1) for(bitid=0;bitid<249;bitid=bitid+1) begin
            expected=0;expected[255:253]=typ;expected[252:249]=5;expected[bitid]=1;
            portid=typ==4?5:0;
            inject(p,expected);#1;
            if(valid!==(6'b1<<portid) || dout[portid*256+:256]!==expected) $fatal(1,"walking-bit mismatch");
            @(posedge clk);#1;
        end
        $display("PASS aux_router route_cases=%0d payload_walks=2490 local_aux_parallel=1 controls_while_aux_blocked=8 same_input_HOL_verified=1",cases);
        $finish;
    end
endmodule
