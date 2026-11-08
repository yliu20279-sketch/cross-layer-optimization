`timescale 1ns/1ps
module tb_management;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;
    reg [255:0] request=0,source_data=0,wdata=0;
    reg valid=0,source_valid=0,write_aux=0,gateway_idle=1,aux_empty=1;
    wire ready,reply_valid,source_ready,admit_valid,frozen,fault;
    wire [255:0] reply,admit_data;
    wire [63:0] accepted,written;
    wire [15:0] epoch;
    wire [11:0] cs;
    wire [4:0] tx,rx;
    managed_endpoint #(.NODE_ID(5),.COUNTER_LIMIT(64'd15)) dut(
        .clk(clk),.rst_n(rst_n),.control_in(request),.control_valid(valid),.control_ready(ready),
        .control_out(reply),.reply_valid(reply_valid),.reply_ready(1'b1),
        .source_data(source_data),.source_valid(source_valid),.source_ready(source_ready),.admit_valid(admit_valid),.admit_data(admit_data),.admit_ready(1'b1),
        .write_aux(write_aux),.write_data(wdata),.gateway_idle(gateway_idle),.aux_empty(aux_empty),.data_fault(1'b0),
        .cs_cfg(cs),.tx_cfg(tx),.rx_cfg(rx),.frozen(frozen),.fault(fault),.accepted_count(accepted),.written_count(written),.data_epoch(epoch));
    task command(input integer kind,op,ep,state,status);
        reg [47:0] c;
        integer target,waits;
        begin
            target=kind==0?4:5;
            c=(48'd7<<45)|(48'd5<<41)|(op*48'd1<<39)|(kind*48'd1<<37)|(target*48'd1<<33)|(ep*48'd1<<17)|(state*48'd1<<5);
            @(negedge clk);request={c,208'd0};valid=1;
            @(posedge clk);if(!ready) $fatal(1,"management unit request blocked");
            @(negedge clk);valid=0;
            waits=0;
            while(!reply_valid) begin @(negedge clk);waits=waits+1;if(waits>20) $fatal(1,"management unit response timeout");end
            if(reply[215:213]!==status[2:0]) $fatal(1,"management unit status op=%0d kind=%0d got=%0d expected=%0d",op,kind,reply[215:213],status);
            @(posedge clk);@(negedge clk);
        end
    endtask
    integer i;
    initial begin
        repeat(2) @(negedge clk);rst_n=1;
        command(0,0,1,0,0);command(1,0,1,20,0);command(2,0,1,20,0);
        command(3,0,1,0,0);command(3,2,1,0,0);
        command(0,2,1,0,0);command(1,2,1,0,0);command(2,2,1,0,0);
        command(3,3,1,0,0);
        // A fully armed destination can receive new-epoch data before its own RUN.
        @(negedge clk);wdata=0;wdata[255:253]=4;wdata[248:245]=5;wdata[240:225]=1;write_aux=1;
        @(negedge clk);write_aux=0;gateway_idle=0;aux_empty=0;
        command(3,3,1,0,0);
        if(written!=1||epoch!=1||!frozen) $fatal(1,"duplicate ARM erased new-epoch state");
        command(3,3,1,1,0);
        if(frozen) $fatal(1,"RUN rejected incoming new-epoch activity");
        gateway_idle=1;aux_empty=1;
        for(i=0;i<16;i=i+1) begin
            @(negedge clk);source_data=0;source_data[255:253]=4;source_data[192:191]=3;source_valid=1;
            @(posedge clk);if(!source_ready||admit_data[240:225]!=1) $fatal(1,"source epoch stamping or threshold setup failed");
        end
        @(negedge clk);source_valid=0;
        if(!fault||accepted!=16||source_ready) $fatal(1,"counter limit did not fail closed");
        command(3,0,2,0,0);command(1,0,2,20,0);command(1,2,2,0,6);
        if(!fault||!frozen) $fatal(1,"counter fault cleared or resumed");
        $display("PASS management duplicate_arm_preserved_count=1 run_with_new_epoch_activity=1 counter_limit=15 commit_blocked_after_fault=1");
        $finish;
    end
endmodule
