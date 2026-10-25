"""Common-emitter amplifier (2N3904, divider bias, bypassed emitter) — a small, complete example.
Reference netlist: circuit.cir. Check it:  python ../../scripts/msa.py check build.py --cir circuit.cir --tran 10e-3 --dt 5e-6
Layout: +12 V rail on top (y=117), ground rail at the bottom (y=468), signal left -> right.
Pin offsets come from `msa.py parts` (e.g. NPN3904: C=(0,0), B=(-27,36), E=(0,72); R_v: 1 top, 2 = +45).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import msgen

d = msgen.Doc()
A, W, J = d.add, d.wire, d.junction
TOP, BOT = 117, 468

# ---- parts: reference designators == circuit.cir element names ----
V1 = A("VDC", "V1", 12, at=(81, 288), pin="1")                 # supply, pin 1 = +
V2 = A("VAC", "V2", (0.01, 1e3), at=(153, 297), pin="1")       # 10 mV peak, 1 kHz input
G = A("GND", "0", at=(81, 504), pin="1")
C1 = A("C_h", "C1", 10e-6, at=(198, 261), pin="2")             # input coupling
R1 = A("R_v", "R1", 47e3, at=(297, 162), pin="1")              # bias divider, top
R2 = A("R_v", "R2", 10e3, at=(297, 315), pin="1")              # bias divider, bottom
Q1 = A("NPN3904", "Q1", at=(342, 261), pin="B")                # C=(369,225) E=(369,297)
R3 = A("R_v", "R3", 4.7e3, at=(369, 153), pin="1")             # collector load
R4 = A("R_v", "R4", 1e3, at=(369, 351), pin="1")               # emitter resistor
C2 = A("C_v", "C2", 100e-6, at=(432, 351), pin="1")            # emitter bypass
C3 = A("C_h", "C3", 10e-6, at=(414, 207), pin="2")             # output coupling
R5 = A("R_v", "R5", 10e3, at=(504, 252), pin="1")              # load

# ---- +12 V rail ----
jr = J(297, TOP)
W(V1["1"], jr, via=[(81, TOP)], net="vcc")
W(jr, R1["1"])
W(jr, R3["1"], via=[(369, TOP)])

# ---- ground rail (a junction wherever a branch drops onto it) ----
gx = [81, 153, 297, 369, 432]
gj = {x: J(x, BOT) for x in gx}
for a, b in zip(gx, gx[1:]):
    W(gj[a], gj[b])
W(V1["2"], gj[81]); W(gj[81], G["1"])
W(V2["2"], gj[153]); W(R2["2"], gj[297]); W(R4["2"], gj[369]); W(C2["2"], gj[432])
W(gj[432], R5["2"], via=[(504, BOT)])

# ---- input and base ----
W(V2["1"], C1["2"], via=[(153, 261)], net="in")
jb = J(297, 261)
W(C1["1"], jb, net="b"); W(R1["2"], jb); W(jb, R2["1"]); W(jb, Q1["B"])

# ---- collector and output ----
jc = J(369, 207)
W(R3["2"], jc, net="c"); W(jc, Q1["C"]); W(jc, C3["2"])
jo = J(504, 207)
W(C3["1"], jo, net="out"); W(jo, R5["1"])

# ---- emitter ----
je = J(369, 333)
W(Q1["E"], je, net="e"); W(je, R4["1"]); W(je, C2["1"], via=[(432, 333)])

# ---- probes, title, simulation settings ----
d.probe("PR1", 324, 261, show=False, node="b")
d.probe("PR2", 396, 207, show=False, node="c")
d.probe("PR3", 486, 207, show=False, node="out")
d.text("Common-emitter amplifier (2N3904)", 36, 27, size=12, bold=True)
d.sim_settings(tstop=10e-3, tmax=5e-6, ic="auto")       # 1 kHz -> period 1 ms; tmax well below period/40
print(d.save("ce_amplifier"))
