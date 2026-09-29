// The whole T1S datapath: a host (MAC-side PCS + x100 rate adaptation, as a
// 10 Mb/s SGMII host would be) on one end of t1s_bridge, a LAN867x-like MII
// model on the other.
//
//   1  host -> T1S, collision on the first attempt: the frame must come out
//      on MII byte-exact on a later attempt
//   2  T1S -> host: an MII frame arrives at the host byte-exact
//   3  a 40-byte (runt) frame from the host is dropped, nothing on MII
//   4  a frame that collides on every attempt is given up after 16, and the
//      frame queued behind it still goes out intact (the FIFO freed exactly
//      one frame)
//   5  both directions at once
`timescale 1ns/1ps
module tb_bridge;
  reg clk = 0, rst = 1;
  always #4 clk = ~clk;                         // 125 MHz
  reg mclk = 0;
  always #200 mclk = ~mclk;                     // 2.5 MHz MII tx_clk = rx_clk

  // ---------------------------------------------------------------- SGMII link
  wire [9:0] b2h, h2b;
  reg  [19:0] sl;
  always @(posedge clk) sl <= {sl[9:0], b2h};
  wire [9:0] b2h_slip = sl[14:5];               // a 5-bit slip towards the host

  // host PCS (MAC side) and its 10 Mb/s rate adaptation
  wire h_tx_en, h_rx_dv, h_rx_er; wire [7:0] h_txd, h_rxd;
  wire h_sync, h_done; wire [15:0] h_cfg;
  sgmii_pcs_phy #(.ABILITY(16'h4001), .LINK_TIMER(200), .MAC_SIDE(1)) hpcs(
    .clk(clk), .rst(rst), .rx_raw(b2h_slip), .tx_code(h2b),
    .gmii_tx_en(h_tx_en), .gmii_txd(h_txd), .gmii_rx_dv(h_rx_dv), .gmii_rxd(h_rxd), .gmii_rx_er(h_rx_er),
    .rx_sync(h_sync), .an_done(h_done), .partner_config(h_cfg));
  // host byte source
  reg [7:0] src [0:2047]; integer src_len = 0, src_i = 0; reg src_on = 0;
  wire      s_req;
  wire      s_avail = src_on;
  wire [7:0] s_byte = src[src_i];
  wire      s_end = (src_i == src_len);
  always @(posedge clk) if (s_req) begin
    if (s_end) src_on <= 0; else src_i <= src_i + 1;
  end
  wire hr_stb, hr_end; wire [7:0] hr_byte;
  sgmii_rate10 hrate(.clk(clk), .rst(rst),
    .req(s_req), .avail(s_avail), .byte_in(s_byte), .end_in(s_end),
    .gmii_tx_en(h_tx_en), .gmii_txd(h_txd), .gmii_rx_dv(h_rx_dv), .gmii_rxd(h_rxd),
    .rx_stb(hr_stb), .rx_byte(hr_byte), .rx_end(hr_end));

  // ---------------------------------------------------------------- DUT
  wire mtx_en; wire [3:0] mtxd;
  reg  mcol = 0, mrx_dv = 0, mrx_er = 0; reg [3:0] mrxd = 0;
  wire mcrs = mtx_en | mcol | mrx_dv;
  wire b_sync, b_done; wire [4:0] b_att; wire [15:0] b_drop, b_p2h;
  // backoff slots of 4 nibble clocks instead of 128: 16 attempts in simulated
  // milliseconds, the same state machine
  t1s_bridge #(.LINK_TIMER(200), .SLOT_SHIFT(2)) dut(
    .clk(clk), .rst(rst), .rx_raw(h2b), .tx_code(b2h),
    .mii_tx_clk(mclk), .mii_tx_en(mtx_en), .mii_txd(mtxd), .mii_crs(mcrs), .mii_col(mcol),
    .mii_rx_clk(mclk), .mii_rx_dv(mrx_dv), .mii_rx_er(mrx_er), .mii_rxd(mrxd),
    .sgmii_sync(b_sync), .sgmii_an_done(b_done), .tx_attempts(b_att),
    .h2p_dropped(b_drop), .p2h_frames(b_p2h));

  integer bad = 0;

  // ---------------------------------------------------------------- MII TX side of the PHY model
  // collide_on: attempts (1-based) that get a collision 30 nibbles in
  reg [31:0] collide_mask = 0;
  integer attempt = 0, nib = 0, tx_frames = 0;
  reg [7:0] cap [0:2047]; integer cap_n = 0; reg [3:0] lo; reg sfd = 0, half = 0, was_en = 0;
  reg [7:0] last_frame [0:2047]; integer last_n = 0;
  always @(negedge mclk) begin
    if (mtx_en && !was_en) begin attempt = attempt + 1; nib = 0; cap_n = 0; sfd = 0; half = 0; end
    if (mtx_en) begin
      nib = nib + 1;
      if (collide_mask[attempt] && nib == 30) mcol <= 1;
      if (!sfd) begin if (mtxd == 4'hD) sfd = 1; else if (mtxd != 4'h5) bad = bad + 1; end
      else if (!half) begin lo = mtxd; half = 1; end
      else begin cap[cap_n] = {mtxd, lo}; cap_n = cap_n + 1; half = 0; end
    end
    if (!mtx_en && was_en) begin
      mcol <= 0;
      if (!mcol) begin                            // a clean attempt: a frame went out
        tx_frames = tx_frames + 1;
        last_n = cap_n;
        for (k = 0; k < cap_n; k = k + 1) last_frame[k] = cap[k];
      end
    end
    was_en = mtx_en;
  end
  integer k;

  // ---------------------------------------------------------------- MII RX side of the PHY model
  task mii_rx(input integer n, input integer seed);
    integer j;
    begin
      @(negedge mclk);
      for (j = 0; j < 15; j = j + 1) begin mrx_dv <= 1; mrxd <= 4'h5; @(negedge mclk); end
      mrxd <= 4'hD; @(negedge mclk);
      for (j = 0; j < n; j = j + 1) begin
        mrxd <= pat(j, seed) & 4'hF; @(negedge mclk);
        mrxd <= pat(j, seed) >> 4;   @(negedge mclk);
      end
      mrx_dv <= 0;
    end
  endtask

  // ---------------------------------------------------------------- host RX capture
  reg [7:0] hcap [0:2047]; integer hcap_n = 0, h_frames = 0, hpre = 0; reg hin = 0;
  reg [7:0] hlast [0:2047]; integer hlast_n = 0;
  always @(posedge clk) begin
    if (hr_stb) begin
      if (!hin) begin if (hr_byte == 8'hD5) begin hin = 1; if (hpre < 5) bad = bad + 1; end
                      else if (hr_byte == 8'h55) hpre = hpre + 1; else bad = bad + 1; end
      else begin hcap[hcap_n] = hr_byte; hcap_n = hcap_n + 1; end
    end
    if (hr_end) begin
      if (hin) begin
        h_frames = h_frames + 1; hlast_n = hcap_n;
        for (k = 0; k < hcap_n; k = k + 1) hlast[k] = hcap[k];
      end
      hin = 0; hcap_n = 0; hpre = 0;
    end
    if (h_rx_er) bad = bad + 1;
  end

  function [7:0] pat(input integer j, input integer seed);
    pat = (j * 7 + seed * 31 + (j >> 3)) & 8'hFF;
  endfunction

  task host_send(input integer n, input integer seed);   // n bytes after the SFD
    integer j;
    begin
      wait (!src_on);
      for (j = 0; j < 7; j = j + 1) src[j] = 8'h55;
      src[7] = 8'hD5;
      for (j = 0; j < n; j = j + 1) src[8 + j] = pat(j, seed);
      src_len = 8 + n; src_i = 0;
      @(posedge clk); src_on <= 1;
      @(posedge clk); wait (!src_on);
    end
  endtask

  task check_mii(input integer n, input integer seed, input [8*24-1:0] what);
    integer j, e;
    begin
      e = 0;
      if (last_n != n) e = e + 1;
      for (j = 0; j < n && j < last_n; j = j + 1) if (last_frame[j] !== pat(j, seed)) e = e + 1;
      $display("  %0s: %0d bytes on MII (want %0d), %0d wrong, attempt counter at %0d", what, last_n, n, e, attempt);
      bad = bad + e;
    end
  endtask
  task check_host(input integer n, input integer seed, input [8*24-1:0] what);
    integer j, e;
    begin
      e = 0;
      if (hlast_n != n) e = e + 1;
      for (j = 0; j < n && j < hlast_n; j = j + 1) if (hlast[j] !== pat(j, seed)) e = e + 1;
      $display("  %0s: %0d bytes at the host (want %0d), %0d wrong", what, hlast_n, n, e);
      bad = bad + e;
    end
  endtask

  integer f0, a0;
  initial begin
    // hold reset across a few MII clocks: the PHY-side domains reset on their own clock
    repeat (500) @(posedge clk); rst <= 0;
    wait (b_done && h_done);
    $display("SGMII up: host sees %h, bridge sees %h", h_cfg, dut.partner);
    if (h_cfg !== 16'hD001) bad = bad + 1;
    repeat (100) @(posedge clk);

    // 1: collision on the first attempt
    collide_mask = 32'b10;                       // attempt 1
    f0 = tx_frames;
    host_send(64, 1);
    wait (tx_frames == f0 + 1);
    check_mii(64, 1, "1 retry after collision");
    if (attempt < 2) bad = bad + 1;

    // 2: T1S -> host
    f0 = h_frames;
    mii_rx(70, 2);
    wait (h_frames == f0 + 1);
    check_host(70, 2, "2 T1S to host");

    // 3: runt from the host
    f0 = tx_frames; a0 = b_drop;
    host_send(40, 3);
    repeat (40000) @(posedge clk);
    $display("  3 runt: dropped %0d, frames on MII %0d", b_drop - a0, tx_frames - f0);
    if (b_drop != a0 + 1 || tx_frames != f0) bad = bad + 1;

    // 4: 16 collisions -> given up; the next frame still clean
    a0 = attempt;
    collide_mask = 32'hFFFF_FFFF;
    f0 = tx_frames;
    host_send(80, 4);
    host_send(64, 5);                            // queued behind it
    wait (attempt == a0 + 16);                   // the 16th attempt has started...
    wait (mcol); wait (!mtx_en);                 // ...collided and ended
    collide_mask = 0;
    wait (tx_frames == f0 + 1);
    check_mii(64, 5, "4 frame after a give-up");
    $display("  4 attempts on the doomed frame: %0d", attempt - a0 - 1);

    // 5: both directions at once
    f0 = tx_frames; a0 = h_frames;
    fork
      host_send(100, 6);
      mii_rx(90, 7);
    join
    wait (tx_frames == f0 + 1 && h_frames == a0 + 1);
    check_mii(100, 6, "5 host to T1S, duplex");
    check_host(90, 7, "5 T1S to host, duplex");

    repeat (100) @(posedge clk);
    $display("errors %0d", bad);
    if (bad) $fatal(1, "FAIL"); else $display("PASS");
    $finish;
  end
  initial begin #60_000_000; $fatal(1, "TIMEOUT"); end
endmodule
