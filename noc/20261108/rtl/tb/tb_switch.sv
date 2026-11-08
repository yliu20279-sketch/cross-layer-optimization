`timescale 1ns/1ps
module tb_switch;
  localparam W=256;
  reg [11:0] cfg;
  reg [4*W-1:0] din;
  reg [3:0] vin,cr;
  wire [4*W-1:0] dout;
  wire [3:0] vout,back;
  wire legal;
`ifdef MAPPED_SWITCH
  terminal_switch dut(.active_cfg(cfg),.in_data(din),.in_valid(vin),.downstream_credit(cr),
    .out_data(dout),.out_valid(vout),.upstream_credit(back),.cfg_legal(legal));
`else
  terminal_switch #(.W(W)) dut(.active_cfg(cfg),.in_data(din),.in_valid(vin),.downstream_credit(cr),
    .out_data(dout),.out_valid(vout),.upstream_credit(back),.cfg_legal(legal));
`endif
  integer c,v,r,o,f,p,used,good,legal_count=0,cases=0,b;
  integer choice[0:3];
  reg [4*W-1:0] ed;
  reg [3:0] ev,eb;
  function integer lookup(input integer outp,sel);
    begin
      case(outp)
        0:case(sel) 0:lookup=1;1:lookup=2;default:lookup=3;endcase
        1:case(sel) 0:lookup=0;1:lookup=2;default:lookup=3;endcase
        2:case(sel) 0:lookup=0;1:lookup=1;default:lookup=3;endcase
        3:case(sel) 0:lookup=0;1:lookup=1;default:lookup=2;endcase
      endcase
    end
  endfunction
  initial begin
    for(o=0;o<4;o=o+1) din[o*W+:W]={8{32'h81020304+o}};
    for(c=0;c<4096;c=c+1) begin
      good=1;used=0;
      for(o=0;o<4;o=o+1) begin
        f=(c>>(3*o))&7;choice[o]=-1;
        if(f!=0) begin
          if(f<4 || f>6) good=0;
          else begin
            p=lookup(o,f-4);choice[o]=p;
            if((used & (1<<p))!=0) good=0;
            used=used|(1<<p);
          end
        end
      end
      if(good) legal_count=legal_count+1;
      for(v=0;v<16;v=v+1) for(r=0;r<16;r=r+1) begin
        cfg=c;vin=v;cr=r;ed=0;ev=0;eb=0;
        if(good) for(o=0;o<4;o=o+1) if(choice[o]>=0) begin
          ed[o*W+:W]=din[choice[o]*W+:W];ev[o]=vin[choice[o]];eb[choice[o]]=cr[o];
        end
        #1;
        if(legal!==good[0] || dout!==ed || vout!==ev || back!==eb)
          $fatal(1,"switch mismatch cfg=%h valid=%h credit=%h",cfg,vin,cr);
        cases=cases+1;
      end
    end
    if(legal_count!=108) $fatal(1,"legal count=%0d",legal_count);
    // Walk every data bit over each of the twelve directed corner connections.
    for(o=0;o<4;o=o+1) for(p=0;p<3;p=p+1) for(b=0;b<W;b=b+1) begin
      cfg=(4+p)<<(3*o);din=0;din[lookup(o,p)*W+b]=1;vin=15;cr=15;#1;
      ed=0;ed[o*W+b]=1;
      if(dout!==ed) $fatal(1,"walking-bit mismatch");
    end
    $display("PASS switch cases=%0d legal=108 illegal=3988 walking_bits=3072",cases);
    $finish;
  end
endmodule
