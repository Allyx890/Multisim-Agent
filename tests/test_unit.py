"""Unit tests that need no Multisim and no ngspice (only `msa.py setup` having unpacked the samples).
Each test pins down a bug that actually happened. Run: python tests/test_unit.py"""
import glob
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import ms14
import msenv
import msxml
import netcheck
import simset
import wiring

results = []


def test(fn):
    try:
        fn()
        results.append((fn.__name__, None))
        print(f"ok   {fn.__name__}")
    except Exception as e:   # noqa
        results.append((fn.__name__, e))
        print(f"FAIL {fn.__name__}: {e!r}")
    return fn


def samples(n=None):
    src = sorted(glob.glob(os.path.join(msenv.SAMPLES_SRC or "", "**", "*.ms14"), recursive=True))
    return src[:n] if n else src


@test
def ms14_roundtrip():
    if os.environ.get("QUICK"):
        return
    """our DCL implode/explode reproduces Multisim's payload byte-for-byte (12 samples incl. multi-block)."""
    files = samples()
    big = [f for f in files if os.path.getsize(f) > 600_000][:2]
    for f in files[:10] + big:
        raw = open(f, "rb").read()
        xml = ms14.decompress_ms14(raw)
        again = ms14.decompress_ms14(ms14.compress_ms14(xml))
        assert again == xml, f"roundtrip differs for {f}"


@test
def literal_newlines_survive():
    """attribute newlines must stay literal after parse+dump: Multisim does NOT decode &#10; in attributes.
    (Bug: resistor SPICE templates became one garbled line -> every resistor ~0 ohm in simulation.)"""
    root = msxml.parse(msenv.BASE)
    raw = open(msenv.BASE, "rb").read()
    n_nl = sum(b"\n" in v for v in msxml._ATTR.findall(raw))
    fd, tmp = tempfile.mkstemp(suffix=".xml"); os.close(fd)
    try:
        wiring.dump(root, tmp)
        out = open(tmp, "rb").read()
        assert b"&#10;" not in out and b"&#13;" not in out, "character references leaked into attributes"
        assert sum(b"\n" in v for v in msxml._ATTR.findall(out)) == n_nl, "multi-line attributes lost their newlines"
        a = [(e.tag, sorted(e.attrib.items())) for e in root.iter()]
        b = [(e.tag, sorted(e.attrib.items())) for e in msxml.parse(tmp).iter()]
        assert a == b, "attributes changed in a parse/dump roundtrip"
    finally:
        os.remove(tmp)


@test
def nul_bytes_tolerated():
    """some samples carry NUL bytes inside attributes; parse must not choke."""
    bad = 0
    for f in samples():
        try:
            msxml.parse(f)
        except Exception:
            bad += 1
    assert bad == 0, f"{bad} sample(s) failed to parse"


@test
def simset_edit_roundtrip():
    text = simset.load_text(msenv.BASE)
    new, n = simset.edit(text, tmax=1e-8, tstop=2e-3, ic="zero")
    assert n > 5
    tree, _ = simset.parse(new[slice(*simset.find_info(new))])
    blocks = {"/".join(p): d for p, d in simset.tran_blocks(tree)}
    tr = blocks["SIMULATION_INFO/ANALYSES/TRAN/ANALYSIS"]
    assert tr["TMAX"] [:2] == ("double", "1e-08") and tr["TSTOP"][1] == "0.002" and tr["IC"][1] == "zero_ic", tr
    inter = blocks["DEFAULT_INST_SETTINGS/TRAN/ANALYSIS"]
    assert float(inter["TSTOP"][1]) >= 1e29, "interactive TSTOP must stay 1e30"


NET = """Netlist Report
Net   Sheet   Component   Pin
a     s       V1          {p1}
a     s       R1          1
0     s       V1          {p2}
0     s       R1          2
0     s       Ground      1
"""


@test
def netcheck_catches_reversed_source():
    """a source wired upside down must FAIL (the old checker ignored pin numbers for every 2-pin part)."""
    fd, cir = tempfile.mkstemp(suffix=".cir"); os.close(fd)
    open(cir, "w").write("t\nV1 a 0 DC 5\nR1 a 0 1k\n.end\n")
    try:
        ok, _ = netcheck.check(NET.format(p1="1", p2="2"), cir)
        bad, _ = netcheck.check(NET.format(p1="2", p2="1"), cir)
        assert ok == 0, "correct polarity reported as mismatch"
        assert bad > 0, "reversed polarity not detected"
    finally:
        os.remove(cir)


@test
def parse_cir_values():
    fd, cir = tempfile.mkstemp(suffix=".cir"); os.close(fd)
    open(cir, "w").write("title\n.param amp=2 f=5k\nV1 a 0 SIN(0 {amp} {f})\nV2 b 0 DC 12\nR1 a b 4.7k\n"
                         "C1 b 0\n+ 2.2u\nL1 b c 1Meg\n.subckt X1 p q\nR9 p q 1\n.ends\n.end\n")
    try:
        v = {n: val for n, k, nodes, val, line in netcheck.parse_cir(cir)}
        assert v["V1"] == ("sin", 2.0, 5000.0), v["V1"]
        assert v["V2"] == 12 and abs(v["R1"] - 4700) < 1e-9 and abs(v["C1"] - 2.2e-6) < 1e-15 and v["L1"] == 1e6, v
        assert "R9" not in v, "subcircuit internals must be skipped"
    finally:
        os.remove(cir)


n = sum(e is not None for _, e in results)
print("test_unit:", "PASS" if n == 0 else f"{n} FAILED")
sys.exit(n)
