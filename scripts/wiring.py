"""在 Multisim XML 的图形层里删除/生成导线、端点和连接点。"""
import copy
import uuid
import xml.etree.ElementTree as ET
import msxml

LINK_ATTR = dict(instID="0", Stretchable="1", Moveable="1", LabelSelectable="1", Selectable="1",
                 LockedPenColor="0", LockedBrushColor="0", Layer="511", ArrowAtSource="0", ArrowAtTarget="0",
                 LineHidden="0", PenColor="255", FgColor="0", BgColor="16777215", **{"Pen-Style": "0", "Pen-Width": "1", "Pen-Color": "255"},
                 Hidden="0", ShowWhenNetSet="0", IsElvisHiddenWireFlags="0")
BASE_ATTR = dict(instID="0", Stretchable="1", Moveable="1", LabelSelectable="1", Selectable="1",
                 LockedPenColor="0", LockedBrushColor="0", Layer="511", Text="", Internal="0")
# 导线端点：隐形笔（Pen-Style=5），否则会画出圆点
END_TAIL = {"Pen-Style": "5", "Pen-Width": "1", "Pen-Color": "0", "Hidden": "0"}
# 连接点（红色圆点）
JUNC_TAIL = {"PenColor": "255", "Pen-Style": "0", "Pen-Width": "1", "Pen-Color": "255"}
IDENT = {"Transformer-M00": "1.", "Transformer-M01": "0.", "Transformer-M10": "0.", "Transformer-M11": "1.",
         "Transformer-M20": "0.", "Transformer-M21": "0."}


def fnum(v):
    v = float(v)
    return f"{int(v)}" if v == int(v) else f"{v:g}"


class Wiring:
    def __init__(self, root, start_id=700000000):
        self.root = root
        self.diag, self.objs, self.refs = msxml.diagram(root)
        self.next = start_id
        self.conn = {}          # 连接器ID -> 元素（元件引脚的 CIITPinConnectorComp）
        for sid, s in msxml.symbols(self.objs):
            for pn, cid, pc, x, y in msxml.pins_of(s):
                self.conn[cid] = pc
        self.junc = {}          # 连接点ID -> 元素

    def nid(self):
        self.next += 8
        return str(self.next)

    def clear(self):
        """删掉所有导线、导线端点、连接点、网络名文字，并清空元件引脚的连接表。"""
        kill = {"CIITLinkComp", "CODPinComp", "CODNodeTextComp"}
        for box in (self.objs, self.refs):
            for it in list(box):
                if it.get("Class") in kill:
                    box.remove(it)
        for it in list(self.refs):            # 引用区里对引脚连接器的空引用也删掉，后面按需加
            if it.get("Class") == "CIITPinConnectorComp" and not len(it):
                self.refs.remove(it)
        for pc in self.conn.values():
            cl = pc.find("ConnectList")
            if cl is not None:
                pc.remove(cl)
        # 电气层节点交给 Multisim 重算
        els = self.diag.find("Elements")
        for it in list(els):
            if it.get("Class") == "CiNode":
                els.remove(it)
        for e in self.diag.iter():
            if e.tag in ("CiCircuit", "CiPort"):
                nd = e.find("Nodes")
                if nd is not None:
                    for k in list(nd):
                        nd.remove(k)

    def _connect_list(self, el):
        cl = el.find("ConnectList")
        if cl is None:
            cl = ET.SubElement(el, "ConnectList")
        return cl

    def junction(self, x, y):
        jid = self.nid()
        it = ET.SubElement(self.objs, "Item", ID=jid, Class="CODPinComp")
        p = ET.SubElement(it, "CODPinComp", Class="CODPinComp", **BASE_ATTR, CenterX=fnum(x), CenterY=fnum(y), Mobility="0", **JUNC_TAIL, **IDENT, Hidden="0")
        ET.SubElement(ET.SubElement(p, "ElectricalObject", HiddenName="0"), "ModifierInfo")
        ET.SubElement(p, "ConnectList")
        ET.SubElement(self.refs, "Item", ID=jid, Class="CODPinComp")
        self.junc[jid] = p
        return ("j", jid)

    def _end(self, target, x, y):
        eid = self.nid()
        it = ET.SubElement(self.refs, "Item", ID=eid, Class="CODPinComp")
        p = ET.SubElement(it, "CODPinComp", Class="CODPinComp", **BASE_ATTR, CenterX=fnum(x), CenterY=fnum(y), Mobility="1", **END_TAIL)
        ET.SubElement(ET.SubElement(p, "ElectricalObject", HiddenName="0"), "ModifierInfo")
        cl = ET.SubElement(p, "ConnectList")
        kind, tid = target
        if kind == "p":
            ET.SubElement(cl, "Item", ID=tid, Class="CIITPinConnectorComp")
            ET.SubElement(self._connect_list(self.conn[tid]), "Item", ID=eid, Class="CODPinComp")
            if not any(r.get("ID") == tid for r in self.refs):
                ET.SubElement(self.refs, "Item", ID=tid, Class="CIITPinConnectorComp")
        else:
            ET.SubElement(cl, "Item", ID=tid, Class="CODPinComp")
            ET.SubElement(self.junc[tid].find("ConnectList"), "Item", ID=eid, Class="CODPinComp")
        return eid

    def wire(self, a, b, pts, net=None):
        """a、b 为 ("p", 连接器ID) 或 ("j", 连接点ID)；pts 为从 a 到 b 的折线点（含两端）。"""
        lid = self.nid()
        e1 = self._end(a, *pts[0])
        e2 = self._end(b, *pts[-1])
        it = ET.SubElement(self.objs, "Item", ID=lid, Class="CIITLinkComp")
        l = ET.SubElement(it, "CIITLinkComp", Class="CIITLinkComp", **LINK_ATTR, Connect1=e1, Connect2=e2, Node="0", NodeText="0")
        P = ET.SubElement(l, "Points")
        for x, y in pts:
            ET.SubElement(P, "Item", X=fnum(x), Y=fnum(y))
        eo = ET.SubElement(l, "ElectricalObject", HiddenName="0")
        mi = ET.SubElement(eo, "ModifierInfo")
        if net:
            el = ET.SubElement(mi, "Element", NetModifier="&ASCNI_EWB_NET_NAME")
            # one real random GUID per net name (made-up GUIDs made Multisim draw those nets in black)
            if not hasattr(self, "_net_guid"):
                self._net_guid = {}
            g = self._net_guid.setdefault(net, "{%s}" % str(uuid.uuid4()).upper())
            ET.SubElement(el, "Item", Value="&ASC" + net, Guid=g)
        ET.SubElement(self.refs, "Item", ID=lid, Class="CIITLinkComp")
        return lid


def dump(root, path):
    s = ET.tostring(root, encoding="unicode")
    # Multisim 的解析器不解码属性里的 &#10; 这类字符引用，会把它当成字面文本：
    # SPICE 模板（"…vres%p &#10;.model vres%p r(…)"）因此坏掉，电阻在仿真里变成约 0 Ω，
    # 多行 .MODEL 直接 E_FAIL。Multisim 自己保存时写的是字面换行，这里照做。
    s = s.replace("&#10;", "\n").replace("&#13;", "\r").replace("&#09;", "\t").replace("&#9;", "\t")
    open(path, "wb").write(b'<?xml version="1.0" encoding="ASCII"?>\n' + s.encode("ascii", "xmlcharrefreplace"))
