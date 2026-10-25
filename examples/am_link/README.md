# Complete AM transmission and reception

This example connects a real transistor oscillator and collector-modulated RF power stage to a receiver.
It contains **71 electrical components**, plus one oscilloscope and ground symbol, on one Multisim sheet.

The upper half is the shared [AM transmitter](../am_transmitter/build.py). Its output drives the lower half
through a resistive channel: a tuned LC input, a 1N4148 envelope detector, an RC filter and detector buffer, an AC-coupled
common-emitter audio amplifier, and an emitter-follower line output loaded by 1 kohm.
The receiver is driven by the generated transmitter signal, not a separate ideal AM source.

## Reproduce

From this directory, with the runtime initialized by `msa doctor` and `msa setup`:

```bash
python ../../scripts/msa.py check build.py --cir circuit.cir --tran 2e-3 --dt 1e-8
python validate_recovery.py
python plot_results.py
```

`check` generates the native schematic, a Multisim-exported image, five probe CSV files and the full
verification report in the configured `MULTISIM_AGENT_CACHE/out` directory. `plot_results.py` reads those
CSVs, runs the same reference netlist in ngspice, and creates the README plot plus measurement metadata.

| Probe | Signal | What it checks |
|---|---|---|
| PR1 | `out` | RF frequency, modulation envelope, load voltage |
| PR2 | `vpa` | Collector modulation supply |
| PR3 | `lpf` | Detected envelope after RF filtering |
| PR4 | `audio` | Recovered signal across the 1 kohm line load |
| PR5 | `aud` | Original 5 kHz modulation input |

The two unjoined orthogonal crossings are intentional: the inter-row signal crosses the transmitter ground
rail and the receiver supply rail. Geometry lint reports them as warnings; Multisim's exported netlist must
still match the reference at layer A. Junction dots mark actual connections.

## Scope

This is a **5 kHz single-tone, conducted-link simulation** with a resistive channel. It demonstrates the
complete modulation and demodulation path. It does not establish wireless range, a voice-band specification,
speaker power, or hardware performance. The output stage is a 1 kohm line driver.

The plotted simulator traces keep their original time and voltage scales. No phase fitting or amplitude
normalization is used. Agreement is checked with the same tolerances as the other examples.

## Functional acceptance

Simulator agreement is necessary but not sufficient. `validate_recovery.py` also checks the actual recovered
audio: at least 1 Vpp across 1 kohm, THD from harmonics 2-5 no more than 3%, and normalized residual to a
5 kHz sine no more than 5%, over 1.2-2.0 ms. These are demonstration acceptance limits, not hardware ratings.
The test suite rejects clipped and wrong-frequency synthetic controls, then applies the gate to the actual
Multisim trace. The README plot generator applies the same gate independently to both simulator traces.
