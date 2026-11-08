`timescale 1ns/1ps
// Round-robin, retaining an offered flit until downstream accepts it.
module merge_two(
    input wire clk,rst_n,
    input wire [255:0] a_data,b_data,
    input wire a_valid,b_valid,
    output wire a_ready,b_ready,
    output wire [255:0] out_data,
    output wire out_valid,
    input wire out_ready
);
    reg prefer_b,locked,held_b;
    wire choose_b=locked?held_b:(b_valid&&(!a_valid||prefer_b));
    assign out_valid=choose_b?b_valid:a_valid;
    assign out_data=choose_b?b_data:a_data;
    assign a_ready=!choose_b&&out_ready;
    assign b_ready=choose_b&&out_ready;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin prefer_b<=0;locked<=0;held_b<=0;end
        else begin
            locked<=out_valid&&!out_ready;
            if(out_valid&&!out_ready) held_b<=choose_b;
            if(out_valid&&out_ready) prefer_b<=!choose_b;
        end
    end
endmodule
