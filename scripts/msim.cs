// 用 Multisim 自己的仿真器跑瞬态，并把探针电压存成 CSV。
// 用法: msim.exe 文件.ms14 终止时间s 输出前缀 [采样间隔s=1e-8]
// 输出: 前缀_V_PR1.csv（t,v）……  电路里必须放了探针（msgen.Doc.probe），只有探针能作为输出。
//
// 已验证的调用协议（见 references/lessons.md）：
//   SetOutputRequest(名, 1=线性插值, 采样率, 每块点数, repeat=true)
//   RunSimulation(终止时间, pause=true)        —— 跑到终止时间后暂停
//   循环: OutputReady(名) 为真 → GetOutputData(名, out 数据, out 插值方式)  —— 第 2、3 参数都是 [out]
//         每次返回一块 double[2, N]（第 0 行 t，第 1 行 v），接起来直到 t >= 终止时间
// 必须编译成 32 位：csc -platform:x86（MSInterface.dll 是 32 位进程内组件）。
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;

class MSim {
    static object Call(object o, string m, params object[] a) { return o.GetType().InvokeMember(m, BindingFlags.InvokeMethod, null, o, a); }
    static object Get(object o, string m) { return o.GetType().InvokeMember(m, BindingFlags.GetProperty, null, o, null); }
    static string Err(object o) { try { return (string)Get(o, "LastErrorMessage"); } catch { return "?"; } }
    static string Msg(Exception e) { return e.InnerException != null ? e.InnerException.Message : e.Message; }

    static double[,] Data(object c, string n) {
        object[] a = new object[] { n, null, 0 };
        ParameterModifier pm = new ParameterModifier(3); pm[1] = true; pm[2] = true;
        c.GetType().InvokeMember("GetOutputData", BindingFlags.InvokeMethod, null, c, a, new ParameterModifier[] { pm }, null, null);
        return a[1] as double[,];
    }

    [STAThread]
    static int Main(string[] args) {
        CultureInfo IC = CultureInfo.InvariantCulture;
        if (args.Length < 3) { Console.WriteLine("usage: msim.exe file.ms14 tstop prefix [dt]"); return 1; }
        double T = double.Parse(args[1], IC);
        double dt = args.Length > 3 ? double.Parse(args[3], IC) : 1e-8;

        object app = null, c = null;
        for (int k = 0; k < 3 && c == null; k++) {
            try {
                app = Activator.CreateInstance(Type.GetTypeFromProgID("MultisimInterface.MultisimApp"));
                Call(app, "Connect");
                c = Call(app, "OpenFile", args[0]);
            } catch (Exception e) {
                Console.WriteLine("open attempt " + k + " failed: " + Msg(e) + " | " + Err(app));
                System.Threading.Thread.Sleep(3000);
            }
        }
        if (c == null) return 2;
        Console.WriteLine("opened " + Get(c, "CircuitName"));

        List<string> outs = new List<string>();
        object[] all = Call(c, "EnumOutputs", 0) as object[];
        if (all == null) all = new object[0];
        foreach (object o in all) if (((string)o).StartsWith("V(")) outs.Add((string)o);
        if (outs.Count == 0) { Console.WriteLine("no probe outputs (place probes on wires)"); return 3; }
        Console.WriteLine("outputs " + string.Join(",", outs));
        // 每块点数不能超过总点数，否则一块永远凑不满，OutputReady 一直为假（曾在 2 us 仿真时死等）
        int block = (int)Math.Max(10, Math.Min(2000, Math.Floor(T / dt / 2)));
        foreach (string n in outs) Call(c, "SetOutputRequest", n, 1, 1.0 / dt, block, true);

        Dictionary<string, List<double[]>> acc = new Dictionary<string, List<double[]>>();
        foreach (string n in outs) acc[n] = new List<double[]>();
        Call(c, "RunSimulation", T, true);
        DateTime t0 = DateTime.Now;
        double tmin = 0;
        DateTime last = DateTime.Now;
        while (tmin < T - 2 * dt && (DateTime.Now - t0).TotalSeconds < 1800) {
            bool got = false;
            foreach (string n in outs) {
                bool ready = false;
                try { ready = (bool)c.GetType().InvokeMember("OutputReady", BindingFlags.GetProperty, null, c, new object[] { n }); }
                catch (Exception e) { Console.WriteLine("OutputReady failed: " + Msg(e) + " | " + Err(c)); goto done; }
                if (!ready) continue;
                double[,] d = Data(c, n);
                if (d == null) continue;
                got = true;
                for (int i = 0; i < d.GetLength(1); i++) acc[n].Add(new double[] { d[0, i], d[1, i] });
            }
            tmin = double.MaxValue;
            foreach (string n in outs) tmin = Math.Min(tmin, acc[n].Count > 0 ? acc[n][acc[n].Count - 1][0] : 0);
            if (got) last = DateTime.Now;
            else if ((DateTime.Now - last).TotalSeconds > 15) { Console.WriteLine("no new data for 15 s, stop"); break; }
            else System.Threading.Thread.Sleep(100);
        }
    done:
        try { Call(c, "StopSimulation"); } catch { }
        Console.WriteLine("sim time " + (tmin * 1e6).ToString("F1", IC) + " us, wall " + (DateTime.Now - t0).TotalSeconds.ToString("F1", IC) + " s");
        foreach (string n in outs) {
            string safe = n.Replace("(", "_").Replace(")", "");
            using (StreamWriter w = new StreamWriter(args[2] + "_" + safe + ".csv"))
                foreach (double[] r in acc[n]) w.WriteLine(r[0].ToString("R", IC) + "," + r[1].ToString("R", IC));
            Console.WriteLine("  " + n + ": " + acc[n].Count + " pts -> " + args[2] + "_" + safe + ".csv");
        }
        return 0;
    }
}
