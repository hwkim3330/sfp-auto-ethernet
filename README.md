# sfp-auto-ethernet

SFP 모듈 세 가지. 일반 SFP 슬롯에 꽂으면 호스트와 SerDes로 붙고, 바깥쪽은 차량 이더넷이나 RJ45로 나간다.

| 변형 | 바깥쪽 | PHY | 호스트 쪽 | 커넥터 | 상태 |
|---|---|---|---|---|---|
| [`t1`](hw/t1/) | **100/1000BASE-T1** | TI DP83TG720S (1000) / DP83TC812S (100): 핀 호환이라 PCB 하나로 둘 다 | SGMII 1.25 Gbaud | H-MTD (Rosenberger E6S20A) | **배선 완료, KiCad 9 검사 통과, 주문 파일 있음**. 실물은 아직 없음 |
| [`rj45`](hw/rj45/) | 100M / 1G / **2.5GBASE-T** | Realtek RTL8221B-VB | 2500BASE-X 3.125 Gbaud 또는 SGMII | RJ45 (Kinghelm KH-RJ45-58, 차폐) | 부품·배치 확정, **배선 중**. 주문 불가 |
| [`t1s`](hw/t1s/) | 10BASE-T1S | FPGA (SGMII PCS 브리지) + Microchip LAN8670 | SGMII 10 Mb/s | 2핀 | **게이트웨어만**: 시뮬레이션 통과. 보드 없음 |

![t1](hw/t1/fab/t1-top.png)

## 구조

```
 host SFP cage ── SerDes (AC 결합, 모듈 안) ──┐
                                              ▼
 I²C 0x50/0x51/0x56 ── STM32G031 ── MDIO ──► PHY ── (자기소자 / CMC) ── 커넥터
 TX_DISABLE · RX_LOS ──┘                      ▲
 3.3 V ── 페라이트 ── 부하 스위치(소프트 스타트) ── 벅 1.0 / 0.95 V ─┘
```

- **MCU 하나가 세 가지 일을 한다.** 호스트에게는 EEPROM(A0h/A2h)과 PHY 브리지(I²C 0x56)로 보이고, 링크 제어도 맡는다. 리눅스 `sfp` 드라이버가 기대하는 방식을 그대로 따랐다([docs/LINUX.md](docs/LINUX.md)).
- **데이터시트가 공개된 부품만 쓴다.** NDA가 필요한 PHY로는 설계도 유지보수도 못 한다. 88Q2112를 고르지 않은 이유다([docs/PARTS.md](docs/PARTS.md)).
- **T1S에는 SGMII PHY가 없다.** 그래서 작은 FPGA가 SGMII 10 Mb/s를 받아 MII로 바꾸고, 반이중 버퍼도 맡는다.

## 설계 원칙 (설계 검토 뒤)

- **적층은 F / GND / GND / B** (JLC04101H-3313, 1.0 mm)이다.
  - 두 안쪽 층 모두 GND다. In2에는 저속 신호도 지나가지만, 아래층(B)을 달리는 고속 쌍 밑에는 금지 구역을 두어 판을 온전히 남긴다.
  - 그래서 모든 고속 쌍이 어느 층에 있든 GND를 기준으로 삼는다.
- **고속 쌍은 손으로 결합해서 깐다.** 선폭 0.114, 간격 0.152로 약 100 Ω 차동이다.
  - 쌍 안의 두 선은 같은 층, 같은 비아 수로 간다.
  - 층을 바꾸는 곳 옆에는 GND 비아를 둔다.
  - 라우터(Freerouting)는 나머지 저속 신호만 맡는다.
- **3.3 V 인러시**: 핫플러그하면 호스트 필터가 전압을 수십 µs 만에 올린다. 그래서 모듈 입력에 **TPS22918 부하 스위치**(약 3.6 ms 상승)를 넣었다. MSA의 "정상 상태 대비 +30 mA 이내"를 설계로 맞췄다. **실물 측정은 아직이다.**
- **보드 몸통은 폭 11.8 mm**다. 탭은 9.2 mm, 케이지 안 높이 한도는 위 4.65 mm, 아래 1.65 mm다. 치수 출처는 [docs/SFP_MSA.md](docs/SFP_MSA.md)에 있다.

## 검증 (하드웨어 없이 할 수 있는 것)

| 무엇 | 도구 | 어디서 |
|---|---|---|
| DRC, 회로도-PCB 일치(parity), ERC | KiCad 9 (공식 Docker 이미지). 검토자가 여는 그대로 | `sh hw/check_kicad9.sh t1` |
| 펌웨어 빌드: 4가지 변형, 경고 0 | arm-none-eabi-gcc | `fw/`, CI |
| T1S 게이트웨어 | Icarus Verilog 테스트벤치 3개 | `hw/t1s/gw/`, CI |

- GitHub Actions([.github/workflows/check.yml](.github/workflows/check.yml))가 push할 때마다 위 셋을 다시 돌린다.
- KiCad 9 검사에서 허용하는 경고는 "라이브러리 사본이 다르다" 두 종류뿐이다. KiCad 9 라이브러리가 KiCad 7 원본보다 새 판이라서 생긴다.

## 아직 실물로만 확인할 수 있는 것

- **펌웨어는 보드에서 0회 돌았다.** 보드가 오면 확인할 것:
  - MDC/MDIO 타이밍, 시작 시퀀스, TX_DISABLE/RX_LOS 동작;
  - T1의 SGMII 극성 반전 비트.
- **인러시 전류와 3.3 V 상승 시간.** 오실로스코프로 잰다.
- **H-MTD 풋프린트.** `hw/t1/fab/t1-1to1.pdf`를 100 %로 인쇄하고 실물 커넥터를 대 본다.
- **골드 핑거.** JLC는 경질 금(hard gold)을 하지 않고 ENIG만 한다. MSA 규격(경질 금 ≥ 0.38 µm)은 아니다. 시험용 삽입 수십 회는 쓸 만하다. 반복 삽입이 많다면 경질 금을 하는 업체(예: PCBWay)에 맡긴다.
- **RJ45 코 폭 17 mm.** 잭 자체가 15.7 mm다. D10에서 옆 포트와 부딪히는지 실측해야 한다.

## Kontron D10에 꽂는다면

[docs/D10.md](docs/D10.md): D10의 SFP 포트는 **최대 2.5G**다.
- T1: `make HOST=d10` 펌웨어로 굽는다(1000BASE-X로 보이고 SGMII AN은 끈다).
- RJ45: 호스트 쪽을 2500BASE-X로 고정한다. D10이 2.5G-T 모듈을 속도 2500 고정에서만 붙이기 때문이다.

## 다음

1. RJ45 배선 마무리 → KiCad 9 검사 → 패널 → 주문 파일
2. T1S 보드: FPGA + LAN8670 + MCU
3. 하우징: 래치와 베일

## 참고

- 비슷한 상용 제품이 있다. 그러니 이 크기 안에 들어간다.
  - [Intrepid 88Q2112 SFP](https://intrepidcs.com/products/automotive-ethernet-tools/88q2112-1000base-t1-sfp/): 76.5 × 13.5 × 20.5 mm, H-MTD
  - [Technica TE-1441](https://technica-engineering.de/en-gb/hardware-products/sfp-sfp-modules): I²C → MDIO 게이트웨이, DIP 스위치
- 10G RJ45 SFP+는 만들지 않는다. 10GBASE-T PHY는 2.5–5 W를 쓰고 NDA 부품이다. 게다가 D10 포트는 2.5G까지다.
