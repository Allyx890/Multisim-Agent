# The .ms14 format (Multisim 14.x, reverse-engineered)

Read this only if you change `msgen`/`wiring`/`simset` internals. Building circuits needs only SKILL.md.

## Container

```
"MSMCompressedElectronicsWorkbenchXML"   36-byte signature (project .ewprj: "CompressedElectronicsWorkbenchXML", 33 bytes)
u32 total uncompressed length, u32 0
repeat: u32 block length, u32 compressed length, PKWARE DCL "implode" data (≤ 900 000 bytes per block, blocks independent)
```

- DCL header `01 06`: ASCII mode (Huffman-coded literals), 4 KB dictionary.
- Decompression follows Mark Adler's `zlib/contrib/blast/blast.c`; compression is a greedy LZ77 written for this
  project. Multisim reads our output (verified on every sample). Container layout first documented by barncastle's
  converter gist `4277ac44aa47bf8c4389c7df0d160e56` (which needs the commercial IMPLODE.DLL; we don't).
- Payload: `<?xml version="1.0" encoding="ASCII"?>` + `<MSMElectronicsWorkbench Schema="67">`.
  Multisim also opens the uncompressed XML directly.
- Some samples carry `\x00` inside attribute values; strip before parsing (`msxml.parse` does).

## Strings

- `&ASCtext` — plain ASCII. `&UNItext` — non-ASCII characters written `_uc1XXXX` (4 hex digits):
  `10k_uc103a9` = `10kΩ`, `_uc100b5` = `µ`. Any language works for titles (`msgen.enc`).
- **Newlines inside attribute values must be literal newlines.** SPICE templates, multi-line `.MODEL` text and the
  simulation settings rely on them. Multisim does *not* decode numeric character references (`&#10;`): the file
  still opens and the netlist report is still right, but every resistor's template collapses into one garbled
  line and simulates as ~0 Ω. Only `&amp; &lt; &gt; &quot;` are safe. Python's XML parser, conversely,
  normalises literal newlines in attributes to spaces — so `msxml.fromstring` turns them into character
  references before parsing and `wiring.dump` turns them back into literal newlines when writing.

## Two layers (both under `CIITDiagram`)

### Drawing layer `Components/CODComposite`

- `Objects` — top-level visible objects:
  - `CIITSymbolComp` — a part symbol. `CiComponent` → its electrical record; `InstanceRefDes` = refdes. Children:
    `CIITSymTextCompName/Value` (labels), graphics, `CIITSymbolBorderRect` (body box), `CIITPinSymbolComp`
    (pins; `PortID` → CiPort) each holding a `CIITPinConnectorComp` (`ptCenterX/Y`, `ConnectList` of wire ends).
  - `CIITLinkComp` — a wire. `Points` = absolute polyline; `Connect1/Connect2` = ids of its two end objects;
    `Node`/`NodeText` may be 0; `ElectricalObject/ModifierInfo/Element NetModifier="&ASCNI_EWB_NET_NAME"` names
    the net (use a real random GUID per net name — made-up GUIDs make Multisim draw that net in black).
  - `CODPinComp` (in Objects) — a junction dot. Absolute position = `CenterX/Y` + its own M20/M21.
    `Mobility="0"`; `ConnectList` = the wire ends attached to it.
  - `CIITProbeExtComponent` — a probe. No wires: the net is whatever wire passes through its position.
  - `CODTextComp` — free text.
- `ReferencedComponents` — the wire-end `CODPinComp`s (written in full, `Mobility="1"`, **`Pen-Style="5"`**
  i.e. invisible pen, otherwise every pin gets a dot; `ConnectList` → a pin connector or a junction) plus empty
  `<Item ID= Class=/>` back-references to wires, junctions and pin connectors.

### Electrical layer `Elements`

- `CiComponent` — `LocalName` (refdes), `SymCompID`, `Model`, `Circuit`. `Attributes` hold the SPICE template
  (`CiaSpiceTmpltExprt`), `CiaParamList` (doubles/parameters; R/C/L/VDC main value at index 1, VAC peak at 1 and
  frequency at 5), `CiaCString`s (value and display strings) and `CiaCollString`s (first list's first 4 items =
  family, e.g. `RESISTOR|RESISTOR_VIRTUAL|RESISTOR|VIRTUAL_RESISTANCE`).
- `CiPort` — `Component` → its part; `Nodes` may be empty.
- `CiModel` — `Scope` = circuit id; holds the `.MODEL` text.
- `CiNode` — nets. **May all be deleted**: Multisim rebuilds connectivity from the wires on load (verified with
  the netlist report and the DC operating point). msgen writes none.
- `CiCircuit` — master lists `Models`, `Nodes`, `Components`, `ProbeExts` (`Item CiID=`).

### Bookkeeping Multisim rebuilds itself

`ViewState`, `NetLabels`, `CCompInstancePropManager` may be dropped. In `RefDesMgrs`, entries for deleted parts must
go **together**: `CIRToInfoMapItem` (else a new part reusing a name inherits the old display name, e.g. probe PR1
shows up as `V(Output)`) and `RefDesPrefixUsage` (else Multisim thinks R1/Q1 are taken and renumbers new parts on
load — the netlist then no longer matches).

## Simulation settings (`SIMULATION_INFO` attribute)

A custom nested text format `key:type{value}` (`type` ∈ list/string/double/long). `simset.py` parses/edits it.
Relevant blocks (any list holding both `TSTOP` and `TMAX`):
- `DEFAULT_INST_SETTINGS/TRAN/ANALYSIS` — the interactive simulation (F5): `TSTOP` = 1e30.
- `SIMULATION_INFO/ANALYSES/TRAN/ANALYSIS` — Simulate ▸ Analyses ▸ Transient.
- `…/FOUR|PSWEEP|TSWEEP|WORST|MONTE|TRACEWIDTH/…/Tran` — transient settings embedded in other analyses.
`TMAX:string{calculate}` ≈ TSTOP/50. `IC:string{auto_ic|zero_ic}`. The COM simulation ignores TMAX but honours IC.

## ID references (renew consistently when cloning)

`Item@ID/CiID`, `CiComponent@SymCompID/Model/Circuit`, `CIITSymbolComp@CiComponent`, `CIITPinSymbolComp@PortID`,
`CiPort@Component`, `CiModel@Scope`, `CIITLinkComp@Connect1/Connect2`, `CiProbeExtComp@SymCompID`,
`CIITProbeExtComponent@CiProbeExtComp`. Colour attributes are long integers too — not ids. In some samples a
symbol's id and the component's `SymCompID` disagree: find the symbol via its `CiComponent` attribute.

## Coordinates

Each object has `Transformer-M00 M01 M10 M11 M20 M21`, row-vector convention:
`x' = x·M00 + y·M10 + M20`, `y' = x·M01 + y·M11 + M21`. Pin position = symbol ∘ pin-symbol ∘ connector transform
applied to (ptCenterX, ptCenterY) — checked against all wire ends of a sample. Moving a part = changing the
symbol's own M20/M21. Multisim bakes rotation into the children, leaving the symbol matrix identity — so keep one
template per orientation instead of rotating.
