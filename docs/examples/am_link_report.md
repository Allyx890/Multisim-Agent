# Verification report

| layer | check | result | detail |
|---|---|---|---|
| A | Multisim opens the file | PASS | am_link.ms14 |
| A | netlist vs .cir | PASS | 0 mismatch(es) |
| B | part values (61 checked) | PASS | 0 mismatch(es) |
| D | PR1(out) operating point | PASS | Multisim 8.172e-15 V / ngspice 6.024e-15 V |
| D | PR2(vpa) operating point | PASS | Multisim 4.631 V / ngspice 4.631 V |
| D | PR3(lpf) operating point | PASS | Multisim 1.789e-07 V / ngspice 1.319e-07 V |
| D | PR4(audio) operating point | PASS | Multisim 0 V / ngspice 0 V |
| D | PR5(aud) operating point | PASS | Multisim 0 V / ngspice 0 V |
| E | initial conditions | PASS | file IC=auto_ic -> ngspice operating point first |
| E | PR1(out) DC level | PASS | Multisim -0.0008222 V / ngspice -0.0001977 V |
| E | PR1(out) peak-to-peak | PASS | Multisim 11.1 V / ngspice 11.27 V |
| E | PR1(out) frequency | PASS | Multisim 2.6306 MHz / ngspice 2.6262 MHz (diff 0.17%) |
| E | PR1(out) modulation index | PASS | Multisim 43.2% / ngspice 43.8% |
| E | PR1(out) envelope trough Vpp | PASS | Multisim 4.464 V / ngspice 4.484 V |
| E | PR1(out) envelope shape correlation | PASS | r = 1.000 (need >= 0.95) |
| E | PR2(vpa) DC level | PASS | Multisim 4.486 V / ngspice 4.479 V |
| E | PR2(vpa) peak-to-peak | PASS | Multisim 3.988 V / ngspice 3.989 V |
| E | PR2(vpa) frequency | PASS | Multisim 4.9962 kHz / ngspice 4.9964 kHz (diff 0.00%) |
| E | PR3(lpf) DC level | PASS | Multisim 1.803 V / ngspice 1.837 V |
| E | PR3(lpf) peak-to-peak | PASS | Multisim 1.844 V / ngspice 1.882 V |
| E | PR3(lpf) frequency | PASS | Multisim 4.9965 kHz / ngspice 4.9974 kHz (diff 0.02%) |
| E | PR4(audio) DC level | PASS | Multisim 0.002573 V / ngspice 0.002673 V |
| E | PR4(audio) peak-to-peak | PASS | Multisim 2.234 V / ngspice 2.279 V |
| E | PR4(audio) frequency | PASS | Multisim 4.9988 kHz / ngspice 5.0017 kHz (diff 0.06%) |
| E | PR5(aud) DC level | PASS | Multisim 5.27e-09 V / ngspice -7.589e-10 V |
| E | PR5(aud) peak-to-peak | PASS | Multisim 4 V / ngspice 3.999 V |
| E | PR5(aud) frequency | PASS | Multisim 5 kHz / ngspice 5 kHz (diff 0.00%) |
| C | interactive sim (F5) TMAX | PASS | TMAX=1e-08; 2.6262 MHz signal needs <= 1.9e-08 s |
| C | transient analysis TMAX | PASS | TMAX=1e-08; 2.6262 MHz signal needs <= 1.9e-08 s |

![Signal path comparison](../images/am_link_results.png)