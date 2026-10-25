"""2.63 MHz high-level AM transmitter (collector modulation), C-size sheet, ~50 parts. Reference: circuit.cir.
Seiler oscillator -> emitter follower -> attenuator -> driver (CE + follower) -> class-C PA (collector-modulated)
-> pi match -> 50 ohm. Series modulator Q6 (follower) turns 12 V bias + 5 kHz audio into the PA supply Vpa.
Check:  python ../../scripts/msa.py check build.py --cir circuit.cir --tran 1.2e-3 --dt 1e-8"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import msgen

d = msgen.Doc(sheet="C")
A = d.add; W = d.wire; J = d.junction
V12, V9, GND = 81, 108, 540

# ================= parts =================
V2 = A("VDC", "V2", 12, at=(63, 297), pin="1")
V1 = A("VDC", "V1", 9, at=(126, 297), pin="1")
G1 = A("GND", "0", at=(63, 576), pin="1")
# Seiler oscillator
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
# buffer
C15 = A("C_h", "C15", 47e-12, at=(576, 405), pin="2")
R6 = A("R_v", "R6", 47e3, at=(657, 315), pin="1")
R7 = A("R_v", "R7", 47e3, at=(657, 450), pin="1")
Q2 = A("NPN3904", "Q2", at=(675, 405), pin="B")
R8 = A("R_v", "R8", 1e3, at=(702, 477), pin="1")
# attenuator (sets the drive level)
C16 = A("C_h", "C16", 100e-9, at=(738, 459), pin="2")
R9 = A("R_h", "R9", 390, at=(810, 459), pin="1")
R10 = A("R_v", "R10", 620, at=(882, 477), pin="1")
# driver: Q3 common emitter + Q4 emitter follower
C17 = A("C_h", "C17", 100e-9, at=(918, 351), pin="2")
R11 = A("R_v", "R11", 15e3, at=(990, 270), pin="1")
R12 = A("R_v", "R12", 2.7e3, at=(990, 387), pin="1")
Q3 = A("NPN3904", "Q3", at=(1017, 351), pin="B")
R13 = A("R_v", "R13", 470, at=(1044, 207), pin="1")
R14 = A("R_v", "R14", 47, at=(1044, 405), pin="1")
R15 = A("R_v", "R15", 51, at=(1044, 486), pin="1")
C18 = A("C_v", "C18", 1e-6, at=(1098, 468), pin="1")
Q4 = A("NPN2222", "Q4", at=(1098, 288), pin="B")
R16 = A("R_v", "R16", 220, at=(1152, 369), pin="1")
# class-C PA (zero bias: base to ground through L2, R17)
C19 = A("C_h", "C19", 100e-9, at=(1179, 351), pin="2")
L2 = A("L_v", "L2", 100e-6, at=(1251, 369), pin="1")
R17 = A("R_v", "R17", 4.7, at=(1251, 441), pin="1")
Q5 = A("NPN2222", "Q5", at=(1278, 351), pin="B")
L3 = A("L_v", "L3", 100e-6, at=(1305, 207), pin="1")
# pi network -> 50 ohm
C21 = A("C_v", "C21", 1.65e-9, at=(1359, 306), pin="1")
C22 = A("C_h", "C22", 100e-9, at=(1386, 288), pin="2")
L4 = A("L_h", "L4", 3.3e-6, at=(1458, 288), pin="1")
C23 = A("C_v", "C23", 2.32e-9, at=(1530, 306), pin="1")
RL = A("R_v", "RL", 50, at=(1584, 306), pin="1")
# series modulator (Q6 mirrored: base on the right)
C20 = A("C_v", "C20", 10e-9, at=(1737, 378), pin="1")
Q6 = A("NPN3904m", "Q6", at=(1845, 288), pin="B")
R20 = A("R_v", "R20", 1e3, at=(1818, 378), pin="1")
R18 = A("R_v", "R18", 6.8e3, at=(1872, 198), pin="1")
R19 = A("R_v", "R19", 5.6e3, at=(1872, 315), pin="1")
C24 = A("C_h", "C24", 10e-6, at=(1899, 288), pin="2")
V3 = A("VAC", "V3", (2.0, 5e3), at=(1944, 342), pin="1")

# ================= supplies =================
# +12 V rail (y=81): V2 -> driver, modulator
jv12 = {x: J(x, V12) for x in (990, 1044, 1125, 1818)}
W(V2["1"], jv12[990], via=[(63, V12)], net="vcc12")
W(jv12[990], jv12[1044]); W(jv12[1044], jv12[1125]); W(jv12[1125], jv12[1818])
W(jv12[1818], R18["1"], via=[(1872, V12)])
W(jv12[990], R11["1"]); W(jv12[1044], R13["1"]); W(jv12[1125], Q4["C"])
W(jv12[1818], Q6["C"])
# +9 V rail (y=108): V1 -> oscillator, buffer
jv1, jv2, jv3 = J(405, V9), J(522, V9), J(657, V9)
W(V1["1"], jv1, via=[(126, V9)], net="vcc9")
W(jv1, jv2); W(jv2, jv3)
W(jv3, Q2["C"], via=[(702, V9)])
W(jv1, R3["1"]); W(jv2, Q1["C"]); W(jv3, R6["1"])

# ================= ground rail (y=540) =================
gx = [63, 126, 189, 252, 306, 405, 459, 522, 657, 702, 882, 990, 1044, 1098, 1152, 1251, 1305, 1359,
      1530, 1584, 1737, 1818, 1872, 1944]
gj = {x: J(x, GND) for x in gx}
for a, b in zip(gx, gx[1:]):
    W(gj[a], gj[b], net="0" if a == 63 else None)
W(V2["2"], gj[63]); W(gj[63], G1["1"]); W(V1["2"], gj[126])
W(RL1["2"], gj[189]); W(C13["2"], gj[252]); W(C14["2"], gj[306]); W(R4["2"], gj[405])
W(C11["2"], gj[459]); W(R5["2"], gj[522]); W(R7["2"], gj[657]); W(R8["2"], gj[702])
W(R10["2"], gj[882]); W(R12["2"], gj[990]); W(R15["2"], gj[1044]); W(C18["2"], gj[1098])
W(R16["2"], gj[1152]); W(R17["2"], gj[1251]); W(Q5["E"], gj[1305]); W(C21["2"], gj[1359])
W(C23["2"], gj[1530]); W(RL["2"], gj[1584]); W(C20["2"], gj[1737]); W(R20["2"], gj[1818])
W(R19["2"], gj[1872]); W(V3["2"], gj[1944])

# ================= oscillator, buffer =================
jt1, jt2 = J(252, 279), J(306, 279)
W(L1["1"], jt1, via=[(189, 279)], net="osc_t"); W(jt1, jt2); W(jt2, C12["2"])
W(jt1, C13["1"]); W(jt2, C14["1"]); W(L1["2"], RL1["1"])
jb1, jb2 = J(405, 279), J(459, 279)
W(C12["1"], jb1, net="osc_b"); W(jb1, jb2); W(jb2, Q1["B"])
W(R3["2"], jb1); W(jb1, R4["1"]); W(jb2, C10["1"])
je1, je2 = J(459, 405), J(522, 405)
W(Q1["E"], je2, net="osc_e"); W(C10["2"], je1); W(je1, je2); W(je2, C15["2"])
W(je1, C11["1"]); W(je2, R5["1"])
jq = J(657, 405)
W(C15["1"], jq, net="buf_b"); W(jq, Q2["B"]); W(R6["2"], jq); W(jq, R7["1"])
je3 = J(702, 459)
W(Q2["E"], je3, net="buf_e"); W(je3, R8["1"]); W(je3, C16["2"])

# ================= attenuator, driver =================
W(C16["1"], R9["1"], net="att")
jd = J(882, 459)
W(R9["2"], jd, net="drv_in"); W(jd, R10["1"]); W(jd, C17["2"], via=[(882, 351), (918, 351)])
j3b = J(990, 351)
W(C17["1"], j3b, net="q3_b"); W(R11["2"], j3b); W(j3b, R12["1"]); W(j3b, Q3["B"])
j3c = J(1044, 288)
W(R13["2"], j3c, net="q3_c"); W(j3c, Q3["C"]); W(j3c, Q4["B"])
W(Q3["E"], R14["1"], net="q3_e")
j3e = J(1044, 468)
W(R14["2"], j3e, net="q3_e2"); W(j3e, R15["1"]); W(j3e, C18["1"])
j4e = J(1152, 351)
W(Q4["E"], j4e, via=[(1125, 351)], net="q4_e"); W(j4e, R16["1"]); W(j4e, C19["2"])

# ================= class-C PA, pi network =================
j5b = J(1251, 351)
W(C19["1"], j5b, net="pa_b"); W(j5b, L2["1"]); W(j5b, Q5["B"]); W(L2["2"], R17["1"], net="pa_br")
j5c = J(1305, 288)
W(L3["2"], j5c, net="pa_c"); W(j5c, Q5["C"])
jp = J(1359, 288)
W(j5c, jp); W(jp, C21["1"]); W(jp, C22["2"])
W(C22["1"], L4["1"], net="pi")
jo, jo2 = J(1530, 288), J(1584, 288)
W(L4["2"], jo, net="out"); W(jo, C23["1"]); W(jo, jo2); W(jo2, RL["1"])

# ================= series modulator =================
jvp = J(1737, 360)
jvb = J(1737, 306)
W(L3["1"], jvb, via=[(1305, 162), (1737, 162)], net="vpa")
W(jvb, jvp)
jq6e = J(1818, 360)
W(jvp, C20["1"]); W(jvp, jq6e); W(Q6["E"], jq6e); W(jq6e, R20["1"])
j6b = J(1872, 288)
W(Q6["B"], j6b, net="mod_b"); W(R18["2"], j6b); W(j6b, R19["1"]); W(j6b, C24["2"])
W(C24["1"], V3["1"], via=[(1944, 288)], net="aud")

# ================= scope: A = output, B = Vpa (open minus terminals = ground reference) =================
X = d.scope(at=(1611, 270), pin="1")
W(jo2, X["1"], via=[(1611, 288)])
W(X["2"], jvb, via=[(1647, 306)])

# ================= text =================
d.text("2.63 MHz high-level AM transmitter (collector modulation, ma ~ 45 %, 50 ohm load)", 36, 18, size=12, bold=True)
d.text("+12V", 1400, 63, size=8, bold=False)
d.text("+9V", 560, 90, size=8, bold=False)
for s, x in [("Seiler osc. 2.63 MHz", 200), ("buffer", 640), ("atten.", 800), ("driver", 1010),
             ("class-C PA", 1230), ("pi match", 1380), ("50 ohm load", 1560), ("series modulator (5 kHz)", 1760)]:
    d.text(s, x, 585, size=9, bold=True)

# ================= probes =================
d.probe("PR1", 1557, 288, show=False, node="out")     # AM output across the 50 ohm load
d.probe("PR2", 1530, 162, show=False, node="vpa")     # PA collector supply = modulating voltage
# tmax 10 ns for the 2.63 MHz carrier (the default "calculate" garbles the envelope in Grapher);
# ic="auto": the 10 uF coupling cap would take tens of ms to charge from zero.
d.sim_settings(tstop=1.2e-3, tmax=1e-8, ic="auto")
print(d.save("am_transmitter"))
