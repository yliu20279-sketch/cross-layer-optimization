module noc_fifo #(parameter int WIDTH=260,DEPTH=8)(
 input logic clk,reset,input logic push,pop,input logic [WIDTH-1:0] din,
 output logic [WIDTH-1:0] dout,output logic full,empty,
 output logic [$clog2(DEPTH+1)-1:0] count
);
 localparam int P=$clog2(DEPTH);
 logic [WIDTH-1:0] mem[DEPTH];logic [P-1:0] rd,wr;
 assign full=count==DEPTH;assign empty=count==0;assign dout=mem[rd];
 always_ff @(posedge clk)begin
  if(reset)begin rd<=0;wr<=0;count<=0;end
  else begin
   assert(!(push&&full))else $fatal(1,"FIFO overflow");
   assert(!(pop&&empty))else $fatal(1,"FIFO underflow");
   if(push)begin mem[wr]<=din;wr<=wr==DEPTH-1?0:wr+1'b1;end
   if(pop)rd<=rd==DEPTH-1?0:rd+1'b1;
   case({push,pop})2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:;endcase
  end
 end
 initial assert(DEPTH>=2&&((DEPTH&(DEPTH-1))==0))else $fatal(1,"FIFO depth must be power of two");
endmodule
