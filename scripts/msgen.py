"""从零生成 Multisim 14 原理图（.ms14）。

用法见 build_ch5.py。坐标单位与 Multisim 一致（栅格 9），y 向下。
- 元件：从 Multisim 自带样例里整块克隆（图形符号 + CiComponent + CiPort + CiModel），换新 ID。
- 导线：wiring.Wiring 生成；电气节点交给 Multisim 打开时按导线重算。
"""
import copy
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import msenv
import msxml
import wiring

S = msenv.SAMPLES
BASE = msenv.BASE

# 模板：键 -> (样例文件, 位号)
TPL = {
    "R_h": ("LowPassFilter.xml", "R11"),
    "R_v": ("PowerSupply.xml", "R4"),
    "C_h": ("LowPassFilter.xml", "C9"),
    "C_v": ("Analog_AmplitudeModulator.xml", "C1"),
    "L_h": ("Analog_ColpittsOscillator.xml", "L1"),
    "L_v": ("Analyses_Noise_Figure_-_RF_Amplifier.xml", "L1"),
    "NPN3904": ("Analog_ClassBPushPullAmp.xml", "Q1"),
    "NPN2222": ("Analog_ColpittsOscillator.xml", "Q1"),
    "NPN3904m": ("LabVIEW_Instruments_Signal_Analyzer_GilbertCellMixer.xml", "Q9"),   # 镜像：B 在右
    "GND": ("LowPassFilter.xml", "0"),
    "VDC": ("LowPassFilter.xml", "V2"),
    "PULSE": ("Analog_SpeechFilter.xml", "V5"),
    "VAC": ("LowPassFilter.xml", "V1"),          # 正弦电压源，值写 (峰值V, 频率Hz)
    "D4148_h": ("Analog_PhaseControlledRectifier.xml", "D1"),  # A on left, K on right
}
# 图纸：尺寸由 CircPrefs 里的 "Sheet Size/Width/Height…" 几个键决定（Multisim 按它重画图框），
# 图框线条本身存在 Background 里，两处都从同尺寸样例复制。PageWidth/Height 只是打印设置。
# 可用坐标范围：A 960x720、B 1536x960、C 2016x1536
SHEETS = {"A": None, "B": "Analog_FullWaveVoltageConverter.xml",
          "C": "LabVIEW-Multisim_Co-simulation_Inverter_Thermal_Analysis_ThreePhaseInverter_cosim.xml"}
REF_ATTRS = ("ID", "CiID", "SymCompID", "CiComponent", "PortID", "Component", "Model", "CiProbeExtComp")

_cache = {}


def _src(fname):
    if fname not in _cache:
        _cache[fname] = msxml.parse(os.path.join(S, fname))
    return _cache[fname]


def enc(text):
    """Multisim 字符串编码：ASCII 用 &ASC，其它用 &UNI + _uc1XXXX。"""
    if all(ord(c) < 128 for c in text):
        return "&ASC" + text
    return "&UNI" + "".join(c if ord(c) < 128 else "_uc1%04x" % ord(c) for c in text)


def eng(v):
    """数值 → 工程记数字符串（10k、180p、22u、7.3）。"""
    for s, m in (("G", 1e9), ("M", 1e6), ("k", 1e3), ("", 1), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15)):
        if abs(v) >= m * 0.9999:
            x = v / m
            return (f"{x:.4g}" + s)
    return f"{v:g}"


def dstr(v):
    s = repr(float(v))
    return s if "e" in s else s.rstrip("0") if "." in s else s + "."


class Part:
    def __init__(self, ref, sym, comp, pins):
        self.ref, self.sym, self.comp, self.pins = ref, sym, comp, pins

    def __getitem__(self, pin):
        """("p", 连接器ID), (x, y)"""
        if pin not in self.pins:
            raise KeyError(f"{self.ref} has no pin {pin!r}; pins are {sorted(self.pins)}")
        cid, x, y = self.pins[pin]
        return ("p", cid), (x, y)

    def xy(self, pin):
        """Absolute coordinates of a pin (handy for routing: x, y = R1.xy("2"))."""
        return self[pin][1]

    def body(self):
        """Component body box (x0, y0, x1, y1) — keep wires and other parts out of it."""
        ts = msxml.T(self.sym)
        for it in self.sym.find("Objects"):
            if it.get("Class") == "CIITSymbolBorderRect":
                b = it.find("CIITSymbolBorderRect")
                tb = msxml.T(b)
                pts = [msxml.apply(ts, *msxml.apply(tb, float(b.get(k + "X")), float(b.get(k + "Y")))) for k in ("pt0", "pt1")]
                return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        return None


class Doc:
    def __init__(self, title=None, sheet="A"):
        self.root = msxml.parse(BASE)
        self.w = wiring.Wiring(self.root, start_id=710000000)
        self.diag, self.objs, self.refs = self.w.diag, self.w.objs, self.w.refs
        self.els = self.diag.find("Elements")
        circ = next(i for i in self.els if i.get("Class") == "CiCircuit")
        self.circ_id = circ.get("CiID")
        self.circ = circ.find("CiCircuit")
        self.w.clear()
        self._strip(keep={"XSC2"})
        if SHEETS[sheet]:
            self._sheet(SHEETS[sheet], sheet)
        self.parts = {}
        self._title(title)

    # ---------- 图纸 ----------
    def _sheet(self, fname, size):
        src = next(_src(fname).iter("CIITDiagram"))
        old = self.diag.find("Background")
        self.diag.insert(list(self.diag).index(old), copy.deepcopy(src.find("Background")))
        self.diag.remove(old)
        keys = ("Sheet Size", "Sheet Width", "Sheet Height", "Sheet Width In Inch", "Sheet Height In Inch")
        want = {}
        for e in src.find("CircPrefs").iter("Element"):
            k = e.get("Key", "").replace("&ASC", "")
            if k in keys:
                want[k] = e.find("Item").get("Value")
        for e in self.diag.find("CircPrefs").iter("Element"):
            k = e.get("Key", "").replace("&ASC", "")
            if k in want:
                e.find("Item").set("Value", want[k])
        self.diag.set("TBSize", enc(size))

    # ---------- 清空底稿 ----------
    def _strip(self, keep):
        comps = {i.get("CiID"): i for i in self.els if i.get("Class") == "CiComponent"}
        kill_ci = set()
        for cid, it in comps.items():
            name = it.find("CiComponent").get("LocalName", "").replace("&ASC", "")
            if name in keep:
                continue
            c = it.find("CiComponent")
            kill_ci.add(cid)
            for p in c.find("Ports"):
                kill_ci.add(p.get("CiID"))
            if c.get("Model"):
                kill_ci.add(c.get("Model"))
        for it in list(self.els):
            if it.get("CiID") in kill_ci or it.get("Class") == "CiProbeExtComp":
                self.els.remove(it)
        for lst in ("Components", "Models", "ProbeExts"):
            box = self.circ.find(lst)
            for k in list(box):
                if k.get("CiID") in kill_ci or lst == "ProbeExts":
                    box.remove(k)
        kill_sym = set()
        for it in list(self.objs):
            cl = it.get("Class")
            if cl == "CIITSymbolComp" and it.find("CIITSymbolComp").get("CiComponent") in kill_ci:
                kill_sym.add(it.get("ID")); self.objs.remove(it)
            elif cl in ("CIITProbeExtComponent", "CODTextComp"):
                kill_sym.add(it.get("ID")); self.objs.remove(it)
        for it in list(self.refs):
            if it.get("ID") in kill_sym:
                self.refs.remove(it)
        # 位号管理表里已删元件的旧记录也要删：底稿里有 “PR1 → 显示为 Output” 这样的映射，
        # 新放的同名探针会被套上旧名字（输出名变成 V(Output)），验证时就对不上号。
        # 注意要和“已用编号表”RefDesPrefixUsage 一起清：只删映射不删编号表，Multisim 会认为新放的
        # R1/Q1 与已用编号冲突，打开时自动改号（Q2→Q3…），网表就对不上了（verify 的 A 层抓到过）。
        for parent in self.root.iter():
            for k in list(parent):
                if k.tag == "CIRToInfoMapItem" and k.get("CIRKey", "").replace("&ASC", "") not in keep:
                    parent.remove(k)
                elif k.tag == "RefDesPrefixUsage" and k.get("Class") and k.get("RefDes", "").replace("&ASC", "") != "XSC":
                    parent.remove(k)
        # 剩下的（示波器）重新登记引脚
        self.w.conn = {}
        for sid, s in msxml.symbols(self.objs):
            for pn, cid, pc, x, y in msxml.pins_of(s):
                self.w.conn[cid] = pc

    def _title(self, title):
        self.title_tpl = None
        src = msxml.parse(BASE)
        _, objs, _ = msxml.diagram(src)
        for it in objs:
            if it.get("Class") == "CODTextComp":
                self.title_tpl = it
                break

    def text(self, s, x, y, size=None, bold=None):
        it = copy.deepcopy(self.title_tpl)
        tid = self.w.nid()
        it.set("ID", tid)
        t = it.find("CODTextComp")
        t.set("Output", enc(s))
        t.set("Transformer-M20", dstr(x)); t.set("Transformer-M21", dstr(y))
        if size: t.set("Font-Height", str(size))
        if bold is not None: t.set("Font-Weight", "700" if bold else "400")
        self.objs.append(it)
        return it

    # ---------- 元件 ----------
    def add(self, kind, ref, value=None, at=None, pin=None, **kw):
        """克隆模板 kind，位号 ref，把引脚 pin（默认第一个）放到 at=(x, y)。"""
        if kind not in TPL:
            raise KeyError(f"unknown template {kind!r}; available: {sorted(TPL)} "
                           f"(add more with tplfind.py, see SKILL.md 'Adding a template')")
        if kind == "GND":
            ref = "0"
        elif ref in self.parts:
            raise ValueError(f"duplicate reference designator {ref!r}")
        if at is not None and (at[0] % 9 or at[1] % 9):
            raise ValueError(f"{ref}: at={at} is off the 9-unit grid; use multiples of 9")
        fname, name = TPL[kind]
        src = _src(fname)
        for d in src.iter("CIITDiagram"):
            els = d.find("Elements")
            if els is None:
                continue
            comp = next((i for i in els if i.get("Class") == "CiComponent"
                         and i.find("CiComponent").get("LocalName", "").replace("&ASC", "") == name), None)
            if comp is not None:
                break
        objs = d.find("Components/CODComposite/Objects")
        c = comp.find("CiComponent")
        sym = next(i for i in objs if i.get("Class") == "CIITSymbolComp"
                   and i.find("CIITSymbolComp").get("CiComponent") == comp.get("CiID"))
        ports = [next(i for i in els if i.get("CiID") == p.get("CiID")) for p in c.find("Ports")]
        model = [next(i for i in els if i.get("CiID") == c.get("Model"))] if c.get("Model") else []
        kit = [copy.deepcopy(x) for x in [sym, comp] + ports + model]
        # 新 ID
        own = set()
        for k in kit:
            for e in k.iter():
                for a in ("ID", "CiID"):
                    if e.get(a) and e.tag == "Item" and (e is k or e.get("Class")):
                        own.add(e.get(a))
        m = {o: self.w.nid() for o in own}
        for k in kit:
            for e in k.iter():
                for a in REF_ATTRS:
                    if a == "SymCompID" and e.tag == "CiComponent":
                        e.set(a, m.get(sym.get("ID"), e.get(a))); continue
                    v = e.get(a)
                    if v in m:
                        e.set(a, m[v])
                for a in ("Circuit", "Scope"):
                    if e.get(a):
                        e.set(a, self.circ_id)
                if e.tag == "CIITPinConnectorComp":
                    cl = e.find("ConnectList")
                    if cl is not None:
                        e.remove(cl)
                if e.tag == "CiPort":
                    nd = e.find("Nodes")
                    if nd is not None:
                        for x in list(nd):
                            nd.remove(x)
        sym_it, comp_it = kit[0], kit[1]
        s = sym_it.find("CIITSymbolComp")
        ci = comp_it.find("CiComponent")
        ci.set("InstanceID", "{%s}" % str(uuid.uuid4()).upper())
        # 位号
        ci.set("LocalName", enc(ref))
        s.set("InstanceRefDes", enc(ref))
        for t in s.iter("CIITSymTextCompName"):
            t.set("Output", enc(ref))
        if kind == "GND":
            for t in s.iter("CIITSymTextCompName"):
                t.set("Hidden", "1")
        # 标签字体统一：Arial 8 常规
        for t in list(s.iter("CIITSymTextCompName")) + list(s.iter("CIITSymTextCompValue")):
            t.set("Font-Height", "8"); t.set("Font-Weight", "400"); t.set("Font-FaceName", "&ASCArial")
        # 插入
        self.objs.append(sym_it)
        for k in kit[1:]:
            self.els.append(k)
        ET.SubElement(self.circ.find("Components"), "Item", CiID=comp_it.get("CiID"))
        if model:
            ET.SubElement(self.circ.find("Models"), "Item", CiID=kit[-1].get("CiID"))
        # 摆放：平移整个符号
        pins = {p[0]: p for p in msxml.pins_of(s)}
        pin = pin or next(iter(pins))
        if at is not None:
            dx, dy = at[0] - pins[pin][3], at[1] - pins[pin][4]
            s.set("Transformer-M20", dstr(float(s.get("Transformer-M20")) + dx))
            s.set("Transformer-M21", dstr(float(s.get("Transformer-M21")) + dy))
        pins = {p[0]: (p[1], p[3], p[4]) for p in msxml.pins_of(s)}
        for p in pins.values():
            self.w.conn[p[0]] = next(pc for pn, cid, pc, x, y in msxml.pins_of(s) if cid == p[0])
        part = Part(ref, s, ci, pins)
        part.kind = kind
        if value is not None:
            self.set_value(part, kind, value, **kw)
        key = ref
        if kind == "GND":                      # every ground symbol is named "0"
            n = sum(k.startswith("0#") for k in self.parts)
            key = f"0#{n}"
        self.parts[key] = part
        return part

    def set_value(self, part, kind, v, **kw):
        ci, s = part.comp, part.sym
        if kind == "VAC":
            return self._set_vac(part, *v)
        unit = {"R": "Ω", "C": "F", "L": "H", "V": "V"}[kind[0] if kind[0] in "RCL" else "V"]
        num = eng(v)
        disp = num.replace("u", "µ") + unit
        if kind == "VDC":
            disp = num + "V "
        pl = ci.find(".//CiaParamList")
        dbl = list(pl.find("doubles")); par = list(pl.find("parameters"))
        old_num = par[1].get("Value")
        old_disp = next((t.get("Output") for t in s.iter("CIITSymTextCompValue")), None)
        dbl[1].set("Value", dstr(v)); par[1].set("Value", enc(num))
        # 显示用字符串：只改和旧值完全相同的 CiaCString。
        # 不要按“像数字”去匹配：模板里还有别的数字字段（如 "1"），改坏了仿真就不对
        for e in ci.iter("CiaCString"):
            sv = e.get("String")
            if sv == old_num:
                e.set("String", enc(num))
            elif old_disp and sv == old_disp:
                e.set("String", enc(disp))
        for t in s.iter("CIITSymTextCompValue"):
            t.set("Output", enc(disp))

    def _set_vac(self, part, amp, freq):
        """正弦源：SPICE 模板 sin(#3 #1 #5 ...)，参数表第 2 项峰值、第 6 项频率。"""
        pl = part.comp.find(".//CiaParamList")
        dbl = list(pl.find("doubles")); par = list(pl.find("parameters"))
        for i, x in ((1, amp), (5, freq)):
            dbl[i].set("Value", dstr(x)); par[i].set("Value", enc(eng(x)))
        disp = f"{eng(amp)}Vpk \n{eng(freq)}Hz \n0°"
        for t in part.sym.iter("CIITSymTextCompValue"):
            t.set("Output", enc(disp))

    # ---------- 示波器（底稿自带的 XSC2，两通道：1=A+ 4=A- 2=B+ 5=B- 3/6=外触发）----------
    def scope(self, at, pin="1"):
        mine = {id(p.sym) for p in self.parts.values()}
        xsc = next(s for sid, s in msxml.symbols(self.objs) if id(s) not in mine)
        pins = {p[0]: p for p in msxml.pins_of(xsc)}
        dx, dy = at[0] - pins[pin][3], at[1] - pins[pin][4]
        xsc.set("Transformer-M20", dstr(float(xsc.get("Transformer-M20")) + dx))
        xsc.set("Transformer-M21", dstr(float(xsc.get("Transformer-M21")) + dy))
        part = Part("XSC2", xsc, None, {p[0]: (p[1], p[3], p[4]) for p in msxml.pins_of(xsc)})
        self.parts["XSC2"] = part
        return part

    # ---------- 探针（放在导线上的点，按位置识别网络）----------
    def sim_settings(self, tstop=None, tmax=None, ic=None):
        """保存时写入仿真设置：所有瞬态分析块（含 Fourier/参数扫描等内嵌的 Tran）和交互式仿真(F5)。
        tmax 一定要给：默认 "calculate" ≈ TSTOP/50，对高频信号会把波形画坏。经验值 tmax ≤ 周期/40。
        ic: "zero"（从零起振，适合振荡器）或 "auto"（先算直流工作点）。"""
        self.sim = dict(tstop=tstop, tmax=tmax, ic=ic)

    def probe(self, name, x, y, show=True, box=(13, -75), node=None):
        """电压/电流探针。node = 它测的 .cir 节点名（verify.py 用来和 ngspice 配对，强烈建议写）。"""
        if not hasattr(self, "probe_nodes"):
            self.probe_nodes = {}
        self.probe_nodes[name] = node
        src = msxml.parse(BASE)
        d = next(src.iter("CIITDiagram"))
        objs = d.find("Components/CODComposite/Objects")
        sym = copy.deepcopy(next(i for i in objs if i.get("Class") == "CIITProbeExtComponent"))
        ci = copy.deepcopy(next(i for i in d.find("Elements") if i.get("Class") == "CiProbeExtComp"))
        sid, cid = self.w.nid(), self.w.nid()
        sym.set("ID", sid); ci.set("CiID", cid)
        p = sym.find("CIITProbeExtComponent")
        p.set("CiProbeExtComp", cid)
        p.set("Transformer-M20", dstr(x)); p.set("Transformer-M21", dstr(y))
        p.set("ShowInfo", "1" if show else "0")
        p.set("InfoBoxOffsetX", str(box[0])); p.set("InfoBoxOffsetY", str(box[1]))
        self.probe_n = getattr(self, "probe_n", 0) + 1
        p.set("UniqueID", str(100 + self.probe_n))
        c = ci.find("CiProbeExtComp")
        c.set("LocalName", enc(name)); c.set("SymCompID", sid); c.set("Circuit", self.circ_id)
        c.set("InstanceID", "{%s}" % str(uuid.uuid4()).upper())
        self.objs.append(sym)
        ET.SubElement(self.refs, "Item", ID=sid, Class="CIITProbeExtComponent")
        self.els.append(ci)
        ET.SubElement(self.circ.find("ProbeExts"), "Item", CiID=cid)

    # ---------- 导线 ----------
    def junction(self, x, y):
        return self.w.junction(x, y), (x, y)

    def wire(self, a, b, via=(), net=None):
        """a、b 为 Part[pin] 或 junction() 的返回值；via 为中间拐点。"""
        (ta, pa), (tb, pb) = a, b
        pts = [pa, *via, pb]
        pts = [p for i, p in enumerate(pts) if i == 0 or tuple(p) != tuple(pts[i - 1])]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            assert x1 == x2 or y1 == y2, f"导线不是横平竖直: {pts}"
        self.w.wire(ta, tb, pts, net)

    def save(self, path):
        """保存为 XML；path 不带扩展名时存到 msenv.OUT。返回 .xml 路径。"""
        if not os.path.isabs(path):
            path = os.path.join(msenv.OUT, path)
        if not path.endswith(".xml"):
            path += ".xml"
        wiring.dump(self.root, path)
        sim = getattr(self, "sim", None)
        if sim:
            import simset
            text = open(path, "rb").read().decode("latin-1")
            text, _ = simset.edit(text, sim["tmax"], sim["tstop"], sim["ic"])
            open(path, "wb").write(text.encode("latin-1"))
        meta = {"probes": getattr(self, "probe_nodes", {}),
                "parts": {r: p.comp.get("LocalName", "").replace("&ASC", "") for r, p in self.parts.items() if p.comp is not None},
                "sim": sim}
        import json
        json.dump(meta, open(path[:-4] + ".meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return path


# ---------- 模板信息（给 agent 排版用：不用猜引脚位置） ----------
def templates():
    """{模板键: {"pins": {引脚: (dx, dy)}, "ref_pin": 第一个引脚, "body": (x0,y0,x1,y1) 相对 ref_pin}}"""
    d = Doc()
    out = {}
    for i, kind in enumerate(TPL):
        p = d.add(kind, f"T{i}", at=(450, 450))
        first = next(iter(p.pins))
        x0, y0 = p.pins[first][1], p.pins[first][2]
        b = p.body()
        out[kind] = {"source": TPL[kind][0], "ref_pin": first,
                     "pins": {k: (v[1] - x0, v[2] - y0) for k, v in p.pins.items()},
                     "body": tuple(round(v - o) for v, o in zip(b, (x0, y0, x0, y0))) if b else None,
                     "model": model_name(kind)}
    return out


def _kit_comp(kind):
    fname, name = TPL[kind]
    for d in _src(fname).iter("CIITDiagram"):
        els = d.find("Elements")
        if els is None:
            continue
        for i in els:
            if i.get("Class") == "CiComponent" and i.find("CiComponent").get("LocalName", "").replace("&ASC", "") == name:
                return els, i.find("CiComponent")
    raise KeyError(kind)


def model_name(kind):
    """Multisim model name used by this template (what to reference in your .cir), or None."""
    els, c = _kit_comp(kind)
    if not c.get("Model"):
        return None
    m = next(i for i in els if i.get("CiID") == c.get("Model"))
    return m.find("CiModel").get("LocalName", "").replace("&ASC", "")


def model_text(kind):
    """The exact .MODEL text Multisim simulates for this template (paste into the .cir so ngspice matches)."""
    els, c = _kit_comp(kind)
    if not c.get("Model"):
        return None
    m = next(i for i in els if i.get("CiID") == c.get("Model"))
    for e in m.iter("CiaCString"):
        s = e.get("String", "")
        if ".MODEL" in s.upper():
            return s.replace("&ASC", "").replace("\r\n", "\n")
    return None
