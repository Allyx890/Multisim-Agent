"""Multisim XML 读取工具：安全解析、坐标变换、引脚绝对位置。"""
import re
import xml.etree.ElementTree as ET

NUL = bytes([0])
_ATTR = re.compile(rb'="([^"]*)"')
_WS = {b"\r": b"&#13;", b"\n": b"&#10;", b"\t": b"&#9;"}


def _keep_ws(m):
    v = m.group(1)
    for k, r in _WS.items():
        v = v.replace(k, r)
    return b'="' + v + b'"'


def fromstring(data):
    """解析 Multisim XML（bytes）。
    1) 去掉 NUL（部分样例的属性里有，XML 解析器不收）；
    2) 属性值里的原始 CR/LF/TAB 先转成字符引用。否则按 XML 规范它们会被规范化成空格，
       SIMULATION_INFO（仿真设置，用换行分隔）、多行文字等数据被破坏，
       Multisim 打开后一运行仿真就访问冲突崩溃。ElementTree 写出时会再转回字符引用。"""
    data = data.replace(NUL, b"")
    return ET.fromstring(_ATTR.sub(_keep_ws, data))


def parse(path):
    """读 XML 或 .ms14，返回根元素。一律用它，不要直接 ET.parse。"""
    data = open(path, "rb").read()
    if data.startswith(b"MSMCompressed"):
        import ms14
        data = ms14.decompress_ms14(data)
    return fromstring(data)


def T(e):
    """元素的变换矩阵 (m00, m01, m10, m11, m20, m21)；没有就是单位阵。"""
    g = lambda k, d: float(e.get("Transformer-" + k, d))
    return (g("M00", 1), g("M01", 0), g("M10", 0), g("M11", 1), g("M20", 0), g("M21", 0))


def apply(t, x, y):
    m00, m01, m10, m11, m20, m21 = t
    return (x * m00 + y * m10 + m20, x * m01 + y * m11 + m21)


def diagram(root):
    d = next(root.iter("CIITDiagram"))
    c = d.find("Components/CODComposite")
    return d, c.find("Objects"), c.find("ReferencedComponents")


def symbols(objs):
    for it in objs:
        if it.get("Class") == "CIITSymbolComp":
            yield it.get("ID"), it.find("CIITSymbolComp")


def pins_of(sym):
    """返回 [(引脚名, 连接器ID, 连接器元素, 绝对x, 绝对y)]"""
    out = []
    ts = T(sym)
    for it in sym.find("Objects"):
        if it.get("Class") != "CIITPinSymbolComp":
            continue
        ps = it.find("CIITPinSymbolComp")
        tp = T(ps)
        for c in ps.find("Objects"):
            if c.get("Class") == "CIITPinConnectorComp":
                pc = c.find("CIITPinConnectorComp")
                x, y = float(pc.get("ptCenterX")), float(pc.get("ptCenterY"))
                x, y = apply(T(pc), x, y)
                x, y = apply(tp, x, y)
                x, y = apply(ts, x, y)
                out.append((ps.get("PinName").replace("&ASC", ""), c.get("ID"), pc, round(x, 3), round(y, 3)))
    return out
