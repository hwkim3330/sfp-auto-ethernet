// t1s_top with the board's line polarity: both lanes straight, P to P (the
// host's TX reaches the lane as it is, the lane's TX reaches the host as it
// is). With the default parameters both PCSes must sync, finish
// auto-negotiation, and the top must raise fpga_link; a second instance that
// inverts its RX words (the old board's RX_INVERT), fed the same straight
// line, must stay down - so the check would notice a wrong polarity.
`timescale 1ns/1ps
module tb_top;
  wire clk = dut.lane.word_clk;                 // the lane model's 125 MHz
  reg  mclk = 0;
  always #200 mclk = ~mclk;
  reg  rst = 1;

  // host PCS, MAC side, idle (no frames: this checks the link only)
  wire [9:0] h2l, l2h;
  wire h_sync, h_done; wire [15:0] h_cfg;
  sgmii_pcs_phy #(.ABILITY(16'h4001), .LINK_TIMER(200), .MAC_SIDE(1)) host(
    .clk(clk), .rst(rst), .rx_raw(l2h), .tx_code(h2l),
    .gmii_tx_en(1'b0), .gmii_txd(8'h00), .gmii_rx_dv(), .gmii_rxd(), .gmii_rx_er(),
    .rx_sync(h_sync), .an_done(h_done), .partner_config(h_cfg));

  wire link, bad_link;
  t1s_top #(.LINK_TIMER(200)) dut(
    .mii_tx_clk(mclk), .mii_tx_en(), .mii_txd(), .mii_crs(1'b0), .mii_col(1'b0),
    .mii_rx_clk(mclk), .mii_rx_dv(1'b0), .mii_rxd(4'h0), .fpga_link(link));
  t1s_top #(.RX_INVERT(1), .LINK_TIMER(200)) wrong(
    .mii_tx_clk(mclk), .mii_tx_en(), .mii_txd(), .mii_crs(1'b0), .mii_col(1'b0),
    .mii_rx_clk(mclk), .mii_rx_dv(1'b0), .mii_rxd(4'h0), .fpga_link(bad_link));

  // the board: host TX straight into the lane, lane TX straight to the host
  always @(posedge clk) begin
    dut.lane.rx_r   <= h2l;
    wrong.lane.rx_r <= h2l;
  end
  assign l2h = dut.tx_word;

  initial begin
    #100 dut.lane.rdy_r = 1; wrong.lane.rdy_r = 1;
    #200 rst = 0;
    #400000;
    $display("host sync %b an %b cfg %h | top link %b | with RX inverted: link %b",
             h_sync, h_done, h_cfg, link, bad_link);
    if (h_sync && h_done && link && !bad_link) $display("PASS");
    else $display("FAIL");
    $finish;
  end
endmodule
