// Half-duplex MII MAC side for a 10BASE-T1S PHY (LAN867x).
//
// The LAN867x "operates in conjunction with a CSMA/CD MAC" (DS60001573 4.9):
// with PLCA on, the PHY holds CRS up until this node's transmit opportunity
// and signals COL if it must yield, so an ordinary half-duplex MAC is exactly
// what it wants. Frames arrive complete (preamble + SFD + ... + FCS) from the
// SGMII side through a frame FIFO and are sent as they are.
//
// TX (tx_clk, 2.5 MHz, TXD/TX_EN change on the rising edge):
//   defer while CRS, then 96 bit times (24 nibble clocks) of IFG, send a
//   fresh preamble + SFD and the frame (the FIFO holds DA..FCS + an end marker);
//   on COL: 32-bit jam, abort, binary exponential backoff (slot = 512 bit
//   times = 128 nibble clocks, k = min(attempts, 10)), retry; after 16
//   attempts drop the frame (IEEE 802.3 4.2.3.2.5)
// RX (rx_clk): RX_DV nibbles -> bytes, byte-aligned on the SFD; RX_ER or a
//   frame shorter than 64 bytes after the SFD is dropped
`default_nettype none
module mii_hd_mac #(
    parameter integer SLOT_SHIFT = 7          // slot = 2^7 nibble clocks = 512 bit times; less only to shorten simulations
) (
    // ---- TX
    input  wire       tx_clk,
    input  wire       tx_rst,
    input  wire       crs,
    input  wire       col,
    output reg        mii_tx_en,
    output reg  [3:0] mii_txd,
    input  wire       f_empty,        // frame FIFO read side
    input  wire [7:0] f_data,
    input  wire       f_last,
    output reg        f_re,
    output reg        f_rewind,
    output reg        f_commit,
    output reg  [4:0] attempts_out,
    // ---- RX
    input  wire       rx_clk,
    input  wire       rx_rst,
    input  wire       mii_rx_dv,
    input  wire       mii_rx_er,
    input  wire [3:0] mii_rxd,
    input  wire       w_full,         // FIFO full: the frame being written is lost
    output reg        w_we,
    output reg  [7:0] w_data,
    output reg        w_last,
    output reg        w_commit,
    output reg        w_abort
);
    // ================================================================= TX
    // crs/col come from the PHY in its own timing; two flops each
    reg [1:0] crs_s, col_s;
    always @(posedge tx_clk) begin crs_s <= {crs_s[0], crs}; col_s <= {col_s[0], col}; end
    wire crs_q = crs_s[1], col_q = col_s[1];
    localparam S_IDLE = 0, S_IFG = 1, S_PRE = 2, S_LO = 3, S_HI = 4, S_JAM = 5, S_BACKOFF = 6, S_DROP = 7;
    reg [2:0]  st;
    reg [17:0] cnt;                        // backoff reaches 1023 x 128 nibble clocks
    reg [4:0]  attempts;
    reg [15:0] lfsr;
    reg [3:0]  hi_nib;
    // after the n-th collision r is uniform in [0, 2^min(n,10)); attempts is n-1 here
    wire [4:0] ncol = attempts + 1'b1;
    wire [9:0] mask = (ncol >= 10) ? 10'h3FF : ((10'h1 << ncol) - 1'b1);
    always @(posedge tx_clk) begin
        f_re <= 1'b0; f_rewind <= 1'b0; f_commit <= 1'b0;
        lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
        attempts_out <= attempts;
        if (tx_rst) begin
            st <= S_IDLE; mii_tx_en <= 1'b0; mii_txd <= 0; attempts <= 0; cnt <= 0; lfsr <= 16'hACE1;
        end else case (st)
            S_IDLE: begin
                mii_tx_en <= 1'b0;
                if (!f_empty && !crs_q) begin st <= S_IFG; cnt <= 0; end
            end
            S_IFG: begin                                           // 96 bit times after carrier drops
                if (crs_q) cnt <= 0;
                else if (cnt == 16'd23) begin st <= S_PRE; cnt <= 0; end
                else cnt <= cnt + 1'b1;
            end
            S_PRE: begin                                           // 15 x 5, then the SFD's D
                if (col_q) begin st <= S_JAM; cnt <= 0; end
                else begin
                    mii_tx_en <= 1'b1; mii_txd <= (cnt == 16'd15) ? 4'hD : 4'h5;
                    if (cnt == 16'd15) st <= S_LO; else cnt <= cnt + 1'b1;
                end
            end
            S_LO: begin                                            // low nibble first
                if (col_q) begin st <= S_JAM; cnt <= 0; end
                else if (f_last) begin                             // end marker: frame sent
                    mii_tx_en <= 1'b0; f_re <= 1'b1; f_commit <= 1'b1; attempts <= 0; st <= S_IDLE;
                end else begin
                    mii_tx_en <= 1'b1; mii_txd <= f_data[3:0]; hi_nib <= f_data[7:4]; f_re <= 1'b1;
                    st <= S_HI;
                end
            end
            S_HI: begin
                if (col_q) begin st <= S_JAM; cnt <= 0; end
                else begin mii_txd <= hi_nib; st <= S_LO; end
            end
            S_JAM: begin                                           // 32 bits = 8 nibbles
                mii_tx_en <= 1'b1; mii_txd <= 4'h5;
                if (cnt == 16'd7) begin
                    mii_tx_en <= 1'b0;
                    f_rewind <= 1'b1;                              // back to the frame's start
                    if (attempts == 5'd15) st <= S_DROP;           // 16th attempt: give up
                    else begin
                        attempts <= attempts + 1'b1;
                        cnt <= {8'd0, lfsr[9:0] & mask} << SLOT_SHIFT;   // r slots x 128 nibble clocks
                        st <= S_BACKOFF;
                    end
                end else cnt <= cnt + 1'b1;
            end
            S_BACKOFF: begin
                if (cnt == 0) st <= S_IDLE; else cnt <= cnt - 1'b1;
            end
            S_DROP: begin                                          // read through to the marker, free it
                // every other clock, as in LO/HI: f_re is registered, so the
                // entry shown only moves on the clock after it
                if (!f_rewind && !f_re) begin
                    f_re <= 1'b1;
                    if (f_last) begin f_commit <= 1'b1; attempts <= 0; st <= S_IDLE; end
                end
            end
            default: st <= S_IDLE;
        endcase
    end

    // ================================================================= RX
    reg [3:0]  lo;
    reg        have_lo, aligned, bad;
    reg        dv_q;
    reg [10:0] nbytes;
    always @(posedge rx_clk) begin
        w_we <= 1'b0; w_commit <= 1'b0; w_abort <= 1'b0; w_last <= 1'b0;
        dv_q <= mii_rx_dv;
        if (rx_rst) begin aligned <= 1'b0; have_lo <= 1'b0; bad <= 1'b0; nbytes <= 0; end
        else if (mii_rx_dv) begin
            if (mii_rx_er || (w_we && w_full)) bad <= 1'b1;
            if (!aligned) begin
                // preamble nibbles are 5; the SFD is 5 then D. Only the frame
                // after the SFD goes into the FIFO; the SGMII side makes a new preamble.
                if (mii_rxd == 4'hD && have_lo) begin
                    aligned <= 1'b1; have_lo <= 1'b0; nbytes <= 0;
                end else begin have_lo <= (mii_rxd == 4'h5); lo <= mii_rxd; end
            end else if (!have_lo) begin lo <= mii_rxd; have_lo <= 1'b1; end
            else begin
                have_lo <= 1'b0;
                w_we <= 1'b1; w_data <= {mii_rxd, lo}; nbytes <= nbytes + 1'b1;
            end
        end else if (dv_q) begin                                   // end of frame
            if (aligned && !bad && nbytes >= 11'd64) begin
                w_we <= 1'b1; w_data <= 8'h00; w_last <= 1'b1;    // end marker (not transmitted)
                w_commit <= 1'b1;
            end else w_abort <= 1'b1;
            aligned <= 1'b0; have_lo <= 1'b0; bad <= 1'b0;
        end
    end
endmodule
`default_nettype wire
