module credit_endpoint #(parameter W=256, DEPTH=4) (
  input wire clk, reset, stop, tx_request, consume, arrival, return_credit,
  input wire [W-1:0] arrival_data,
  output wire inject, credit_out, drained,
  output wire [W-1:0] consumed_data,
  output reg fault
);
  localparam AW=$clog2(DEPTH), CW=$clog2(DEPTH+1);
  reg [CW-1:0] balance, used;
  reg [AW-1:0] head, tail;
  reg [W-1:0] fifo [0:DEPTH-1];
  assign inject=!stop && !reset && tx_request && balance!=0;
  assign credit_out=!reset && consume && used!=0;
  assign consumed_data=fifo[head];
  assign drained=balance==DEPTH && used==0;
  always @(posedge clk) begin
    if(reset) begin
      balance<=DEPTH; used<=0; head<=0; tail<=0; fault<=0;
    end else begin
      if((return_credit && !inject && balance==DEPTH) ||
         (arrival && !credit_out && used==DEPTH)) fault<=1;
      case({return_credit,inject})
        2'b10: balance<=balance+1'b1;
        2'b01: balance<=balance-1'b1;
        default: ;
      endcase
      case({arrival,credit_out})
        2'b10: used<=used+1'b1;
        2'b01: used<=used-1'b1;
        default: ;
      endcase
      if(arrival) begin
        fifo[tail]<=arrival_data;
        tail<=tail==DEPTH-1 ? 0 : tail+1'b1;
      end
      if(credit_out) head<=head==DEPTH-1 ? 0 : head+1'b1;
    end
  end
endmodule
