"""Build script for __NAME__ — generates __NAME__.ms14 (via d.save) for `msa.py check`.

Runs as-is (a divider + RC low-pass driven by a sine source) so you can see the whole flow work first;
then replace the circuit with yours. Rules that keep the result correct and tidy:
  * Reference designators MUST equal the element names in __NAME__.cir (R1 here = R1 there).
  * Every coordinate is a multiple of 9. y grows downward. `msa.py parts` lists pin offsets and body boxes.
  * Always pass pin=...: the named pin lands exactly on at=(x, y).
  * Supply rail on top, ground rail at the bottom, signal flows left -> right.
  * A wire may only end on a pin or a junction. Where 3+ wires meet, create d.junction(x, y) and
    wire every branch to it. Never end a wire on the middle of another wire (lint FAILs it: not connected).
  * Wires are horizontal/vertical polylines: d.wire(a, b, via=[corner, ...]).
  * Put a probe on every node you want verified: d.probe("PRn", x, y, node="<cir node name>"),
    with (x, y) on a wire segment (not on a part body).
  * Set simulation settings explicitly: tmax <= period/40 of the fastest signal (default "calculate"
    produces garbage waveforms for anything fast); ic="auto" unless you need a from-zero start-up.
"""
import os
import sys

sys.path.insert(0, r"__SCRIPTS__")
import msgen

d = msgen.Doc(sheet="A")        # A: ~930 x 690 usable; use "B" or "C" for bigger circuits
A, W, J = d.add, d.wire, d.junction
TOP, BOT = 117, 405             # supply rail y, ground rail y

# ---- parts (ref designators == .cir names) -------------------------------------------
V1 = A("VAC", "V1", (1.0, 1e3), at=(108, 234), pin="1")      # 1 V peak, 1 kHz; pin 1 = +
G = A("GND", "0", at=(108, 441), pin="1")
R1 = A("R_h", "R1", 1e3, at=(198, TOP), pin="1")
R2 = A("R_v", "R2", 1e3, at=(306, 198), pin="1")
R3 = A("R_h", "R3", 1.6e3, at=(378, TOP), pin="1")
C1 = A("C_v", "C1", 100e-9, at=(504, 198), pin="1")

# ---- wiring -----------------------------------------------------------------------------
jg = J(108, BOT)                                   # ground rail, left end (3 wires meet: V1, G, rail)
W(V1["2"], jg)
W(jg, G["1"])
W(V1["1"], R1["1"], via=[(108, TOP)], net="in")
jm = J(306, TOP)                                   # divider mid-point: R1, R2, R3 meet
W(R1["2"], jm, net="mid")
W(jm, R2["1"])
W(jm, R3["1"])
jo = J(504, TOP)                                   # output node: R3, C1, scope meet
W(R3["2"], jo, net="out")
W(jo, C1["1"])
# oscilloscope: pins are on its bottom edge (1=A+, 4=A-, 2=B+, 5=B-), body sits above them —
# route into the pin from below so the wire never crosses the instrument body. A-/B- open = ground reference.
X = d.scope(at=(621, 315), pin="1")
W(jo, X["1"], via=[(585, TOP), (585, 342), (621, 342)])
jg2 = J(306, BOT)
W(R2["2"], jg2)
W(jg, jg2)
W(C1["2"], jg2, via=[(504, BOT)])

# ---- probes (node = .cir node name) -------------------------------------------------------
d.probe("PR1", 261, TOP, show=False, node="mid")
d.probe("PR2", 459, TOP, show=False, node="out")

# ---- title & simulation settings ------------------------------------------------------------
d.text("__NAME__", 36, 27, size=12, bold=True)
d.sim_settings(tstop=5e-3, tmax=2e-6, ic="auto")

print(d.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "__NAME__")))   # check needs this print
