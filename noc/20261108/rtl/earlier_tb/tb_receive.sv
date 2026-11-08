`timescale 1ns/1ps
module tb_receive;
  reg clk=0;always #5 clk=~clk;
  reg rst_n=0,mv=0,av=0,wr=0;
  reg [255:0] md=0,ad=0;
  wire mr,ar,credit,wv,wa,empty;
  wire [255:0] wd;
  wire [31:0] mc,ac;
  ni_receive dut(clk,rst_n,md,ad,mv,av,mr,ar,credit,wd,wv,wa,wr,empty,mc,ac);
  integer fd,rc,imv,iav,iwr,emr,ear,ewv,ewa,ec,emc,eac,rows=0;
  reg [255:0] imd,iad,ewd;
  initial begin
    repeat(2) @(negedge clk);rst_n=1;
    fd=$fopen("vectors/receive.txt","r");if(!fd) $fatal(1,"missing receive vectors");
    while(!$feof(fd)) begin
      rc=$fscanf(fd,"%h %h %h %h %h %h %h %h %h %h %h %h %h\n",imv,imd,iav,iad,iwr,emr,ear,ewv,ewa,ewd,ec,emc,eac);
      if(rc!=13) $fatal(1,"bad receive vector");
      @(negedge clk);mv=imv;av=iav;md=imd;ad=iad;wr=iwr;#1;
      if(mr!==emr[0] || ar!==ear[0] || wv!==ewv[0] || (wv && wa!==ewa[0]) || wd!==ewd || credit!==ec[0])
        $fatal(1,"receive mismatch cycle=%0d got wv=%b wa=%b data=%h expected wv=%b wa=%b data=%h",rows,wv,wa,wd,ewv[0],ewa[0],ewd);
      @(posedge clk);#1;
      if(mc!==emc || ac!==eac || empty!==(eac==0)) $fatal(1,"FIFO count mismatch cycle=%0d",rows);
      rows=rows+1;
    end
    $fclose(fd);
    if(mc!=0 || ac!=0) $fatal(1,"undrained FIFO");
    $display("PASS receive cycles=%0d",rows);$finish;
  end
endmodule
