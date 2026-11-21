// Olivia-setup.exe —— 单文件一键安装器（解压即装、建快捷方式、启动服务）。
// 纯 .NET Framework 4，用 csc.exe 编译；不依赖任何 .bat / .ps1 / pip / 7z。
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

internal class Setup
{
    private static string _target;
    private static string _pyw;

    [STAThread]
    private static void Main()
    {
        try { Run(); }
        catch (Exception ex)
        {
            MessageBox.Show(ex.ToString(), "安装失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static void Run()
    {
        // 1) 检测 Python 3（无 Python 时给出明确指引）
        _pyw = FindPythonW();
        if (_pyw == null)
        {
            DialogResult r = MessageBox.Show(
                "未检测到 Python 3。\n请先从 https://www.python.org/downloads/ 安装，\n安装时务必勾选 “Add Python to PATH”，装好后重新双击本安装器。\n\n点击“确定”打开下载页，或“取消”退出。",
                "Olivia 安装", MessageBoxButtons.OKCancel, MessageBoxIcon.Warning);
            if (r == DialogResult.OK)
                Process.Start(new ProcessStartInfo("https://www.python.org/downloads/") { UseShellExecute = true });
            return;
        }

        // 2) 选择安装目录（默认 %LOCALAPPDATA%\Olivia）
        string defaultDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Olivia");
        using (var dlg = new FolderBrowserDialog())
        {
            dlg.Description = "选择 Olivia 的安装目录（直接“确定”用默认位置）";
            dlg.SelectedPath = defaultDir;
            dlg.ShowNewFolderButton = true;
            if (dlg.ShowDialog() != DialogResult.OK) return;
            _target = dlg.SelectedPath;
        }

        // 3) 解压内嵌 payload（agent / knowledge / prompts / skills）
        string temp = Path.Combine(Path.GetTempPath(), "olivia-payload-" + Guid.NewGuid().ToString("N"));
        try
        {
            string zipPath = Path.Combine(temp, "payload.zip");
            Directory.CreateDirectory(temp);
            File.WriteAllBytes(zipPath, ReadEmbeddedBytes("payload.zip"));
            ZipFile.ExtractToDirectory(zipPath, temp);

            // 隐私清理：打包时已排除，这里再兜底一次
            Directory.CreateDirectory(_target);
            foreach (string d in new[] { "agent", "knowledge", "prompts", "skills" })
            {
                string src = Path.Combine(temp, d);
                if (Directory.Exists(src)) CopyDir(src, Path.Combine(_target, d));
            }
            foreach (string f in new[] { "README.md", "LICENSE" })
            {
                string src = Path.Combine(temp, f);
                if (File.Exists(src)) File.Copy(src, Path.Combine(_target, f), true);
            }
            CleanPrivate(_target);

            // 4) 释放启动器 Olivia.exe
            string launcher = Path.Combine(_target, "Olivia.exe");
            File.WriteAllBytes(launcher, ReadEmbeddedBytes("launcher.exe"));
        }
        finally
        {
            try { Directory.Delete(temp, true); } catch { }
        }

        // 5) 快捷方式（桌面 + 开始菜单）， COM WScript.Shell
        CreateShortcuts();

        // 6) 询问开机自启
        bool autostart = MessageBox.Show(
            "是否设置开机自动启动 Olivia？\n（是 = 每次登录 Windows 后自动在后台运行服务）",
            "Olivia 安装", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes;
        if (autostart) CreateAutostart();

        // 7) 立即启动服务 + 打开浏览器
        StartServer();
        Process.Start(new ProcessStartInfo("http://127.0.0.1:8765") { UseShellExecute = true });

        MessageBox.Show(
            "安装完成！\n\n服务已启动，浏览器已打开 http://127.0.0.1:8765\n" +
            "以后双击桌面「Olivia 奥莉薇娅」即可使用。\n\n" +
            "首次使用：点右上角「设置」填入你自己的 API key（DeepSeek 等）。",
            "Olivia 安装完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    private static byte[] ReadEmbeddedBytes(string name)
    {
        Assembly asm = Assembly.GetExecutingAssembly();
        using (Stream s = asm.GetManifestResourceStream(name))
        {
            if (s == null) throw new FileNotFoundException("缺少内嵌资源: " + name);
            using (var m = new MemoryStream())
            {
                s.CopyTo(m);
                return m.ToArray();
            }
        }
    }

    private static void CopyDir(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (string f in Directory.GetFiles(src)) File.Copy(f, Path.Combine(dst, Path.GetFileName(f)), true);
        foreach (string d in Directory.GetDirectories(src)) CopyDir(d, Path.Combine(dst, Path.GetFileName(d)));
    }

    private static void CleanPrivate(string target)
    {
        try { File.Delete(Path.Combine(target, "agent", "config.json")); } catch { }
        try { File.Delete(Path.Combine(target, "agent", "olivia.pid")); } catch { }
        string data = Path.Combine(target, "agent", "data");
        try { if (Directory.Exists(data)) Directory.Delete(data, true); } catch { }
        foreach (string d in Directory.GetDirectories(target, "__pycache__", SearchOption.AllDirectories))
            try { Directory.Delete(d, true); } catch { }
    }

    // 用后期绑定创建 .lnk，避免引入 Interop 程序集
    private static void MakeShortcut(string linkPath, string targetPath, string workDir, string desc)
    {
        Type t = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(t);
        object sc = t.InvokeMember("CreateShortcut",
            System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] { linkPath });
        Type st = sc.GetType();
        st.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, sc, new object[] { targetPath });
        st.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, sc, new object[] { workDir });
        st.InvokeMember("Description", System.Reflection.BindingFlags.SetProperty, null, sc, new object[] { desc });
        st.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, sc, null);
    }

    private static void CreateShortcuts()
    {
        string launcher = Path.Combine(_target, "Olivia.exe");
        foreach (string dir in new[] {
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            Path.Combine(Environment.GetEnvironmentVariable("APPDATA") ?? "", "Microsoft", "Windows", "Start Menu", "Programs")
        })
        {
            if (!Directory.Exists(dir)) continue;
            MakeShortcut(Path.Combine(dir, "Olivia 奥莉薇娅.lnk"), launcher, _target,
                "Olivia 塔罗咨询师 · 本地 Agent");
        }
    }

    private static void CreateAutostart()
    {
        string startup = Path.Combine(Environment.GetEnvironmentVariable("APPDATA") ?? "", "Microsoft", "Windows", "Start Menu", "Programs", "Startup");
        if (!Directory.Exists(startup)) return;
        MakeShortcut(Path.Combine(startup, "Olivia.lnk"), Path.Combine(_target, "Olivia.exe"),
            _target, "Olivia Agent 开机自启");
    }

    private static void StartServer()
    {
        var psi = new ProcessStartInfo(_pyw, "\"" + Path.Combine(_target, "agent", "server.py") + "\"");
        psi.WorkingDirectory = Path.Combine(_target, "agent");
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        Process.Start(psi);
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
        foreach (string dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
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
