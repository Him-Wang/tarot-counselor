# Olivia 奥莉薇娅 · Windows 一键安装器

一个自包含的 `Olivia-setup.exe`：双击即装，无需 Python 安装包以外的任何东西，也不需要 `.bat` / `.ps1` / `pip` / 解压工具。

## 使用者：双击即装

1. 从 Release 下载 `Olivia-setup.exe`（约 11 MB），双击。
2. 若提示未安装 Python 3，点确定打开 <https://www.python.org/downloads/>，安装时勾选 **Add Python to PATH**，装完重新双击安装器。
3. 选择安装目录（默认 `%LOCALAPPDATA%\Olivia`）。
4. 选择是否开机自启。
5. 安装器自动解压内置文件、建桌面/开始菜单快捷方式、后台启动服务并打开浏览器 <http://127.0.0.1:8765>。
6. 点右上角「设置」填入自己的 API key（DeepSeek 等）即可使用。

以后双击桌面「Olivia 奥莉薇娅」即可启动；命令行窗口不会出现，服务在后台运行。

## 开发者：重新构建安装包

环境：Windows + Python 3 + .NET Framework 4（系统自带 `csc.exe`，无需 Visual Studio / dotnet SDK）。

```bash
python installer/build.py
```

产物在 `installer/dist/`：
- `Olivia.exe` —— 启动器，后台起服务并打开浏览器。
- `payload.zip` —— 打包的 agent/knowledge/prompts/skills（自动排除 config.json / 数据库 / 缓存）。
- `Olivia-setup.exe` —— 最终单文件安装器，已内嵌上面两者。

源码：`Setup.cs`（安装器）、`Launcher.cs`（启动器）。改完 C# 源码后重新运行 `build.py` 即可。

## 卸载

在 Windows「设置 → 应用」里卸载，或删除安装目录后手动删掉桌面/开始菜单快捷方式与开机自启项。程序数据（API key、记忆、知识库）都在安装目录内，删除目录即彻底清除。

## 设计说明

- **单文件**：payload 与启动器作为 Win32 资源嵌进 setup.exe，分发只发一个文件。
- **零依赖**：C# 只用 .NET Framework 4 与 `System.IO.Compression`；服务端只用 Python 3 标准库。
- **隐私零泄漏**：打包时排除 `config.json`、`agent/data/*.db`、`olivia.pid`、`__pycache__`，安装后再兜底清理一次。
- **无黑窗口**：服务由 `pythonw.exe` 后台启动，快捷方式直接指向原生 `Olivia.exe`。
