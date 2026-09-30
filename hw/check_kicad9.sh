#!/bin/sh
# Independent check of a board with KiCad 9 (official Docker image), the way a
# reviewer opening the project would see it:
#   - DRC (on the saved zone fills) with schematic parity (every pad's net and every
#     footprint against the schematic), all severities
#   - ERC on the schematic
# The generator runs on KiCad 7; this catches what KiCad 7's python and
# kicad-cli (no drc/erc there) cannot. Writes <design>/kicad9-drc.rpt and
# kicad9-erc.rpt and prints a summary. Exit code 1 on any finding (errors or
# warnings) other than KiCad 9's newer library revisions.
#
#   sh check_kicad9.sh t1        sh check_kicad9.sh rj45
set -e
NAME=${1:?design name, e.g. t1}
HW=$(cd "$(dirname "$0")" && pwd)
IMG=kicad/kicad:9.0
# KICAD9_NATIVE=1: already inside a KiCad 9 environment (the CI job runs in the
# same image), so no docker-in-docker
if [ -n "$KICAD9_NATIVE" ]; then RUN="sh -c"; cd "$HW/$NAME"; export HOME=${HOME:-/tmp}
else RUN="docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $HW:/hw -w /hw/$NAME $IMG sh -c"; fi
$RUN '
set -e
N='"$NAME"'
# the image has the libraries but no per-user tables: give it the defaults,
# as a fresh KiCad install would
mkdir -p $HOME/.config/kicad/9.0
cp /usr/share/kicad/template/fp-lib-table /usr/share/kicad/template/sym-lib-table $HOME/.config/kicad/9.0/
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
# the only findings allowed: KiCad 9 carrying newer revisions of the same
# library footprints / symbols than the KiCad 7 copies embedded in the design
OK = {"lib_footprint_mismatch", "lib_symbol_mismatch"}
other = sorted({f"DRC {t}" for (s, t) in viol if t not in OK} | {f"ERC {t}" for (s, t) in erc if t not in OK})
bad = sum(n for (s, t), n in viol.items() if t not in OK) + len(d["unconnected_items"]) + sum(par.values()) + sum(n for (s, t), n in erc.items() if t not in OK)
print("RESULT   ", "PASS" if not bad else "FAIL (%d: %s)" % (bad, ", ".join(other) or "unconnected/parity"))
sys.exit(1 if bad else 0)
EOF
'
