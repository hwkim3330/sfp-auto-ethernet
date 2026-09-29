// Every (rd, k, d) from the Python model through the Verilog encoder and
// back through the decoder.
`timescale 1ns/1ps
module tb_8b10b;
  reg [7:0] d; reg k, rd; wire [9:0] q; wire rdo;
  wire [7:0] d2; wire k2, err, neu, pos;
  enc8b10b e(.d(d), .k(k), .rd_in(rd), .q(q), .rd_out(rdo));
  dec8b10b x(.q(q), .d(d2), .k(k2), .err(err), .rd_neutral(neu), .rd_pos(pos));
  integer f, r, n, bad; reg [31:0] vrd, vk, vd, vq, vn;
  initial begin
    f = $fopen("vectors_8b10b.txt", "r"); n = 0; bad = 0;
    while (!$feof(f)) begin
      r = $fscanf(f, "%h %h %h %h %h\n", vrd, vk, vd, vq, vn);
      if (r == 5) begin
        rd = vrd[0]; k = vk[0]; d = vd[7:0]; #1;
        if (q !== vq[9:0] || rdo !== vn[0] || d2 !== d || k2 !== k || err) begin
          bad = bad + 1;
          if (bad < 5) $display("MISMATCH rd=%0d k=%0d d=%h: q=%b want %b rd_out=%b dec=%h/%b err=%b", rd, k, d, q, vq[9:0], rdo, d2, k2, err);
        end
        n = n + 1;
      end
    end
    // a few codes that must be rejected
    d = 0; k = 0;
    force e.q = 10'b1111111111; #1; if (!err) bad = bad + 1; release e.q;
    $display("8b10b: %0d vectors, %0d mismatches", n, bad);
    if (bad) $fatal(1, "FAIL"); else $display("PASS");
    $finish;
  end
endmodule
