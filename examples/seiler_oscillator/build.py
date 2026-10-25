"""Seiler oscillator 2.63 MHz + emitter-follower buffer. Reference: circuit.cir.
Check:  python ../../scripts/msa.py check build.py --cir circuit.cir --tran 300e-6 --dt 1e-8"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import msgen

d = msgen.Doc()
A = d.add; W = d.wire; J = d.junction
VCC, GND = 108, 540

# ---- parts ----
V1 = A("VDC", "V1", 9, at=(81, 297), pin="1")
G1 = A("GND", "0", at=(81, 576), pin="1")
L1 = A("L_v", "L1", 22e-6, at=(189, 315), pin="1")
RL1 = A("R_v", "RL1", 7.3, at=(189, 405), pin="1")
C13 = A("C_v", "C13", 30e-12, at=(252, 315), pin="1")
C14 = A("C_v", "C14", 4e-12, at=(306, 315), pin="1")
C12 = A("C_h", "C12", 180e-12, at=(333, 279), pin="2")
R3 = A("R_v", "R3", 10e3, at=(405, 189), pin="1")
R4 = A("R_v", "R4", 6.8e3, at=(405, 351), pin="1")
C10 = A("C_v", "C10", 1e-9, at=(459, 315), pin="1")
Q1 = A("NPN3904", "Q1", at=(495, 279), pin="B")
C11 = A("C_v", "C11", 1e-9, at=(459, 441), pin="1")
R5 = A("R_v", "R5", 3.9e3, at=(522, 441), pin="1")
C15 = A("C_h", "C15", 47e-12, at=(576, 405), pin="2")
R6 = A("R_v", "R6", 47e3, at=(657, 315), pin="1")
R7 = A("R_v", "R7", 47e3, at=(657, 450), pin="1")
Q2 = A("NPN3904", "Q2", at=(675, 405), pin="B")
R8 = A("R_v", "R8", 1e3, at=(702, 477), pin="1")
C16 = A("C_h", "C16", 10e-9, at=(738, 459), pin="2")
RL = A("R_v", "RLOAD", 1e3, at=(810, 477), pin="1")

# ---- supply rail VCC ----
jv1, jv2, jv3 = J(405, VCC), J(522, VCC), J(657, VCC)
W(V1["1"], jv1, via=[(81, VCC)], net="vcc")
W(jv1, jv2); W(jv2, jv3)
W(jv3, Q2["C"], via=[(702, VCC)])
W(jv1, R3["1"]); W(jv2, Q1["C"]); W(jv3, R6["1"])

# ---- ground rail ----
gx = [81, 189, 252, 306, 405, 459, 522, 657, 702, 810]
gj = {x: J(x, GND) for x in gx}
for a, b in zip(gx, gx[1:]):
    W(gj[a], gj[b], net="0" if a == 81 else None)
W(V1["2"], gj[81]); W(gj[81], G1["1"])
W(RL1["2"], gj[189]); W(C13["2"], gj[252]); W(C14["2"], gj[306]); W(R4["2"], gj[405])
W(C11["2"], gj[459]); W(R5["2"], gj[522]); W(R7["2"], gj[657]); W(R8["2"], gj[702]); W(RL["2"], gj[810])

# ---- tank osc_t ----
jt1, jt2 = J(252, 279), J(306, 279)
W(L1["1"], jt1, via=[(189, 279)], net="osc_t"); W(jt1, jt2); W(jt2, C12["2"])
W(jt1, C13["1"]); W(jt2, C14["1"])
W(L1["2"], RL1["1"])

# ---- base ----
jb1, jb2 = J(405, 279), J(459, 279)
W(C12["1"], jb1, net="osc_b"); W(jb1, jb2); W(jb2, Q1["B"])
W(R3["2"], jb1); W(jb1, R4["1"]); W(jb2, C10["1"])

# ---- emitter ----
je1, je2 = J(459, 405), J(522, 405)
W(Q1["E"], je2, net="osc_e"); W(C10["2"], je1); W(je1, je2); W(je2, C15["2"])
W(je1, C11["1"]); W(je2, R5["1"])

# ---- buffer ----
jq = J(657, 405)
W(C15["1"], jq, net="buf_b"); W(jq, Q2["B"]); W(R6["2"], jq); W(jq, R7["1"])
je3 = J(702, 459)
W(Q2["E"], je3, net="buf_e"); W(je3, R8["1"]); W(je3, C16["2"])
jo = J(810, 459)
W(C16["1"], jo, net="out"); W(jo, RL["1"])

# ---- scope: A+ = out, A- = ground ----
X = d.scope(at=(837, 351), pin="1")
W(jo, X["1"], via=[(810, 396), (837, 396)])
W(gj[810], X["4"], via=[(846, GND)])

# ---- title ----
d.text("Seiler oscillator  f0 = 2.63 MHz", 36, 27, size=12, bold=True)
d.text("Q1 oscillator (C10/C11 feedback, C12 series, L1 || C13 || C14 tank)   Q2 emitter follower   scope A = out", 36, 54, size=8, bold=False)

# ---- probes (node = name in circuit.cir) and simulation settings ----
d.probe("PR1", 792, 459, show=False, node="out")      # on the C16 -> RLOAD wire
d.probe("PR2", 216, 279, show=False, node="osc_t")    # on the tank wire
# 2.63 MHz -> period 380 ns; tmax 10 ns. ic="zero": an oscillator needs a kick, starting from the exact
# operating point it may never start (and ngspice would then disagree with Multisim).
d.sim_settings(tstop=300e-6, tmax=1e-8, ic="zero")
print(d.save("seiler_oscillator"))
