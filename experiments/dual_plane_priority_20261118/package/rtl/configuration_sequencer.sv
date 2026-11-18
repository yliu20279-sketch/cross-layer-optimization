module configuration_sequencer(
 input logic clk,reset,start,input logic [77:0] plan,input logic [15:0] version,
 output logic ready,busy,done,error,
 input logic cs_idle,input logic [15:0] pause_ack,
 output logic command_valid,input logic command_ready,
 output logic [3:0] command_dst,command_target,output logic [2:0] command_action,
 output logic [5:0] command_state,output logic [15:0] command_version,
 output logic [31:0] command_id,
 input logic ack_valid,ack_ok,input logic [31:0] ack_id
);
 localparam int IDLE=0,ISSUE=1,WAIT_ACK=2,DRAIN=3,FINISH=4,FAILED=5;
 logic [2:0] state,phase;logic [3:0] index;
 logic [77:0] saved;logic [15:0] saved_version;logic [31:0] next_id,expected_id;
 function automatic logic [3:0] owner(input int c);
  if(c<9)return 4'(4*(c/3)+c%3);
  case(c)9:return 0;10:return 2;11:return 8;default:return 10;endcase
 endfunction
 always_comb begin
  ready=state==IDLE||state==FINISH||state==FAILED;
  busy=!ready;done=state==FINISH||state==FAILED;error=state==FAILED;
  command_valid=state==ISSUE;command_dst=index;command_target=0;command_state=0;
  command_version=saved_version;command_id=next_id;
  case(phase)
   0:command_action=0;
   1:begin command_action=1;command_dst=owner(index);command_target=index;command_state=saved[index*6+:6];end
   2:begin command_action=2;command_dst=0;end
   3:command_action=3;
   default:command_action=4;
  endcase
 end
 always_ff @(posedge clk)begin
  if(reset)begin state<=IDLE;phase<=0;index<=0;saved<=0;saved_version<=0;next_id<=32'hc0000000;expected_id<=0;end
  else case(state)
   IDLE,FINISH,FAILED:if(start)begin saved<=plan;saved_version<=version;phase<=0;index<=0;state<=ISSUE;end
   ISSUE:if(command_ready)begin expected_id<=next_id;next_id<=next_id+1'b1;state<=WAIT_ACK;end
   WAIT_ACK:if(ack_valid)begin
    if(ack_id!=expected_id||!ack_ok)state<=FAILED;
    else if(phase==0&&index==15)begin state<=DRAIN;index<=0;phase<=1;end
    else if(phase==1&&index==12)begin state<=ISSUE;index<=0;phase<=2;end
    else if(phase==2)begin state<=ISSUE;index<=0;phase<=3;end
    else if(phase==3&&index==15)begin state<=ISSUE;index<=0;phase<=4;end
    else if(phase==4&&index==15)state<=FINISH;
    else begin index<=index+1'b1;state<=ISSUE;end
   end
   DRAIN:if(cs_idle&&(&pause_ack))state<=ISSUE;
   default:state<=FAILED;
  endcase
 end
endmodule
