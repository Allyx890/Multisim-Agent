// 用 Multisim 自己的仿真器求直流工作点，打印每个探针的 V(...) 和 I(...)。
// 用法: msop.exe 文件.ms14
// 用途: 和 ngspice 的 .op 逐点对比，最快地确认“Multisim 里仿真的电路就是你以为的那个电路”。
// 探针电流 I(PRx) 是流过探针所在导线的电流；若比例离谱（如 V/I ≈ 1e-12 Ω），说明元件值在仿真里失效了。
// 必须编译成 32 位：csc -platform:x86。
using System;
using System.Globalization;
using System.Reflection;

class MsOp {
    static object Call(object o, string m, params object[] a) { return o.GetType().InvokeMember(m, BindingFlags.InvokeMethod, null, o, a); }
    static string Msg(Exception e) { return (e.InnerException ?? e).Message; }

    [STAThread]
    static int Main(string[] args) {
        if (args.Length < 1) { Console.WriteLine("usage: msop.exe file.ms14"); return 1; }
        object app = Activator.CreateInstance(Type.GetTypeFromProgID("MultisimInterface.MultisimApp"));
        Call(app, "Connect");
        object c = Call(app, "OpenFile", args[0]);
        object[] outs = (object[])Call(c, "EnumOutputs", 0);
        if (outs == null || outs.Length == 0) { Console.WriteLine("no probe outputs (place probes on wires)"); return 3; }
        try { Call(c, "DoDCOperatingPoint", new object[] { outs }); }
        catch (Exception e) { Console.WriteLine("op failed: " + Msg(e)); return 2; }
        System.Threading.Thread.Sleep(1000);
        foreach (object o in outs) {
            object[] a = new object[] { o, null, 0 };
            ParameterModifier pm = new ParameterModifier(3); pm[1] = true; pm[2] = true;
            try {
                c.GetType().InvokeMember("GetOutputData", BindingFlags.InvokeMethod, null, c, a, new ParameterModifier[] { pm }, null, null);
                double[,] d = a[1] as double[,];
                Console.WriteLine(o + " = " + (d != null && d.GetLength(1) > 0 ? d[1, 0].ToString("G6", CultureInfo.InvariantCulture) : "null"));
            } catch (Exception e) { Console.WriteLine(o + " failed: " + Msg(e)); }
        }
        return 0;
    }
}
