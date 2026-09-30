// Transceiver lane 0 of the GW5AT-15 as the bridge needs it: a 125 MHz word
// clock and raw 10-bit words each way, nothing else. No 8b/10b, no comma
// alignment in the hard block: sgmii_pcs_phy does both, so the same PCS runs
// in simulation and on any other FPGA.
//
// On the board this module is the Gowin "Customized PHY" IP (IPUG1024),
// generated in Gowin EDA and not redistributable, with these settings:
//   Quad 0, lane 0, RX and TX enabled
//   line rate 1.25 Gb/s from REFCLK0 (125 MHz, balls A8/A7), CPLL or QPLL0
//   fabric width 10 bit, one word per 125 MHz fabric clock
//   8b/10b encoder and decoder: bypassed; word alignment: off
//   RX / TX polarity: as laid (the inversion is in t1s_top)
//   bit order: first bit on the line = word bit 0 (IEEE 802.3 clause 36 'a')
// With `define GOWIN the lane is gw_customized_phy_lane0: a shim of a few
// lines to write round the generated SerDes_Top once it exists, mapping its
// fabric clock to clk_o, PLL lock AND CDR lock to ready_o, and its RX / TX
// data to rx_data_o / tx_data_i (the generated port names are the IP
// version's; they are not guessed here).
//
// Without GOWIN this is a simulation model: a 125 MHz clock and registers
// that tb/tb_top.v drives from a host PCS through hierarchical references.
`default_nettype none
module serdes_lane (
    output wire       word_clk,
    output wire       ready,
    output wire [9:0] rx_word,
    input  wire [9:0] tx_word
);
`ifdef GOWIN
    // Customized PHY instance goes here (generated: SerDes_Top.v)
    gw_customized_phy_lane0 ip (
        .clk_o(word_clk), .ready_o(ready), .rx_data_o(rx_word), .tx_data_i(tx_word));
`else
    // simulation: the testbench forces these through hierarchical references
    reg        clk_r = 1'b0;
    reg        rdy_r = 1'b0;
    reg  [9:0] rx_r  = 10'h0;
    always #4 clk_r = ~clk_r;                 // 125 MHz
    assign word_clk = clk_r;
    assign ready    = rdy_r;
    assign rx_word  = rx_r;
`endif
endmodule
