module priority_unit_tb;
 import noc_pkg::*;
 logic clk=0,reset=1;
 always #5 clk=~clk;
 logic [4:0] in_valid,out_valid;
 flit_t in_flit[5],out_flit[5];
 logic [3:0] in_credit[5],out_credit[5];logic busy;
 xy_router #(.ID(0),.TYPE_PRIORITY(1)) dut(.*);
 task automatic enqueue(input int v,input int dst);
  @(negedge clk);
  in_valid=1;in_flit[0]=frame(header(v==3?CONFIG:v==2?DATAS:v==1?GETS:MOE_DATA,4'd0,4'(dst),32'(v+1),0,0),v,1,1);
  #1;assert(in_credit[0][v])else $fatal(1,"input blocked");
  @(posedge clk);#1;
 endtask
 task automatic reset_dut;
  @(negedge clk);reset=1;in_valid=0;
  for(int p=0;p<5;p++)begin in_flit[p]='0;out_credit[p]=0;end
  repeat(2)@(posedge clk);
  @(negedge clk);reset=0;
 endtask
 initial begin
  in_valid=0;for(int p=0;p<5;p++)begin in_flit[p]='0;out_credit[p]=0;end
  reset_dut();
  for(int v=0;v<4;v++)enqueue(v,0);
  @(negedge clk);in_valid=0;out_credit[4]=15;
  for(int v=3;v>=0;v--)begin
   #1;assert(out_valid[4]&&out_flit[4][259:258]==v)else $fatal(1,"fixed VN priority violated");
   @(posedge clk);@(negedge clk);
  end
  reset_dut();
  enqueue(0,1);enqueue(3,0);
  @(negedge clk);in_valid=0;out_credit[0]=15;out_credit[4]=15;
  #1;assert(out_valid[4]&&!out_valid[0]&&out_flit[4][259:258]==3)else $fatal(1,"cross-output input conflict violated priority");
  @(posedge clk);@(negedge clk);
  #1;assert(out_valid[0]&&out_flit[0][259:258]==0)else $fatal(1,"low class failed to resume");
  $display("PASS fixed class order and cross-output input conflict; no added queue or link");$finish;
 end
 initial begin #10000;$fatal(1,"priority unit timeout");end
endmodule
