#!/bin/sh
# Independent check of a board with KiCad 9 (official Docker image), the way a
# reviewer opening the project would see it:
#   - DRC (on the saved zone fills) with schematic parity (every pad's net and every
#     footprint against the schematic), all severities
#   - ERC on the schematic
# The generator runs on KiCad 7; this catches what KiCad 7's python and
# kicad-cli (no drc/erc there) cannot. Writes <design>/kicad9-drc.rpt and
# kicad9-erc.rpt and prints a summary. Exit code 1 if anything but the
# expected warnings remains.
#
#   sh check_kicad9.sh t1        sh check_kicad9.sh rj45
set -e
NAME=${1:?design name, e.g. t1}
HW=$(cd "$(dirname "$0")" && pwd)
IMG=kicad/kicad:9.0
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$HW:/hw" -w "/hw/$NAME" "$IMG" sh -c '
set -e
N='"$NAME"'
# the image has the libraries but no per-user tables: give it the defaults,
# as a fresh KiCad install would
mkdir -p /tmp/.config/kicad/9.0
cp /usr/share/kicad/template/fp-lib-table /usr/share/kicad/template/sym-lib-table /tmp/.config/kicad/9.0/
kicad-cli pcb drc --schematic-parity --severity-all -o kicad9-drc.rpt $N.kicad_pcb >/dev/null 2>&1 || true
kicad-cli pcb drc --schematic-parity --severity-all --format json -o /tmp/drc.json $N.kicad_pcb >/dev/null 2>&1 || true
kicad-cli sch erc --severity-all -o kicad9-erc.rpt $N.kicad_sch >/dev/null 2>&1 || true
kicad-cli sch erc --severity-all --format json -o /tmp/erc.json $N.kicad_sch >/dev/null 2>&1 || true
python3 - <<EOF
import json, sys
from collections import Counter
d = json.load(open("/tmp/drc.json")); e = json.load(open("/tmp/erc.json"))
viol = Counter((v["severity"], v["type"]) for v in d["violations"])
par = Counter(v["type"] for v in d["schematic_parity"])
erc = Counter((v["severity"], v["type"]) for s in e["sheets"] for v in s["violations"])
print("KiCad", d.get("kicad_version", "?"))
print("DRC      ", dict(viol) or "clean")
print("unconnected", len(d["unconnected_items"]))
print("parity   ", dict(par) or "clean")
print("ERC      ", dict(erc) or "clean")
bad = sum(n for (s, t), n in viol.items() if s == "error") + len(d["unconnected_items"]) \
      + sum(par.values()) + sum(n for (s, t), n in erc.items() if s == "error")
print("RESULT   ", "PASS" if not bad else f"FAIL ({bad} errors)")
sys.exit(1 if bad else 0)
EOF
'
