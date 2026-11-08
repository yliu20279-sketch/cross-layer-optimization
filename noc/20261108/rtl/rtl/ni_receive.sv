// Functional NI receive queues and a single shared, fair buffer-write port.
// No SRAM bank count, access latency, or cycle-level NoC performance is assumed.
module ni_receive #(parameter integer W=256, DEPTH=4)(
    input wire clk,rst_n,
    input wire [W-1:0] mesh_data,aux_data,
    input wire mesh_valid,aux_valid,
    output wire mesh_ready,aux_ready,
    output wire aux_credit,
    output reg [W-1:0] write_data,
    output reg write_valid,write_aux,
    input wire write_ready,
    output wire aux_empty,
    output wire [31:0] mesh_count,aux_count
);
    reg [W-1:0] mq [0:DEPTH-1];
    reg [W-1:0] aq [0:DEPTH-1];
    integer mr,mw,ar,aw,mc,ac;
    reg prefer_aux;
    reg stalled, stalled_aux;
    wire pop_m=write_valid && write_ready && !write_aux;
    wire pop_a=write_valid && write_ready && write_aux;
    wire push_m=mesh_valid && mesh_ready;
    wire push_a=aux_valid && aux_ready;
    assign mesh_ready=(mc<DEPTH)||pop_m;
    assign aux_ready=(ac<DEPTH)||pop_a;
    assign aux_credit=pop_a;
    assign aux_empty=(ac==0);
    assign mesh_count=mc;
    assign aux_count=ac;
    always @* begin
        write_valid=(mc!=0)||(ac!=0);
        write_aux=stalled ? stalled_aux : (ac!=0)&&((mc==0)||prefer_aux);
        write_data=0;
        if(write_valid) write_data=write_aux ? aq[ar] : mq[mr];
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            mr<=0;mw<=0;ar<=0;aw<=0;mc<=0;ac<=0;prefer_aux<=0;
            stalled<=0;stalled_aux<=0;
        end
        else begin
            if(push_m) begin mq[mw]<=mesh_data;mw<=(mw==DEPTH-1)?0:mw+1;end
            if(push_a) begin aq[aw]<=aux_data;aw<=(aw==DEPTH-1)?0:aw+1;end
            if(pop_m) mr<=(mr==DEPTH-1)?0:mr+1;
            if(pop_a) ar<=(ar==DEPTH-1)?0:ar+1;
            case({push_m,pop_m}) 2'b10:mc<=mc+1;2'b01:mc<=mc-1;default:mc<=mc;endcase
            case({push_a,pop_a}) 2'b10:ac<=ac+1;2'b01:ac<=ac-1;default:ac<=ac;endcase
            if(write_valid&&write_ready) prefer_aux<=!write_aux;
            // Hold both the source selection and FIFO head until accepted.
            stalled<=write_valid&&!write_ready;
            if(write_valid&&!write_ready) stalled_aux<=write_aux;
        end
    end
endmodule
