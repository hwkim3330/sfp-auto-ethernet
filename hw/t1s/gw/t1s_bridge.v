// SGMII (10 Mb/s) <-> 10BASE-T1S bridge: the whole datapath of the T1S SFP.
//
//   host --SGMII--> PCS -> x100 rate adaptation -> strip preamble -> FIFO h2p
//        -> half-duplex MII MAC (CSMA/CD, PLCA done by the PHY) -> LAN867x
//   LAN867x -> MII MAC RX -> FIFO p2h -> new preamble -> x100 -> PCS --SGMII--> host
//
// The FIFOs hold whole frames (DA..FCS plus an end marker) and publish a
// frame only once it is complete, so neither side can underrun mid-frame and
// a frame that loses on the T1S segment can be replayed from its start.
// Frames shorter than 64 bytes, errored ones and ones that overflow are
// dropped whole.
`default_nettype none
module t1s_bridge #(
    parameter integer LINK_TIMER = 200000,
    parameter integer FIFO_AW    = 12,
    parameter integer SLOT_SHIFT = 7
) (
    input  wire       clk,            // 125 MHz, the SerDes word clock
    input  wire       rst,
    // SerDes
    input  wire [9:0] rx_raw,
    output wire [9:0] tx_code,
    // MII to the LAN867x (the PHY drives both clocks)
    input  wire       mii_tx_clk,
    output wire       mii_tx_en,
    output wire [3:0] mii_txd,
    input  wire       mii_crs,
    input  wire       mii_col,
    input  wire       mii_rx_clk,
    input  wire       mii_rx_dv,
    input  wire       mii_rx_er,
    input  wire [3:0] mii_rxd,
    // status
    output wire       sgmii_sync,
    output wire       sgmii_an_done,
    output wire [4:0] tx_attempts,
    output reg  [15:0] h2p_dropped,   // frames from the host dropped (short, errored, overflow)
    output reg  [15:0] p2h_frames     // frames delivered to the host
);
    // ------------------------------------------------------------ resets
    reg [1:0] txr, rxr;
    always @(posedge mii_tx_clk or posedge rst) if (rst) txr <= 2'b11; else txr <= {txr[0], 1'b0};
    always @(posedge mii_rx_clk or posedge rst) if (rst) rxr <= 2'b11; else rxr <= {rxr[0], 1'b0};
    wire tx_rst = txr[1], rx_rst = rxr[1];

    // ------------------------------------------------------------ SGMII PCS
    wire       g_tx_en;  wire [7:0] g_txd;       // to the host
    wire       g_rx_dv, g_rx_er; wire [7:0] g_rxd;   // from the host
    wire [15:0] partner;
    sgmii_pcs_phy #(.ABILITY(16'h9001), .LINK_TIMER(LINK_TIMER)) pcs (
        .clk(clk), .rst(rst), .rx_raw(rx_raw), .tx_code(tx_code),
        .gmii_tx_en(g_tx_en), .gmii_txd(g_txd),
        .gmii_rx_dv(g_rx_dv), .gmii_rxd(g_rxd), .gmii_rx_er(g_rx_er),
        .rx_sync(sgmii_sync), .an_done(sgmii_an_done), .partner_config(partner));

    // ------------------------------------------------------------ rate adaptation
    wire       src_req, src_avail, src_end; wire [7:0] src_byte;
    wire       r_stb, r_end; wire [7:0] r_byte;
    sgmii_rate10 rate (
        .clk(clk), .rst(rst),
        .req(src_req), .avail(src_avail), .byte_in(src_byte), .end_in(src_end),
        .gmii_tx_en(g_tx_en), .gmii_txd(g_txd),
        .gmii_rx_dv(g_rx_dv), .gmii_rxd(g_rxd),
        .rx_stb(r_stb), .rx_byte(r_byte), .rx_end(r_end));

    // ------------------------------------------------------------ host -> PHY
    // drop the preamble, keep SFD+1 .. FCS, then an end marker and commit
    reg        h_in, h_bad; reg [11:0] h_n;
    reg        h_we, h_last, h_commit, h_abort; reg [7:0] h_data;
    wire       h_full;
    always @(posedge clk) begin
        h_we <= 1'b0; h_last <= 1'b0; h_commit <= 1'b0; h_abort <= 1'b0;
        if (rst) begin h_in <= 1'b0; h_bad <= 1'b0; h_n <= 0; h2p_dropped <= 0; end
        else begin
            if (g_rx_er) h_bad <= 1'b1;
            if (r_stb) begin
                if (!h_in) begin
                    if (r_byte == 8'hD5) begin h_in <= 1'b1; h_n <= 0; end
                end else begin
                    h_we <= 1'b1; h_data <= r_byte;
                    if (h_full) h_bad <= 1'b1;
                    if (h_n != 12'hFFF) h_n <= h_n + 1'b1;
                end
            end
            if (r_end) begin
                if (h_in && !h_bad && h_n >= 12'd64 && !h_full) begin
                    h_we <= 1'b1; h_data <= 8'h00; h_last <= 1'b1; h_commit <= 1'b1;
                end else if (h_in || h_bad) begin
                    h_abort <= 1'b1; h2p_dropped <= h2p_dropped + 1'b1;
                end
                h_in <= 1'b0; h_bad <= 1'b0;
            end
        end
    end

    wire       f_empty, f_last, f_re, f_rewind, f_commit; wire [7:0] f_data;
    frame_fifo #(.AW(FIFO_AW)) h2p (
        .wclk(clk), .wrst(rst), .we(h_we), .wdata(h_data), .wlast(h_last),
        .wr_commit(h_commit), .wr_abort(h_abort), .wfull(h_full),
        .rclk(mii_tx_clk), .rrst(tx_rst), .re(f_re), .rdata(f_data), .rlast(f_last),
        .rempty(f_empty), .rd_rewind(f_rewind), .rd_commit(f_commit));

    // ------------------------------------------------------------ MII MAC
    wire       w_we, w_last, w_commit, w_abort, p_full; wire [7:0] w_data;
    mii_hd_mac #(.SLOT_SHIFT(SLOT_SHIFT)) mac (
        .tx_clk(mii_tx_clk), .tx_rst(tx_rst), .crs(mii_crs), .col(mii_col),
        .mii_tx_en(mii_tx_en), .mii_txd(mii_txd),
        .f_empty(f_empty), .f_data(f_data), .f_last(f_last),
        .f_re(f_re), .f_rewind(f_rewind), .f_commit(f_commit), .attempts_out(tx_attempts),
        .rx_clk(mii_rx_clk), .rx_rst(rx_rst), .mii_rx_dv(mii_rx_dv), .mii_rx_er(mii_rx_er),
        .mii_rxd(mii_rxd), .w_full(p_full), .w_we(w_we), .w_data(w_data), .w_last(w_last),
        .w_commit(w_commit), .w_abort(w_abort));

    // ------------------------------------------------------------ PHY -> host
    wire       p_empty, p_last; wire [7:0] p_data;
    reg  [3:0] pre;                                  // 0..6 preamble, 7 SFD, 8 frame
    assign src_avail = !p_empty;
    assign src_byte  = (pre < 4'd7) ? 8'h55 : (pre == 4'd7) ? 8'hD5 : p_data;
    assign src_end   = (pre == 4'd8) && p_last;
    wire   p_re      = src_req && (pre == 4'd8);
    wire   p_commit  = p_re && p_last;
    always @(posedge clk) begin
        if (rst) begin pre <= 0; p2h_frames <= 0; end
        else if (src_req) begin
            if (pre != 4'd8) pre <= pre + 1'b1;
            else if (p_last) begin pre <= 0; p2h_frames <= p2h_frames + 1'b1; end
        end
    end
    frame_fifo #(.AW(FIFO_AW)) p2h (
        .wclk(mii_rx_clk), .wrst(rx_rst), .we(w_we), .wdata(w_data), .wlast(w_last),
        .wr_commit(w_commit), .wr_abort(w_abort), .wfull(p_full),
        .rclk(clk), .rrst(rst), .re(p_re), .rdata(p_data), .rlast(p_last),
        .rempty(p_empty), .rd_rewind(1'b0), .rd_commit(p_commit));
endmodule
`default_nettype wire
