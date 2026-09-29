# sfp-auto-ethernet

SFP 모듈 세 가지. 일반 SFP 슬롯에 꽂으면 호스트와 **SGMII**로 붙고, 바깥쪽은 차량 이더넷이나 RJ45로 나간다.

| 변형 | 바깥쪽 | PHY | 커넥터 | 상태 |
|---|---|---|---|---|
| [`t1`](hw/t1/) | **100/1000BASE-T1** | TI DP83TG720S (1000) / DP83TC812S (100) — 핀 호환이라 PCB 하나로 둘 다 | H-MTD | **회로도 ERC 0 · 4층 배선 DRC 0 · 거버 · 펌웨어** — 주문 전 2가지 남음 |
| [`rj45`](hw/rj45/) | 1000BASE-T | TI DP83869HM | 저프로파일 RJ45 | v0 배치 |
| [`t1s`](hw/t1s/) | 10BASE-T1S | Lattice CrossLink-NX (SGMII 브리지) + Microchip LAN8670 | 2핀 | v0 배치 |

![t1](hw/t1/fab/t1-top.png)

## 구조

```
 host SFP cage ── SGMII 1.25 Gbaud (AC 결합, 모듈 안) ──┐
                                                        ▼
 I²C 0x50/0x51/0x56 ── STM32G031 ── MDIO ──►  PHY  ── CMC / ESD ── 커넥터
 TX_DISABLE · RX_LOS ──┘                        ▲
 3.3 V ── 필터 ── 벅 1.0/1.1 V · LDO 2.5/1.8 V ─┘
```

- MCU 하나가 세 가지 일을 맡는다. 호스트 쪽에서는 EEPROM(A0h/A2h)이자 PHY 브리지(I²C 0x56)로 보이고, 링크 제어도 한다. 리눅스 `sfp` 드라이버가 기대하는 방식을 그대로 따랐다([docs/LINUX.md](docs/LINUX.md)).
- **데이터시트가 공개된 부품만 쓴다.** NDA가 필요한 PHY로는 설계도 유지보수도 못 한다. 88Q2112를 고르지 않은 이유다([docs/PARTS.md](docs/PARTS.md)).
- **T1S는 SGMII를 지원하는 PHY가 없다.** 그래서 작은 FPGA가 SGMII 10 Mb/s를 받아 MII로 변환하고, 반이중 버퍼도 맡는다. 게이트웨어가 필요해서 셋 중 가장 손이 많이 간다.

## 지금 된 것 (v0: 기구)

`python3 hw/make_boards.py`를 돌리면 아래가 만들어진다.

- **SFP 모듈 에지 커넥터 풋프린트**
  - `hw/fp/sfp.pretty/SFP_Module_Edge.kicad_mod`
  - INF-8074i Figure 2/3의 치수를 그대로 썼다: 0.8 피치, 0.6 폭, 윗면 +3.8/−3.4, 접지 0.5 · 전원 0.9 · 신호 1.3의 계단 배치.
  - 정리는 [docs/SFP_MSA.md](docs/SFP_MSA.md)에 있다.
- **변형 3종의 KiCad PCB**
  - 외형: 탭 폭 9.2, 몸통 폭 12.4
  - 에지 커넥터, 모든 부품 배치, 케이지 앞면 표시선
  - 4층
- **외피 검사**
  - 케이지 안쪽 부품이 높이 한도(PCB 위 4.65 mm, 아래 1.65 mm)를 넘지 않는지 본다.
  - 부품끼리 겹치지 않는지, 에지 핑거 위에 올라간 부품이 없는지도 본다.
  - 코에 달린 커넥터가 13.7 mm 폭을 넘지 않는지 본다.
  - **지금은 세 변형 모두 통과한다.**

## T1 모듈 (hw/t1/)

**회로도, 4층 배선, 거버, 펌웨어까지 다 됐다.**

| 항목 | 결과 |
|---|---|
| ERC | 0/0 |
| 회로도 ↔ 넷리스트 | 175핀 불일치 0 |
| DRC | 0, 미연결 0 |
| 펌웨어 | 1.7 KB, 경고 0 |

**주문하기 전에 두 가지가 남았다.** 자세한 건 [hw/t1/README.md](hw/t1/README.md)에 있다.

1. H-MTD 커넥터 풋프린트: 지금은 **자리표시**다. 실제 부품 도면으로 바꿔야 한다.
2. 적층과 SGMII 100 Ω 폭: 제작사 계산기 값으로 바꾸고, SGMII 쌍을 결합해서 손으로 다시 배선해야 한다.

펌웨어([fw/](fw/))는 STM32G031용 베어메탈이다.
- A0h EEPROM을 에뮬레이션한다. 바이트 6 = 1000BASE-T, 바이트 96이 master 설정이다.
- 0x56에 I²C → MDIO 브리지가 있다(리눅스 `mdio-i2c` 규약).
- TX_DISABLE이 걸리면 PHY를 리셋 상태로 잡아 둔다.
- 링크 상태를 RX_LOS로 내보낸다.

## 다음

1. T1: 커넥터 확정 → 임피던스 → SGMII 손배선 → **주문**
2. RJ45: 같은 생성기로 회로도·배선. DP83869HM 데이터시트에서 옮기고, 저프로파일 잭을 찾는다.
3. T1S: CrossLink-NX 게이트웨어(SGMII PCS + 10 Mb/s 속도 적응 + MII + 반이중 버퍼)
4. 하우징: 인쇄 셸이나 기성 셸. 래치와 베일도 필요하다.

## 참고

- 비슷한 상용 제품이 있다. 그러니 이 크기 안에 들어간다.
  - [Intrepid 88Q2112 SFP](https://intrepidcs.com/products/automotive-ethernet-tools/88q2112-1000base-t1-sfp/): 76.5 × 13.5 × 20.5 mm, H-MTD
  - [Technica TE-1441](https://technica-engineering.de/en-gb/hardware-products/sfp-sfp-modules): I²C → MDIO 게이트웨어, DIP 스위치
- 10G RJ45 SFP+는 만들지 않는다. 10GBASE-T PHY는 2.5–5 W를 쓰고, 10.3 Gbaud 신호 무결성까지 챙겨야 해서 사는 편이 맞다.
