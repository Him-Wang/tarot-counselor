# Olivia Agent · Windows 安装包生成

这个目录放的是**一键部署工具**：把本地 Agent 打包成一个自包含的 Windows 安装包。

## 生成安装包

在仓库根目录执行：

```bash
python installer/make_installer.py
```

产物：`installer/dist/Olivia-agent-setup.zip`（约 90 KB，纯标准库生成，无需 pip）。

## 安装包里有什么

解压后是一个"安装源"目录：

```
Olivia-agent-setup/
├── install.bat          # 双击安装
├── uninstall.bat        # 双击卸载
├── install.ps1 / uninstall.ps1
├── 使用说明.txt
└── payload/             # agent/ + knowledge/ + prompts/（保持兄弟目录关系）
```

## 使用者怎么装（拿到 zip 的人）

1. 解压整个 zip 到任意文件夹（不要只拖出单个文件）。
2. 双击 `install.bat`：脚本自动检测 Python 3、询问安装位置（默认 `%LOCALAPPDATA%\Olivia`）、复制文件、在桌面和开始菜单建快捷方式，并可选加入开机自启、立即启动。
3. 以后双击桌面「Olivia 奥莉薇娅」打开，浏览器访问 `http://127.0.0.1:8765`，右上角「设置」填入自己的 API key。
4. 卸载：双击安装目录里的 `uninstall.bat`（会删快捷方式、开机自启、停止服务，并按确认删除程序目录及其中的 key/记忆数据）。

**前提**：目标电脑装了 Python 3（安装时勾选 *Add Python to PATH*）。agent 本身零第三方依赖。

## 设计说明

- **不写死路径**：启动器用 `%~dp0` 相对定位，快捷方式指向安装目录，换任何电脑都能用。
- **隐私零泄漏**：打包时排除 `agent/config.json`（API key）、`agent/data/*.db`（记忆/知识库）、`__pycache__`、`*.pyc`。
- **精确停服**：server 启动时写 `agent/olivia.pid`，卸载时按 PID 精确停止，不误杀其它 Python 进程。
- **单一真相源**：安装/卸载的 PowerShell 逻辑内嵌在 `make_installer.py`，每次生成都从同一份代码写出，改一处即可。

> 如果你想要的是真正的 `.exe`/`.msi`（双击下一步下一步那种），可以在此基础上套 Inno Setup / NSIS：让安装程序先解包再执行 `install.ps1` 的等价逻辑即可。当前这个 zip 方案零外部工具、改起来最快。
