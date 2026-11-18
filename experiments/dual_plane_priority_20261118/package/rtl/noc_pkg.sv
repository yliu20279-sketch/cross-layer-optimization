package noc_pkg;
  localparam int W=256, VNS=4, FW=W+4;
  localparam logic [3:0] GETS=1, DATAS=2, MOE_DATA=3, MOE_CTRL=4, CONFIG=5, CONFIG_ACK=6;
  // Physical links: 256 data bits, head/tail and two virtual-network bits.
  // Routing and transaction fields occupy the header flit's 256 data bits.
  typedef logic [FW-1:0] flit_t;
  function automatic int vn_of(input logic [3:0] opcode);
    case(opcode) GETS:vn_of=1; DATAS:vn_of=2;
      MOE_DATA,MOE_CTRL:vn_of=0;CONFIG,CONFIG_ACK:vn_of=3;default:vn_of=-1;
    endcase
  endfunction
  function automatic logic [255:0] header(input logic [3:0] op,src,dst,
      input logic [31:0] id,txn,input logic [15:0] bytes);
    header='0;
    header[255:252]=op;header[251:248]=dst;header[247:244]=src;
    header[243:212]=id;header[211:196]=bytes;header[195:164]=txn;
  endfunction
  function automatic flit_t frame(input logic [255:0] data,input int vn,
                                  input logic head,tail);
    frame={2'(vn),head,tail,data};
  endfunction
endpackage
