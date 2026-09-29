// Asynchronous frame FIFO with rewind on BOTH sides.
//
//   write side: bytes go in speculatively; wr_commit publishes the frame,
//               wr_abort throws it away (bad frame, RX_ER, overflow)
//   read side:  a reader only sees committed frames; rd_rewind goes back to
//               the start of the frame being read (collision -> retry),
//               rd_commit frees it (sent, or given up after 16 attempts)
//
// Pointers cross clock domains in Gray code, two flops each way. Entries are
// {last, byte}.
`default_nettype none
module frame_fifo #(parameter AW = 12) (     // 2^12 = 4096 bytes: two full frames
    input  wire        wclk, wrst,
    input  wire        we,
    input  wire [7:0]  wdata,
    input  wire        wlast,
    input  wire        wr_commit,
    input  wire        wr_abort,
    output wire        wfull,
    input  wire        rclk, rrst,
    input  wire        re,
    output wire [7:0]  rdata,
    output wire        rlast,
    output wire        rempty,           // no committed byte left to read
    input  wire        rd_rewind,
    input  wire        rd_commit
);
    reg [8:0] mem [0:(1 << AW) - 1];
    function [AW:0] b2g(input [AW:0] b); b2g = b ^ (b >> 1); endfunction
    function [AW:0] g2b(input [AW:0] g); integer i; begin
        g2b[AW] = g[AW]; for (i = AW - 1; i >= 0; i = i - 1) g2b[i] = g2b[i + 1] ^ g[i]; end endfunction

    // ---- write domain
    reg [AW:0] wp, wc;                      // write pointer, committed write pointer
    reg [AW:0] rc_g1, rc_g2;                // reader's committed pointer, synced
    wire [AW:0] rc_w = g2b(rc_g2);
    assign wfull = (wp[AW-1:0] == rc_w[AW-1:0]) && (wp[AW] != rc_w[AW]);
    always @(posedge wclk) begin
        {rc_g2, rc_g1} <= {rc_g1, b2g(rc)};
        if (wrst) begin wp <= 0; wc <= 0; end
        else begin
            if (we && !wfull) begin mem[wp[AW-1:0]] <= {wlast, wdata}; wp <= wp + 1'b1; end
            if (wr_abort) wp <= wc;
            else if (wr_commit) wc <= (we && !wfull) ? wp + 1'b1 : wp;
        end
    end
    // ---- read domain
    reg [AW:0] rp, rc;                      // read pointer, committed read pointer
    reg [AW:0] wc_g1, wc_g2;
    wire [AW:0] wc_r = g2b(wc_g2);
    reg [AW:0] wc_gw;                       // Gray of the write commit, registered in wclk
    always @(posedge wclk) wc_gw <= b2g(wc);
    assign rempty = (rp == wc_r);
    assign {rlast, rdata} = mem[rp[AW-1:0]];
    always @(posedge rclk) begin
        {wc_g2, wc_g1} <= {wc_g1, wc_gw};
        if (rrst) begin rp <= 0; rc <= 0; end
        else begin
            if (rd_rewind) rp <= rc;
            else if (re && !rempty) rp <= rp + 1'b1;
            if (rd_commit) rc <= (re && !rempty) ? rp + 1'b1 : rp;
        end
    end
endmodule
`default_nettype wire
