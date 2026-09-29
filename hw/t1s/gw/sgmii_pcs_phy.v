// SGMII PCS, PHY side, one 10-bit code group per clock (125 MHz).
//
// The SFP is the PHY end of the SGMII link, so unlike a MAC-side PCS it
// ANNOUNCES the link: its transmitted config word carries link-up, full
// duplex and the speed (10 Mb/s for 10BASE-T1S), and it waits for the MAC to
// acknowledge. Per the Cisco SGMII spec (ENG-46158 r1.8) the PHY sends
// tx_config = 16'b1_A_0_1_00_0000000001 (link, ack, full duplex, 10M, SGMII)
// and the MAC answers 16'h4001.
//
// TX:  /C1/ /C2/ config sets during auto-negotiation, then /I2/ idles; a frame
//      from the gmii_* side goes out as /S/ data.. /T/ /R/ [/R/] with the
//      ordered sets on even code-group boundaries (IEEE 802.3 36.2.4).
// RX:  word alignment on the K28.5 comma (a 20-bit window, 10 phases), sync
//      after 3 commas, config capture, /S/../T/ frame extraction.
//
// Rate adaptation (the x100 replication of 10 Mb/s) is NOT here - see
// sgmii_rate10.v. This block moves bytes at the line's full code-group rate.
`default_nettype none
module sgmii_pcs_phy #(
    parameter [15:0] ABILITY = 16'h9001,      // link | full duplex | 10M | SGMII
    parameter integer LINK_TIMER = 200000,    // 1.6 ms at 125 MHz (SGMII link timer)
    parameter integer MAC_SIDE = 0            // 1: behave as the MAC end (for testing):
                                              //    any SGMII config from the partner completes AN
) (
    input  wire       clk,
    input  wire       rst,
    // from the SerDes: raw 10-bit words, unaligned; q[9] = first bit received
    input  wire [9:0] rx_raw,
    // to the SerDes
    output reg  [9:0] tx_code,
    // byte side (MAC-facing data of this PHY): what goes out to the host...
    input  wire       gmii_tx_en,
    input  wire [7:0] gmii_txd,
    // ...and what comes in from it
    output reg        gmii_rx_dv,
    output reg  [7:0] gmii_rxd,
    output reg        gmii_rx_er,
    // status
    output wire       rx_sync,
    output reg        an_done,
    output reg [15:0] partner_config
);
    // ------------------------------------------------------------ constants
    localparam [7:0] K28_5 = 8'hBC, K27_7 = 8'hFB, K29_7 = 8'hFD, K23_7 = 8'hF7;
    localparam [7:0] D21_5 = 8'hB5, D2_2 = 8'h42, D16_2 = 8'h50, D5_6 = 8'hC5;

    // ------------------------------------------------------------ RX align
    reg  [19:0] win;
    reg  [3:0]  phase;
    reg  [9:0]  rx_al;
    reg  [2:0]  commas;
    reg         synced;
    assign rx_sync = synced;
    wire [9:0] cand [0:9];
    genvar g;
    generate for (g = 0; g < 10; g = g + 1) begin : cw
        assign cand[g] = win[19 - g -: 10];
    end endgenerate
    function is_comma(input [9:0] w);
        is_comma = (w[9:3] == 7'b0011111) || (w[9:3] == 7'b1100000);
    endfunction
    integer i;
    reg found; reg [3:0] fphase;
    always @* begin
        found = 1'b0; fphase = phase;
        for (i = 0; i < 10; i = i + 1)
            if (!found && is_comma(cand[i])) begin found = 1'b1; fphase = i[3:0]; end
    end
    always @(posedge clk) begin
        win <= {win[9:0], rx_raw};
        if (rst) begin
            phase <= 0; commas <= 0; synced <= 1'b0;
        end else if (!synced) begin
            if (found) begin
                if (fphase == phase) begin
                    if (commas == 3'd2) synced <= 1'b1;
                    commas <= commas + 1'b1;
                end else begin
                    phase <= fphase; commas <= 3'd1;
                end
            end
        end
        rx_al <= cand[phase];
    end

    // ------------------------------------------------------------ RX decode
    wire [7:0] rd_d; wire rd_k, rd_err, rd_neu, rd_pos;
    dec8b10b dec(.q(rx_al), .d(rd_d), .k(rd_k), .err(rd_err), .rd_neutral(rd_neu), .rd_pos(rd_pos));
    reg [2:0] cstate;            // 0: expect K28.5, 1: after K28.5, 2: cfg lo, 3: cfg hi
    reg [7:0] cfg_lo;
    reg [15:0] cfg_last;
    reg [1:0]  cfg_same;
    reg        in_frame;
    reg        rx_cfg_seen;      // a config ordered set arrived recently
    reg [7:0]  cfg_age;
    always @(posedge clk) begin
        gmii_rx_dv <= 1'b0; gmii_rx_er <= 1'b0;
        if (rst || !synced) begin
            cstate <= 0; in_frame <= 1'b0; cfg_same <= 0; rx_cfg_seen <= 1'b0; cfg_age <= 0;
            partner_config <= 16'h0000;
        end else begin
            if (cfg_age != 8'hFF) cfg_age <= cfg_age + 1'b1; else rx_cfg_seen <= 1'b0;
            if (in_frame) begin
                if (rd_k && rd_d == K29_7) in_frame <= 1'b0;                 // /T/
                else if (rd_k || rd_err) begin in_frame <= 1'b0; gmii_rx_er <= 1'b1; end
                else begin gmii_rx_dv <= 1'b1; gmii_rxd <= rd_d; end
            end else if (rd_k && rd_d == K27_7) begin                         // /S/ = first preamble byte
                in_frame <= 1'b1; gmii_rx_dv <= 1'b1; gmii_rxd <= 8'h55;
                cstate <= 0;
            end else begin
                case (cstate)
                    0: if (rd_k && rd_d == K28_5) cstate <= 1;
                    1: cstate <= (!rd_k && (rd_d == D21_5 || rd_d == D2_2)) ? 3'd2 : 3'd0;   // /C1/ /C2/ ; else idle
                    // config bytes are data code groups; a K here means it was not a config set
                    2: if (rd_k) cstate <= 0; else begin cfg_lo <= rd_d; cstate <= 3; end
                    3: begin
                        cstate <= 0;
                        if (!rd_k) begin
                            rx_cfg_seen <= 1'b1; cfg_age <= 0;
                            cfg_last <= {rd_d, cfg_lo};
                            // accept a word only after it arrived three times in a row
                            if ({rd_d, cfg_lo} == cfg_last) begin
                                if (cfg_same != 2'd3) cfg_same <= cfg_same + 1'b1;
                                if (cfg_same >= 2'd1) partner_config <= {rd_d, cfg_lo};
                            end else cfg_same <= 0;
                        end
                    end
                    default: cstate <= 0;
                endcase
            end
        end
    end

    // ------------------------------------------------------------ AN (PHY side)
    // 0 CONFIG: send ABILITY until the MAC's config (bit 14 ack, bit 0) is seen
    // 1 ACK:    send ABILITY | ack for the link timer
    // 2 DATA:   idles and frames; back to CONFIG if the MAC restarts
    reg [1:0]  an;
    reg [17:0] timer;
    wire mac_ack = MAC_SIDE ? partner_config[0] : (partner_config[14] && partner_config[0]);
    always @(posedge clk) begin
        if (rst || !synced) begin an <= 0; timer <= 0; an_done <= 1'b0; end
        else case (an)
            0: if (mac_ack) begin an <= 1; timer <= 0; end
            1: if (timer == LINK_TIMER - 1) begin an <= 2; an_done <= 1'b1; end else timer <= timer + 1'b1;
            2: if (rx_cfg_seen && !mac_ack) begin an <= 0; an_done <= 1'b0; end   // MAC restarted AN
            default: an <= 0;
        endcase
    end

    // ------------------------------------------------------------ TX
    reg        rd;                      // running disparity: 0 = RD-, 1 = RD+
    reg [7:0]  e_d; reg e_k;
    wire [9:0] e_q; wire e_rd;
    enc8b10b enc(.d(e_d), .k(e_k), .rd_in(rd), .q(e_q), .rd_out(e_rd));
    reg        even;                    // next code group is at an even position
    reg [1:0]  cpos;                    // position inside a 4-group ordered set
    reg        cfg2;                    // alternate /C1/ and /C2/
    reg [2:0]  ts;                      // 0 idle 1 frame 2 /R/ after /T/
    wire [15:0] txcfg = (an == 1 || an == 2) ? (ABILITY | 16'h4000) : ABILITY;
    reg        cfg_mode;                // sending /C/ sets; follows (an != 2) only at set boundaries
    always @* begin
        e_d = K28_5; e_k = 1'b1;
        if (cfg_mode) begin                         // configuration ordered sets
            case (cpos)
                0: begin e_d = K28_5; e_k = 1'b1; end
                1: begin e_d = cfg2 ? D2_2 : D21_5; e_k = 1'b0; end
                2: begin e_d = txcfg[7:0]; e_k = 1'b0; end
                3: begin e_d = txcfg[15:8]; e_k = 1'b0; end
            endcase
        end else case (ts)
            0: if (gmii_tx_en && even) begin e_d = K27_7; e_k = 1'b1; end      // /S/
               else if (even) begin e_d = K28_5; e_k = 1'b1; end               // /I/ first half
               // after the K28.5, rd = 1 means the set began RD-: /I2/ (D16.2)
               // brings it back to RD-; rd = 0 means it began RD+: /I1/ (D5.6)
               else begin e_d = rd ? D16_2 : D5_6; e_k = 1'b0; end
            1: if (gmii_tx_en) begin e_d = gmii_txd; e_k = 1'b0; end
               else begin e_d = K29_7; e_k = 1'b1; end                         // /T/
            2: begin e_d = K23_7; e_k = 1'b1; end                               // /R/
            default: ;
        endcase
    end
    always @(posedge clk) begin
        if (rst) begin rd <= 1'b0; even <= 1'b1; cpos <= 0; cfg2 <= 1'b0; ts <= 0; cfg_mode <= 1'b1;
                       tx_code <= 10'b0011111010; end
        else begin
            tx_code <= e_q; rd <= e_rd; even <= ~even;
            if (cfg_mode && cpos == 3 && an == 2) cfg_mode <= 1'b0;         // after a whole /C/ set
            else if (!cfg_mode && an != 2 && ts == 0 && !even) cfg_mode <= 1'b1;   // next group is even
            if (cfg_mode) begin
                cpos <= cpos + 1'b1;
                if (cpos == 3) cfg2 <= ~cfg2;
                ts <= 0;
            end else begin
                cpos <= 0;
                case (ts)
                    0: if (gmii_tx_en && even) ts <= 1;
                    1: if (!gmii_tx_en) ts <= 2;                                    // /T/ sent
                    2: if (!even) ts <= 0; else ts <= 2;                            // /R/ until the next idle is even
                    default: ts <= 0;
                endcase
            end
        end
    end
endmodule
`default_nettype wire
