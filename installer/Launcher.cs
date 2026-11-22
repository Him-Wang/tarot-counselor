// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright (c) 2026 Him-Wang
// Olivia.exe —— 安装后放在程序目录，双击即可后台启动服务并打开浏览器。
// 纯 .NET Framework 4，无控制台窗口，不依赖任何 .bat / .ps1。
using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

internal class Launcher
{
    [STAThread]
    private static void Main()
    {
        try { Run(); }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Olivia 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static void Run()
    {
        string baseDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string agentDir = Path.Combine(baseDir, "agent");
        string server = Path.Combine(agentDir, "server.py");
        if (!File.Exists(server))
        {
            MessageBox.Show("找不到 agent\\server.py，安装似乎不完整，请重新安装。", "Olivia");
            return;
        }

        if (!IsRunning())
        {
            string pyw = FindPythonW();
            if (pyw == null)
            {
                MessageBox.Show("未找到 Python 3（pythonw.exe）。\n请先安装 Python 3 并在安装时勾选 “Add Python to PATH”。", "Olivia");
                return;
            }
            var psi = new ProcessStartInfo(pyw, "\"" + server + "\"");
            psi.WorkingDirectory = agentDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            Process.Start(psi);
            for (int i = 0; i < 40 && !IsRunning(); i++) Thread.Sleep(250);
        }

        Process.Start(new ProcessStartInfo("http://127.0.0.1:8765") { UseShellExecute = true });
    }

    private static bool IsRunning()
    {
        try
        {
            using (var client = new TcpClient())
            {
                client.Connect("127.0.0.1", 8765);
                return true;
            }
        }
        catch { return false; }
    }

    private static string FindPythonW()
    {
        string onPath = FindOnPath("pythonw.exe");
        if (onPath != null) return onPath;

        try
        {
            var psi = new ProcessStartInfo("py", "-3 -c \"import sys;print(sys.executable)\"");
            psi.RedirectStandardOutput = true;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            var p = Process.Start(psi);
            string exe = p.StandardOutput.ReadToEnd().Trim();
            p.WaitForExit();
            if (File.Exists(exe))
            {
                string sibling = Path.Combine(Path.GetDirectoryName(exe), "pythonw.exe");
                if (File.Exists(sibling)) return sibling;
            }
        }
        catch { }

        string pyRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python");
        if (Directory.Exists(pyRoot))
        {
            string[] dirs = Directory.GetDirectories(pyRoot, "Python3*");
            Array.Sort(dirs, (a, b) => string.Compare(b, a, StringComparison.OrdinalIgnoreCase));
            foreach (string d in dirs)
            {
                string candidate = Path.Combine(d, "pythonw.exe");
                if (File.Exists(candidate)) return candidate;
            }
        }
        return null;
    }

    private static string FindOnPath(string name)
    {
        string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string dir in pathEnv.Split(Path.PathSeparator))
        {
            try
            {
                string candidate = Path.Combine(dir, name);
                if (File.Exists(candidate)) return candidate;
            }
            catch { }
        }
        return null;
    }
}
