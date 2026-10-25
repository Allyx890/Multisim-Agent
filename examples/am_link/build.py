"""Complete conducted AM link: actual RF transmitter -> tuned detector -> audio line output.

Reuses the tested transmitter layout, then adds a receiver on the lower half of the sheet.
This is a 5 kHz single-tone demonstration with a resistive channel, not a radio-range model.
Check: python ../../scripts/msa.py check build.py --cir circuit.cir --tran 2e-3 --dt 1e-8
"""
from pathlib import Path
import runpy

tx = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'am_transmitter' / 'build.py'))
d = tx['d']
A, W, J = d.add, d.wire, d.junction
# Leave room for the inter-row signal wire beneath the transmitter's load.
for item in d.objs:
    label = item.find('CODTextComp')
    if label is not None and label.get('Output') == '&ASC50 ohm load':
        label.set('Transformer-M20', '1476.')

# Channel, tuned RF input and detector.
R21=A('R_h','R21',1e3,at=(207,900),pin='1')
C25=A('C_v','C25',166e-12,at=(360,972),pin='1')
L5=A('L_v','L5',22e-6,at=(432,972),pin='1')
R23=A('R_v','R23',7.3,at=(432,1062),pin='1')
R22=A('R_v','R22',3.3e3,at=(504,972),pin='1')
D1=A('D4148_h','D1',at=(594,900),pin='A')
R24=A('R_v','R24',10e3,at=(738,1026),pin='1')
C26=A('C_v','C26',220e-12,at=(810,1026),pin='1')
R25=A('R_h','R25',1e3,at=(855,900),pin='1')
C27=A('C_v','C27',1e-9,at=(945,1026),pin='1')
Q9=A('NPN3904','Q9',at=(981,900),pin='B')
R32=A('R_v','R32',1e3,at=(1008,1080),pin='1')
C28=A('C_h','C28',10e-9,at=(1035,936),pin='2')

# Degenerated common-emitter audio amplifier and emitter-follower line driver.
V4=A('VDC','V4',12,at=(117,900),pin='1')
R26=A('R_v','R26',47e3,at=(1116,810),pin='1')
R27=A('R_v','R27',10e3,at=(1116,1026),pin='1')
Q7=A('NPN3904','Q7',at=(1170,900),pin='B')
R28=A('R_v','R28',3.3e3,at=(1197,810),pin='1')
R29=A('R_v','R29',2.2e3,at=(1197,1026),pin='1')
Q8=A('NPN2222','Q8',at=(1368,864),pin='B')
R30=A('R_v','R30',1e3,at=(1395,1044),pin='1')
C29=A('C_h','C29',220e-9,at=(1485,954),pin='2')
R31=A('R_v','R31',1e3,at=(1674,1044),pin='1')

# Continue the output wire to the receiver without a second independent RF source.
W(tx['jout_scope'],R21['1'],via=[(1611,666),(207,666)])
rf={x:J(x,900) for x in (360,432,504)}
W(R21['2'],rf[360],net='rx'); W(rf[360],rf[432]); W(rf[432],rf[504]); W(rf[504],D1['A'])
W(rf[360],C25['1']); W(rf[432],L5['1']); W(L5['2'],R23['1'],net='rxl'); W(rf[504],R22['1'])
det1,det2=J(738,900),J(810,900)
W(D1['K'],det1,net='det'); W(det1,det2); W(det1,R24['1']); W(det2,C26['1']); W(det2,R25['1'])
lp=J(945,900)
W(R25['2'],lp,net='lpf'); W(lp,C27['1']); W(lp,Q9['B'])
db=J(1008,936)
W(Q9['E'],db); W(db,R32['1'],net='det_buf'); W(db,C28['2'])
ab=J(1116,900)
W(C28['1'],ab,via=[(1080,900)],net='af_b'); W(ab,Q7['B']); W(R26['2'],ab); W(ab,R27['1'])
ac=J(1197,864)
W(R28['2'],ac,net='af_c'); W(ac,Q7['C']); W(ac,Q8['B']); W(Q7['E'],R29['1'],net='af_e')
buf=J(1395,954)
W(Q8['E'],buf,net='af_buf'); W(buf,R30['1']); W(buf,C29['2'])
W(C29['1'],R31['1'],via=[(1674,954)],net='audio')

# Receiver supply and one shared ground reference for the complete circuit.
sv0,sv1,sv2=J(1008,738),J(1116,738),J(1197,738)
W(V4['1'],sv0,via=[(117,738)],net='vccrx'); W(sv0,sv1); W(sv0,Q9['C']); W(sv1,sv2); W(sv2,Q8['C'],via=[(1395,738)])
W(sv1,R26['1']); W(sv2,R28['1'])
gx=[117,360,432,504,738,810,945,1008,1116,1197,1395]
gg={x:J(x,1188) for x in gx}
W(tx['gj'][63],gg[117],via=[(27,540),(27,1188)])
for a,b in zip(gx,gx[1:]): W(gg[a],gg[b])
W(gg[1395],R31['2'],via=[(1674,1188)])
for p,x in ((V4,117),(C25,360),(R23,432),(R22,504),(R24,738),(C26,810),(C27,945),
            (R32,1008),(R27,1116),(R29,1197),(R30,1395)):
    W(p['2'],gg[x])

d.text('RECEIVER: resistive channel -> LC selection -> diode detector -> audio amplifier -> line output',36,630,size=12,bold=True)
for label,x in [('channel loss',207),('LC tuned input',360),('1N4148 envelope detector',666),('RF rejection',900),
                ('audio voltage gain',1107),('output buffer',1368),('1 kohm line load',1611)]:
    d.text(label,x,1233,size=9,bold=True)
d.text('5 kHz single-tone conducted-link demonstration. No antenna, propagation model or speaker-power claim.',36,1296,size=11,bold=False)
d.probe('PR3',918,900,show=False,node='lpf')
d.probe('PR4',1584,954,show=False,node='audio')
d.probe('PR5',1944,306,show=False,node='aud')
d.sim_settings(tstop=2e-3,tmax=1e-8,ic='auto')
if __name__ == '__main__':
    print(d.save('am_link'))
