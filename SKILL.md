---
name: multisim-agent
description: Generate correct, tidy NI Multisim 14 schematics (.ms14) from code and prove they are right — parts placed on a grid, orthogonal wires, probes and simulation settings included, then verified automatically (Multisim's own netlist + simulation compared against an ngspice reference). Use whenever the user wants a circuit "in Multisim", a .ms14 file, a Multisim schematic/simulation for coursework or a lab, or needs to read, fix or re-check an existing .ms14 (e.g. "the waveform in Multisim looks wrong"). 中文触发：画 Multisim 电路图、生成 .ms14、Multisim 仿真、仿真波形不对。Windows + Multisim 14.x required.
---

# multisim-agent

Turns a SPICE netlist you trust into a Multisim schematic a human would be happy to hand in, and **proves** it:
Multisim opens the file, its own netlist equals your netlist, every part value matches, the stored simulation
settings are sane, and Multisim's simulation agrees with ngspice. Nothing is delivered on "looks right".

All commands: `python <skill>/scripts/msa.py <command>` (below just `msa`). Every command has `--help`.

## Golden path (do exactly this)

```
msa doctor                      # once per machine; fix anything MISSING (it prints the fix)
msa setup                       # once per machine (unpacks Multisim samples, compiles helpers; idempotent)
msa new NAME --dir WORKDIR      # scaffold NAME.cir (reference netlist) + NAME.py (layout script); runs as-is
```
1. **Write `NAME.cir` first** and simulate it in ngspice until the *circuit* is right. This is the answer key.
   - Element names = the Multisim reference designators you will use (`R1`, `C3`, `Q1`, `V2`).
   - Transistors: `msa models NPN3904` prints the exact `.MODEL` Multisim uses — put it in a `models.lib`
     and reference that model name, so ngspice and Multisim simulate the same device.
2. **Plan the layout on paper**: rails, columns, which pin goes where. `msa parts` lists every template with
   pin offsets and body boxes (grid = 9 units, y grows downward).
3. **Write `NAME.py`** with `msgen` (API below). Copy the style of `templates/build_template.py` or
   `examples/*/build.py`.
4. **Check — the only acceptance test:**
   ```
   msa check NAME.py --cir NAME.cir --tran <seconds> [--dt <max step>] [--deliver OUTDIR]
   ```
   build → lint (geometry) → Multisim opens it → verify layers A–E. Exit code 0 + "ALL CHECKS PASSED" is
   required. On FAIL, use the table below, fix, re-run. Then look at `NAME.png` once (labels, aesthetics).
5. Deliver the `.ms14` (and the `.png`/compare plot if useful). `--deliver DIR` copies them for you.

Choose `--tran` long enough to reach steady state plus a few periods of the slowest signal (verify compares the
last 50 %); `--dt` ≤ period/40 of the fastest signal (1e-8 for MHz, 1e-6 for kHz).

## Hard rules (each one cost a real failure)

- Every coordinate is a multiple of 9. Always pass `pin=` to `d.add`: that pin lands exactly on `at`.
- A wire may only end on a **pin** or a **junction**. Where 3+ wires meet, create `d.junction(x, y)` and wire each
  branch to it. A wire end resting on the middle of another wire is *not connected* in Multisim (lint FAILs it).
- Wires are horizontal/vertical polylines (`via=[corners]`); never through a part body; never on top of another wire.
- Put a probe on every node you care about: `d.probe("PRn", x, y, node="<.cir node>")`, (x, y) on a wire segment.
  Probes are the only way to read Multisim's simulation, and `node=` is how verify pairs them with ngspice.
- **Always** `d.sim_settings(tstop=..., tmax=..., ic=...)`. Multisim's default TMAX "calculate" ≈ TSTOP/50 makes any
  fast waveform (RF carrier, AM envelope) look garbled in the user's Transient/Grapher run, and the COM
  simulation used by verify does not read TMAX — only layer C catches it. Use `ic="auto"` (operating point first)
  unless you need a start-up transient; oscillators need `ic="zero"` to get a kick.
- Supply rail on top, ground rail at the bottom, signal left → right, one ground symbol. Big circuit → `Doc(sheet="B"|"C")`.
- Never hand-edit the XML with Python string escapes inside a shell heredoc; write code to files (escapes have broken
  the sources several times).
- Close nothing you did not start: the tools only kill Multisim processes they launched themselves.

## When a check fails

| failing item | meaning | fix |
|---|---|---|
| lint `t-no-junction` | a wire end / pin touches the middle of another wire | split that wire at a `d.junction()` and wire both halves + the branch to it, or move it |
| lint `through-body` / `overlap` / `body-overlap` | wire crosses a part, two wires coincide, parts overlap | re-route with other `via` corners / move parts (check `msa parts` body boxes) |
| lint `probe-off-wire` | probe not on a wire segment | put (x, y) on a segment between two corners |
| A `netlist vs .cir` | connectivity differs; the report shows the closest Multisim net | wrong pin, missing wire, reversed source (`0 (ground) … NOT the ground net`) |
| B `value` | value in the schematic ≠ .cir | fix the number in `d.add(...)` (SI units; VAC = `(peak, freq)`) |
| C `TMAX` | stored max step too coarse for the signal | `d.sim_settings(tmax=...)`, or `msa simset FILE.ms14 --tmax ...` for an existing file |
| D `operating point` | DC bias differs | wrong model name / part value / pin order (B-E-C!) in the .cir or schematic |
| D/E `no value` / `missing waveform` | probe not readable | probe on a wire? `node=` spelled like the .cir node? |
| E frequency / p-p / envelope | dynamics differ | models differ (use `msa models`), `ic` mismatch, `--tran` too short for steady state |
| `Multisim opens the file` FAIL / COM errors | Multisim could not load | run `msa doctor`; re-run once (COM is occasionally flaky; tools retry) |

## msgen API (in `scripts/msgen.py`)

```python
import sys; sys.path.insert(0, r"<skill>/scripts"); import msgen
d = msgen.Doc(sheet="A")                         # A ≈ 930×690 usable, B ≈ 1500×930, C ≈ 1990×1500
R1 = d.add("R_v", "R1", 4.7e3, at=(405, 189), pin="1")    # template key, refdes, value, placement
Q1 = d.add("NPN3904", "Q1", at=(495, 279), pin="B")
V2 = d.add("VAC", "V2", (0.01, 1e3), at=(153, 297), pin="1")   # sine: (peak V, Hz)
G  = d.add("GND", "0", at=(81, 504), pin="1")    # ground symbols are always named "0"
j  = d.junction(405, 279)                        # red dot; only where ≥3 wires meet
d.wire(R1["2"], j)                               # straight
d.wire(j, Q1["B"], via=[(450, 279)], net="b")    # with corners; net= optional label
R1.xy("2"); R1.body()                            # pin coordinates, body box (for planning)
X = d.scope(at=(621, 315), pin="1")              # 2-ch scope: 1=A+ 4=A- 2=B+ 5=B- (pins on its bottom edge)
d.probe("PR1", 396, 207, show=False, node="c")
d.text("Title (any language)", 36, 27, size=12, bold=True)
d.sim_settings(tstop=10e-3, tmax=5e-6, ic="auto")
print(d.save("NAME"))                            # path → NAME.xml (+ NAME.meta.json); `check` needs this print
```
Templates now: `R_h R_v C_h C_v L_h L_v NPN3904 NPN3904m NPN2222 VDC VAC PULSE GND` — run `msa parts` for
geometry. To add one (diode, op-amp, ...): `python scripts/tplfind.py 1N4148`, pick an un-rotated ("ident")
instance with the orientation you need, add it to `msgen.TPL`, then add a tiny test circuit and run `msa check`.
Read `references/format.md` before touching anything below msgen.

## Tools

| command | what |
|---|---|
| `msa check` | build → lint → Multisim → verify; the acceptance gate |
| `msa lint FILE.xml` | geometry only, < 1 s, no Multisim |
| `msa verify FILE --cir C [--tran T]` | layers A–E only (`--help` for tolerances) |
| `msa render FILE` | Multisim opens it, exports `FILE.png` + netlist `FILE.net` |
| `msa sim FILE.ms14 T` / `--op` | Multisim's simulator on the probes → CSV / DC values |
| `msa simset FILE [--tmax --tstop --ic]` | show / fix the simulation settings stored in a file |
| `msa unpack/pack` | `.ms14` ⇄ XML |
| `msa selftest [--quick]` | unit + lint tests; full run also builds and verifies 4 circuits and 3 broken ones |

## Limits

Windows only (Multisim's COM interface is 32-bit Windows). Instruments other than the 2-channel scope are not
templated yet. Multisim's GUI "Interactive" run is not automatable; its settings are checked statically (layer C).
Hierarchical blocks/subcircuits are not generated. Details and history: `references/lessons.md`.
