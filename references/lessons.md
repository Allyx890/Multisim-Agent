# Lessons (append new ones at the end: symptom → cause → fix)

Most of these cost hours. The tools now guard against each; the list explains *why* the rules exist.

## Approach

- **"Import SPICE netlist" in Multisim** gives correct connectivity but auto-placed parts and tangled wires. Not a
  deliverable. COM `OpenFile("x.cir")` hangs on a hidden dialog — don't.
- Final approach: unpack `.ms14` → clone parts from Multisim's own samples → generate wires → pack. Multisim's
  own netlist, simulation and PNG export (COM) are the ground truth for checking.

## COM interface (`MultisimInterface.MultisimApp`, MSInterface.dll)

- 32-bit in-process server: call it from 32-bit PowerShell (`SysWOW64`) or a C# program compiled `-platform:x86`.
  64-bit Python cannot load it.
- Each `CreateInstance` starts a hidden multisim.exe that survives `Disconnect()`. Kill only the processes *you*
  started (compare PID sets before/after) — never the user's Multisim. Starting the next instance immediately can
  fail intermittently (E_FAIL / access violation) → wait ~1.5 s and retry (sim.py does).
- Windows PowerShell 5 reads BOM-less `.ps1` as ANSI: non-ASCII text breaks parsing. Keep `.ps1` ASCII.
- Useful methods: `OpenFile`, `SaveAs`, `GetCircuitImage(0=PNG, path)`, `ReportNetlist(false, 0, "")`,
  `RunSimulation`, `SetOutputRequest`, `GetOutputData`, `DoDCOperatingPoint`, `RLCValue`. No placement API.
  Print exact signatures with `bin/tlbdump.exe <MSInterface.dll>`.
- The netlist report omits instruments (scope wiring is only visible in the PNG).

## Simulation over COM

- Outputs exist only for **probes** (`V(PRx)`, `I(PRx)`); a net name is "Output not found". The probe must sit on a
  wire (not inside a part body).
- `GetOutputData`'s 2nd **and 3rd** parameters are `[out]`; PowerShell crashes on it. In C#, mark both byref.
- `SetOutputRequest(name, 1, rate, n, true)` then `RunSimulation(T, true)` (async) then loop `OutputReady` →
  `GetOutputData` block by block. Block size must not exceed the total sample count, or it never fills.
- **The COM run ignores the TMAX stored in the file (both interactive and Transient) but honours IC.** So a file
  can pass every simulation comparison and still show garbage in the user's Transient analysis → static check
  (verify layer C) + always write settings (`Doc.sim_settings`).
- Delete old CSVs before a run; a failed run otherwise "returns" the previous data.
- An oscillator started at its exact operating point may never start in ngspice; use `ic="zero"` (both simulators
  then start from zero, the supply step kicks it).
- Coupling caps of µF with kΩ need tens of ms to charge from zero: with `ic="zero"` a 1 ms run never reaches the
  operating point. Use `ic="auto"` for such circuits. verify mirrors the file's IC in ngspice (`uic`).

## "Netlist right, simulation wrong" (the big one)

- Symptom: file opens, netlist report matches, but readings ignore resistor values (1k/3k divider reads 4.5 V,
  identical results for different transistors, oscillator output 0, multi-line `.MODEL` → E_FAIL).
- Cause: Python wrote attribute newlines as `&#10;`; Multisim does not decode it → SPICE templates garbled.
- Fix: literal newlines on write (`wiring.dump`), char-refs only during Python parsing (`msxml.fromstring`).
- Detection: verify layer D (operating point) and E; `tests/test_unit.py::literal_newlines_survive`.

## Netlist comparison

- Matching nets by "same set of pins" ignores net names, so a reversed source (both of its nets swapped) matched
  perfectly. Ground now anchors the match: the `.cir` net `0` must be the Multisim net holding the ground symbol;
  polarised parts (sources, diodes, transistors) compare pin numbers. `tests/test_unit.py` and the negative case
  `neg_reversed_source` guard this.

## Bookkeeping in the base document

- Stale `CIRToInfoMapItem` "PR1 → Output" in the base sample renamed our probe PR1 to `V(Output)`.
- Removing only those mappings made Multisim renumber new parts (R1 → R3 …) because `RefDesPrefixUsage` still
  marked the numbers used. Remove both. verify layer A caught the renumbering immediately.
- Net names written with made-up GUIDs drew those nets in black. Use `uuid4` per net name.

## Waveform comparison

- Peak-to-peak via max−min is fooled by single-sample numerical spikes in ngspice (5.0 % false alarm): use the
  0.5/99.5 % percentiles; median-filter per-cycle envelopes.
- An oscillator's phase is arbitrary: compare frequency/amplitude/envelope, and phase-align only for plotting.

## XML and code hygiene

- Some samples contain `\x00` in attributes — strip before parsing.
- Wire-end objects need `Pen-Style="5"` (invisible), else every pin shows a red dot.
- Don't let ElementTree add its own XML declaration on top of yours.
- Writing Python that writes Python inside a Bash heredoc has injected real NUL bytes and newlines into sources
  five times. Edit source files with an editor tool or a standalone script file.

## Layout

- Moving a part (M20/M21) does not move wires (absolute coordinates) — place parts first, then route by pin coordinates.
- The base sample (ColpittsOscillator) keeps its 2-channel scope XSC2; `Doc()` deletes its parts, text and probe.
- Mirrored templates (e.g. NPN3904m, base on the right) have different pin offsets — always route from `Part.xy()`.
- Sheet size lives in `CircPrefs` (`Sheet Size/Width/Height…`), not `PageWidth/PageHeight`; `Doc(sheet=…)` sets both
  the keys and the border drawing. PNG export size = sheet size (A 960×720, B 1536×960, C 2016×1536).
