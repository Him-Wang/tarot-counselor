# Olivia Agent · Windows 一键安装

这个目录就是**安装器本体**——双击 `install.bat` 即可开始安装，不需要先生成 zip、不需要解压任何东西。

## 用法（最简单）

1. 保持本目录与仓库根目录的 `agent/`、`knowledge/`、`prompts/` 在一起（clone 下来就是这样）。
2. **双击 `install.bat`**：自动检测 Python 3，然后依次问你三个问题：
   - **安装到哪儿**（回车 = 默认 `%LOCALAPPDATA%\Olivia`）
   - **是否开机自启**（回车 = 否）
   - **安装完立即启动**（回车 = 否）
3. 装完双击桌面「Olivia 奥莉薇娅」打开，浏览器访问 `http://127.0.0.1:8765`，右上角「设置」填你自己的 API key。

> 也就是说：**双击 installer 就直接进安装流程**，但三个选择仍由你当场决定——不是全默认硬装。

## 发给别人 / 换电脑部署

如果你想把一个"自带文件、脱离仓库"的安装包发给别人：

```bash
python installer/make_installer.py
```

生成 `installer/dist/Olivia-agent-setup.zip`。对方解压后双击里面的 `install.bat`，体验完全一样（同样问那三个问题），因为 zip 里带了 `payload/`（agent + knowledge + prompts），不依赖仓库。

## 卸载

双击安装目录里的 `uninstall.bat`，全自动删除快捷方式、开机自启、服务与数据（无需确认）。

## 设计说明

- **双击即用**：`install.ps1` 会智能定位安装源——优先同目录 `payload/`（zip 分发场景），找不到就用上一级仓库根（clone 场景）。
- **不写死路径**：启动器用 `%~dp0` 相对定位；快捷方式指向安装目录；解析出真实的 `python.exe`/`pythonw.exe` 绝对路径写进 launcher。
- **隐私零泄漏**：复制后主动删除 `config.json`（API key）、`agent/data/*.db`（记忆/知识库）、`olivia.pid`、`__pycache__`。
- **精确停服**：server 启动时写 `agent/olivia.pid`，覆盖安装/卸载时按 PID 精确停止旧服务，不误杀其它 Python 进程。
- **单一真相源**：`make_installer.py` 只负责把这里的 install/uninstall 脚本连同 payload 打包成 zip；脚本本身只有这一份。

> 若需要真正的 `.exe`/`.msi`（双击下一步那种），可在此基础上套 Inno Setup / NSIS：让安装程序执行 `install.ps1` 的等价逻辑即可。当前 zip 方案零外部工具、改起来最快。
