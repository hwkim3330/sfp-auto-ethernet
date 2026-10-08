// Top level of the T1S SFP's FPGA (Gowin GW5AT-LV15MG132): transceiver lane 0
// <-> t1s_bridge <-> MII to the LAN8670. Pins: t1s.cst (from hw/t1s/make_t1s.py).
//
// Polarity: the board keeps both SGMII lanes P to P (hw/t1s/make_t1s.py, C3-C6:
// host TD+ reaches RXP, TXP reaches host RD+), so nothing is inverted. Until
// the SFP edge was corrected (2026-10) the fingers were drawn mirrored and RX
// arrived inverted, which RX_INVERT undid. The parameters stay for a board
// that needs them: inverting a 10-bit code group bit by bit is exact for
// 8b/10b, the decoder sees what the host sent.
`default_nettype none
module t1s_top #(
    parameter RX_INVERT = 0,
    parameter TX_INVERT = 0,
    parameter integer LINK_TIMER = 200000       // 1.6 ms at 125 MHz (SGMII link timer)
) (
    // transceiver lane 0 and REFCLK0 go straight to the hard block (serdes_lane)
    // MII to the LAN8670 (it drives both 2.5 MHz clocks)
    input  wire       mii_tx_clk,
    output wire       mii_tx_en,
    output wire [3:0] mii_txd,
    input  wire       mii_crs,
    input  wire       mii_col,
    input  wire       mii_rx_clk,
    input  wire       mii_rx_dv,
    input  wire [3:0] mii_rxd,
    // to the MCU: SGMII link up (it drives the SFP's RX_LOS from this)
    output wire       fpga_link
);
    wire       clk, lane_ready;
    wire [9:0] rx_word, tx_word;
    serdes_lane lane (.word_clk(clk), .ready(lane_ready), .rx_word(rx_word), .tx_word(tx_word));

    // hold the datapath in reset until the lane's PLL and CDR have locked
    reg [3:0] rst_sr = 4'hF;
    always @(posedge clk) rst_sr <= {rst_sr[2:0], ~lane_ready};
    wire rst = rst_sr[3];

    wire [9:0] rx_raw  = RX_INVERT ? ~rx_word : rx_word;
    wire [9:0] tx_code;
    assign tx_word = TX_INVERT ? ~tx_code : tx_code;

    wire sync, an_done;
    t1s_bridge #(.LINK_TIMER(LINK_TIMER)) bridge (
        .clk(clk), .rst(rst), .rx_raw(rx_raw), .tx_code(tx_code),
        .mii_tx_clk(mii_tx_clk), .mii_tx_en(mii_tx_en), .mii_txd(mii_txd),
        .mii_crs(mii_crs), .mii_col(mii_col), .mii_rx_clk(mii_rx_clk),
        .mii_rx_dv(mii_rx_dv), .mii_rx_er(1'b0), .mii_rxd(mii_rxd),   // RXER is only a strap on this board
        .sgmii_sync(sync), .sgmii_an_done(an_done),
        .tx_attempts(), .h2p_dropped(), .p2h_frames());
    assign fpga_link = sync & an_done;
endmodule
