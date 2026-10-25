"""multisim-agent environment: locate Multisim, its samples, ngspice, and the cache directory.

Everything is auto-detected; override with environment variables if needed:
  MULTISIM_AGENT_CACHE  cache dir (default ~/.cache/multisim-agent)
  MULTISIM_DIR          Multisim install dir (the folder containing MSInterface.dll)
  MULTISIM_SAMPLES      Multisim samples dir (contains *.ms14)
  NGSPICE               ngspice console executable (ngspice_con.exe on Windows)
Run `python scripts/msa.py doctor` to see what was found.
"""
import glob
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _first(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def _multisim_dir():
    if os.environ.get("MULTISIM_DIR"):
        return os.environ["MULTISIM_DIR"]
    cands = []
    for pf in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files")):
        cands += sorted(glob.glob(os.path.join(pf, "National Instruments", "Circuit Design Suite *")), reverse=True)
    return _first([c for c in cands if os.path.exists(os.path.join(c, "MSInterface.dll"))]) or (cands[0] if cands else None)


def _samples_dir():
    if os.environ.get("MULTISIM_SAMPLES"):
        return os.environ["MULTISIM_SAMPLES"]
    pub = os.environ.get("PUBLIC", r"C:\Users\Public")
    cands = sorted(glob.glob(os.path.join(pub, "Documents", "National Instruments", "Circuit Design Suite *", "samples")), reverse=True)
    return _first(cands)


def _ngspice():
    if os.environ.get("NGSPICE"):
        return os.environ["NGSPICE"]
    w = shutil.which("ngspice_con") or shutil.which("ngspice")
    home = os.path.expanduser("~")
    cands = [w,
             r"C:\Program Files\Spice64\bin\ngspice_con.exe",
             r"C:\Spice64\bin\ngspice_con.exe",
             *sorted(glob.glob(os.path.join(home, "tools", "ngspice*", "Spice64", "bin", "ngspice_con.exe")), reverse=True),
             *sorted(glob.glob(os.path.join(home, "*", "ngspice*", "Spice64", "bin", "ngspice_con.exe")), reverse=True),
             *sorted(glob.glob(r"C:\*\Spice64\bin\ngspice_con.exe"), reverse=True)]
    return _first(cands)


CACHE = os.environ.get("MULTISIM_AGENT_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "multisim-agent"))
MULTISIM_DIR = _multisim_dir()
SAMPLES_SRC = _samples_dir()
MSINTERFACE = os.path.join(MULTISIM_DIR, "MSInterface.dll") if MULTISIM_DIR else None
NGSPICE = _ngspice()

SAMPLES = os.path.join(CACHE, "samples")          # decompressed sample XML (templates come from here)
INDEX = os.path.join(CACHE, "index.json")          # part index built by setup
BIN = os.path.join(CACHE, "bin")                   # compiled 32-bit COM helpers (msim/msop/tlbdump)
OUT = os.path.join(CACHE, "out")                   # default output dir for Doc.save("name")
BASE = os.path.join(SAMPLES, "Analog_ColpittsOscillator.xml")   # base document for new schematics
WINDIR = os.environ.get("SystemRoot", r"C:\Windows")
PS32 = os.path.join(WINDIR, "SysWOW64", "WindowsPowerShell", "v1.0", "powershell.exe")   # MSInterface.dll is 32-bit
CSC = _first(sorted(glob.glob(os.path.join(WINDIR, "Microsoft.NET", "Framework", "v4.*", "csc.exe")), reverse=True))

for _d in (CACHE, SAMPLES, BIN, OUT):
    os.makedirs(_d, exist_ok=True)
