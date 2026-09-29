// SGMII rate adaptation for 10 Mb/s (Cisco SGMII spec: every byte is
// replicated 100 times on the 1.25 Gbaud line).
//
// to_line:   entries from a byte source (bytes, then an end marker) become
//            gmii_tx_en / gmii_txd holding each byte for 100 clocks.
// from_line: gmii_rx_dv / gmii_rxd at 125 MHz become one byte strobe per 100
//            clocks, sampled mid-copy (copy 50 of 100) so a PCS that shrank
//            the preamble by a code group or two changes nothing.
`default_nettype none
module sgmii_rate10 (
    input  wire       clk,
    input  wire       rst,
    // ---- towards the host (TX): a byte source that shows one entry at a time
    output reg        req,          // consume the entry shown (one-clock pulse)
    input  wire       avail,        // an entry is shown
    input  wire [7:0] byte_in,
    input  wire       end_in,       // the entry shown is the end-of-frame marker
    output reg        gmii_tx_en,
    output reg  [7:0] gmii_txd,
    // ---- from the host (RX)
    input  wire       gmii_rx_dv,
    input  wire [7:0] gmii_rxd,
    output reg        rx_stb,       // one pulse per recovered byte
    output reg  [7:0] rx_byte,
    output reg        rx_end        // pulse after the last byte of a frame
);
    // ------------------------------------------------------------ TX
    // every 100 clocks take the next entry: a byte is held for 100 clocks,
    // the end marker drops tx_en; a short gap separates frames
    reg [6:0] tcnt;
    reg [3:0] gap;
    always @(posedge clk) begin
        req <= 1'b0;
        if (rst) begin gmii_tx_en <= 1'b0; tcnt <= 0; gap <= 0; end
        else if (gmii_tx_en) begin
            if (tcnt == 7'd99) begin
                tcnt <= 0;
                if (avail) begin
                    req <= 1'b1;
                    if (end_in) begin gmii_tx_en <= 1'b0; gap <= 4'd15; end
                    else gmii_txd <= byte_in;
                end else begin gmii_tx_en <= 1'b0; gap <= 4'd15; end   // underrun: end the frame
            end else tcnt <= tcnt + 1'b1;
        end else if (gap != 0) gap <= gap - 1'b1;
        else if (avail && !end_in && !req) begin
            gmii_tx_en <= 1'b1; gmii_txd <= byte_in; tcnt <= 0; req <= 1'b1;
        end else if (avail && end_in && !req) req <= 1'b1;             // stray marker: drop it
    end
    // ------------------------------------------------------------ RX
    reg [6:0] rcnt;
    reg       rdv_q;
    always @(posedge clk) begin
        rx_stb <= 1'b0; rx_end <= 1'b0;
        rdv_q <= gmii_rx_dv;
        if (rst) rcnt <= 0;
        else if (gmii_rx_dv) begin
            if (!rdv_q) rcnt <= 7'd1;
            else rcnt <= (rcnt == 7'd99) ? 7'd0 : rcnt + 1'b1;
            if (rcnt == 7'd50) begin rx_stb <= 1'b1; rx_byte <= gmii_rxd; end
        end else if (rdv_q) rx_end <= 1'b1;
    end
endmodule
`default_nettype wire
