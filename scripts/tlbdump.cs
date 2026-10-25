using System;
using DllImportAttribute = System.Runtime.InteropServices.DllImportAttribute; using CharSet = System.Runtime.InteropServices.CharSet; using Marshal = System.Runtime.InteropServices.Marshal;
using System.Runtime.InteropServices.ComTypes;
class D {
    [DllImport("oleaut32.dll", CharSet = CharSet.Unicode)] static extern int LoadTypeLibEx(string f, int k, out ITypeLib tl);
    static string VT(TYPEDESC td, ITypeInfo ti) {
        int vt = td.vt;
        if (vt == 26) { TYPEDESC inner = (TYPEDESC)Marshal.PtrToStructure(td.lpValue, typeof(TYPEDESC)); return VT(inner, ti) + "*"; }
        if (vt == 27) { TYPEDESC inner = (TYPEDESC)Marshal.PtrToStructure(td.lpValue, typeof(TYPEDESC)); return "SAFEARRAY(" + VT(inner, ti) + ")"; }
        if (vt == 29) { ITypeInfo r; ti.GetRefTypeInfo((int)td.lpValue.ToInt64(), out r); string n, doc, hf; int hc; r.GetDocumentation(-1, out n, out doc, out hc, out hf); return n; }
        return "vt" + vt;
    }
    static void Main(string[] a) {
        ITypeLib tl; LoadTypeLibEx(a[0], 2, out tl);
        int n = tl.GetTypeInfoCount();
        for (int i = 0; i < n; i++) {
            ITypeInfo ti; tl.GetTypeInfo(i, out ti);
            string name, doc, hf; int hc; ti.GetDocumentation(-1, out name, out doc, out hc, out hf);
            IntPtr pta; ti.GetTypeAttr(out pta); TYPEATTR ta = (TYPEATTR)Marshal.PtrToStructure(pta, typeof(TYPEATTR));
            if (a.Length > 1 && name != a[1]) { ti.ReleaseTypeAttr(pta); continue; }
            Console.WriteLine("== " + name + " kind=" + ta.typekind + " guid=" + ta.guid + " funcs=" + ta.cFuncs + " flags=" + ta.wTypeFlags);
            for (int f = 0; f < ta.cFuncs; f++) {
                IntPtr pfd; ti.GetFuncDesc(f, out pfd); FUNCDESC fd = (FUNCDESC)Marshal.PtrToStructure(pfd, typeof(FUNCDESC));
                string[] names = new string[fd.cParams + 1]; int cn; ti.GetNames(fd.memid, names, names.Length, out cn);
                string s = "  [" + fd.memid + " vt_off=" + fd.oVft + " inv=" + fd.invkind + "] " + names[0] + "(";
                for (int p = 0; p < fd.cParams; p++) {
                    ELEMDESC ed = (ELEMDESC)Marshal.PtrToStructure(new IntPtr(fd.lprgelemdescParam.ToInt64() + p * Marshal.SizeOf(typeof(ELEMDESC))), typeof(ELEMDESC));
                    s += (p > 0 ? ", " : "") + "[" + ed.desc.paramdesc.wParamFlags + "] " + VT(ed.tdesc, ti) + " " + (p + 1 < cn ? names[p + 1] : "");
                }
                Console.WriteLine(s + ") -> " + VT(fd.elemdescFunc.tdesc, ti));
                ti.ReleaseFuncDesc(pfd);
            }
            ti.ReleaseTypeAttr(pta);
        }
    }
}
