`timescale 1ns/1ps
module tb_selectors;
  localparam W=256;
  reg [4:0] tx,rx;
  reg [255:0] data;
  reg tv,credit;
  reg [8:0] cv,fv;
  reg [9*W-1:0] fdata;
  wire [9*W-1:0] od[0:15];
  wire [8:0] ov[0:15],oc[0:15];
  wire [255:0] rd[0:15];
  wire [15:0] tc,rv,tl,rl,unexpected;
  genvar g;
  generate for(g=0;g<16;g=g+1) begin:nodes
    node_selectors #(.NODE_ID(g)) dut(tx,rx,data,tv,cv,od[g],ov[g],tc[g],fdata,fv,credit,rd[g],rv[g],oc[g],tl[g],rl[g],unexpected[g]);
  end endgenerate
  integer masks[0:15];
  integer a,b,n,j,goodt,goodr,cases=0;
  reg [9*W-1:0] ed;
  reg [8:0] ev,ec;
  reg [255:0] er;
  reg etc,erv,eu;
  function integer allowed(input integer nodeid,value);
    begin allowed=(value==0)||((value>=16 && value<=24)&&((masks[nodeid] & (1<<(value-16)))!=0));end
  endfunction
  initial begin
    masks[0]=1;masks[1]=3;masks[2]=6;masks[3]=4;
    masks[4]=9;masks[5]=27;masks[6]=54;masks[7]=36;
    masks[8]=72;masks[9]=216;masks[10]=432;masks[11]=288;
    masks[12]=64;masks[13]=192;masks[14]=384;masks[15]=256;
    data={8{32'habcdef01}};
    for(j=0;j<9;j=j+1) fdata[j*W+:W]={8{32'h71000000+j}};
    for(a=0;a<32;a=a+1) for(b=0;b<32;b=b+1) begin
      tx=a;rx=b;tv=(a+b)%2;credit=(a+b/2)%2;cv=(a*17+b*11)&511;fv=(a*31+b*7)&511;#1;
      for(n=0;n<16;n=n+1) begin
        goodt=allowed(n,a);goodr=allowed(n,b);
        ed=0;ev=0;ec=0;er=0;etc=0;erv=0;
        if(goodt && a!=0) begin ed[(a-16)*W+:W]=data;ev[a-16]=tv;etc=cv[a-16];end
        if(goodr && b!=0) begin er=fdata[(b-16)*W+:W];erv=fv[b-16];ec[b-16]=credit;end
        eu=|(fv & ~(goodr && b!=0 ? (9'b1<<(b-16)):9'b0));
        if(tl[n]!==goodt[0] || rl[n]!==goodr[0] || od[n]!==ed || ov[n]!==ev || oc[n]!==ec || rd[n]!==er || tc[n]!==etc || rv[n]!==erv || unexpected[n]!==eu)
          $fatal(1,"selector mismatch node=%0d tx=%0d rx=%0d",n,a,b);
        cases=cases+1;
      end
    end
    $display("PASS selectors cases=%0d nodes=16",cases);$finish;
  end
endmodule
