// Two PCS back to back: the SFP (PHY side, ABILITY 0x9001) and a host (MAC
// side, 0x4001). Checks: word alignment from an arbitrary bit slip, AN on
// both ends, the PHY's advertised word as seen by the MAC, and a frame each
// way arriving byte-exact.
`timescale 1ns/1ps
module tb_pcs;
  reg clk = 0, rst = 1;
  always #4 clk = ~clk;
  wire [9:0] p2m, m2p;
  // a 3-bit slip on one direction and 7 on the other, so alignment is exercised
  reg [19:0] s1, s2;
  always @(posedge clk) begin s1 <= {s1[9:0], p2m}; s2 <= {s2[9:0], m2p}; end
  wire [9:0] p2m_slip = s1[12:3], m2p_slip = s2[16:7];
  reg  ptx_en = 0, mtx_en = 0; reg [7:0] ptxd = 0, mtxd = 0;
  wire prx_dv, mrx_dv, prx_er, mrx_er; wire [7:0] prxd, mrxd;
  wire psync, msync, pdone, mdone; wire [15:0] pcfg, mcfg;
  sgmii_pcs_phy #(.ABILITY(16'h9001), .LINK_TIMER(200)) phy(
    .clk(clk), .rst(rst), .rx_raw(m2p_slip), .tx_code(p2m),
    .gmii_tx_en(ptx_en), .gmii_txd(ptxd), .gmii_rx_dv(prx_dv), .gmii_rxd(prxd), .gmii_rx_er(prx_er),
    .rx_sync(psync), .an_done(pdone), .partner_config(pcfg));
  sgmii_pcs_phy #(.ABILITY(16'h4001), .LINK_TIMER(200), .MAC_SIDE(1)) mac(
    .clk(clk), .rst(rst), .rx_raw(p2m_slip), .tx_code(m2p),
    .gmii_tx_en(mtx_en), .gmii_txd(mtxd), .gmii_rx_dv(mrx_dv), .gmii_rxd(mrxd), .gmii_rx_er(mrx_er),
    .rx_sync(msync), .an_done(mdone), .partner_config(mcfg));
  // frames: 7 x 55, D5, then a counting payload
  integer n = 64, i, bad = 0, got_m = 0, got_p = 0;
  reg [7:0] exp_m [0:127]; reg [7:0] exp_p [0:127];
  initial begin
    for (i = 0; i < 128; i = i + 1) begin
      exp_m[i] = (i < 7) ? 8'h55 : (i == 7) ? 8'hD5 : i[7:0];
      exp_p[i] = (i < 7) ? 8'h55 : (i == 7) ? 8'hD5 : (8'hFF - i[7:0]);
    end
  end
  // IEEE 802.3 lets a PCS drop preamble bytes (an /S/ must start on an even
  // code group), so compare from the SFD: >= 5 x 55, D5, then the payload exact
  integer pm = 0, pp = 0; reg sm = 0, sp = 0;
  always @(posedge clk) begin
    if (mrx_dv) begin
      if (!sm) begin if (mrxd == 8'hD5) begin sm = 1; if (pm < 5) bad = bad + 1; got_m = 8; end
                     else if (mrxd == 8'h55) pm = pm + 1; else bad = bad + 1; end
      else begin if (mrxd !== exp_m[got_m]) bad = bad + 1; got_m = got_m + 1; end
    end
    if (prx_dv) begin
      if (!sp) begin if (prxd == 8'hD5) begin sp = 1; if (pp < 5) bad = bad + 1; got_p = 8; end
                     else if (prxd == 8'h55) pp = pp + 1; else bad = bad + 1; end
      else begin if (prxd !== exp_p[got_p]) bad = bad + 1; got_p = got_p + 1; end
    end
    if (mrx_er || prx_er) bad = bad + 1;
  end
  task send(input integer who);
    begin
      @(posedge clk);
      for (i = 0; i < n; i = i + 1) begin
        if (who == 0) begin ptx_en <= 1; ptxd <= exp_m[i]; end
        else begin mtx_en <= 1; mtxd <= exp_p[i]; end
        @(posedge clk);
      end
      ptx_en <= 0; mtx_en <= 0;
      repeat (20) @(posedge clk);
    end
  endtask
  initial begin
    repeat (5) @(posedge clk); rst <= 0;
    wait (pdone && mdone);
    $display("sync %b/%b, AN done, MAC sees PHY config %h, PHY sees MAC config %h", psync, msync, mcfg, pcfg);
    if (mcfg !== 16'hD001) bad = bad + 1;      // 0x9001 | ack once the PHY has seen the MAC
    repeat (10) @(posedge clk);
    send(0); send(1);
    repeat (40) @(posedge clk);
    // /S/ carries the first preamble byte, so each side sees the full 64
    $display("PHY->MAC: %0d preamble + SFD + %0d payload; MAC->PHY: %0d preamble + SFD + %0d payload; errors %0d",
             pm, got_m - 8, pp, got_p - 8, bad);
    if (got_m != n || got_p != n || bad) $fatal(1, "FAIL"); else $display("PASS");
    $finish;
  end
  initial begin #2000000; $fatal(1, "TIMEOUT"); end
endmodule
