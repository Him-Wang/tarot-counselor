# Olivia · 安卓客户端

一个**不重新实现任何逻辑**的 WebView 薄客户端：Olivia 仍然跑在你的电脑上，手机只是个窗口。
牌义、记忆、定时任务、离线整理都只有一份，改 `agent/` 一处两边都更新。

```
android/
├── AndroidManifest.xml            # package com.olivia.tarot，minSdk 24 / targetSdk 34
├── build.ps1                      # 一条命令出签名 APK（aapt2 + d8 + apksigner，不用 Gradle）
├── src/com/olivia/tarot/
│   └── MainActivity.java          # WebView / TTS 桥 / 相册下载 / 换地址 / 错误页
├── res/values/strings.xml         # app_name
├── res/mipmap-*/ic_launcher.png   # 图标（5 档）
└── tools/merge_dex.py             # 把 classes.dex 塞进 aapt2 出的 base APK
```

## 装之前

App 里没有模型、没有牌、没有数据——**先把电脑上的 Olivia 跑起来**：

```powershell
cd agent
$env:AGENT_HOST = "0.0.0.0"   # 让同一 Wi-Fi 下的手机能访问；默认只监听 127.0.0.1
python server.py              # 端口默认 8765，可 AGENT_PORT=xxxx 改
```

手机和电脑连同一个 Wi-Fi，然后在 App 的错误页里填 `http://<电脑的内网 IP>:8765`。

> 开放到 `0.0.0.0` 等于把她的记忆和对话暴露给同网段所有人，用完改回默认即可。
> Windows 首次运行会弹防火墙提示，选「专用网络」放行。

## 手机上能做的事

| 操作 | 说明 |
|---|---|
| 抽牌 / 解读 / 补牌 | 与网页版完全一致（同一份 `index.html`） |
| 停止生成 | 流式输出中点「停止」，已生成的部分保留 |
| 双击牌面 / 点「看大图」 | 全屏看牌，逆位会转 180° |
| 「存这次解读」 | 生成一张 1080 宽的解读图，落到相册 `Pictures/Olivia/` |
| 「朗读」 | 走**系统 TTS**（安卓 WebView 不实现 Web Speech），同一按钮点了变「停止朗读」 |
| 关怀面板 → 每日一牌 | 到点本地抽一张写进收件箱，不调模型、没 key 也能用 |
| 返回键 | 有错误页先关错误页，否则页内后退；已在首页则退出 |

## 自己出包

不需要 Android Studio，也不需要 Gradle。只要有 **JDK 17** 和 **Android SDK**（`platforms/android-34` + `build-tools/34.0.0`）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File android\build.ps1 `
  -SdkRoot "C:\path\to\android\sdk"
# 产物：android\build\Olivia-release.apk
```

脚本做四件事：`javac` 编 Java → `d8` 转 dex → `aapt2` 打包资源与清单 → `zipalign` + `apksigner` 签名并验签。

### 签名

默认读 `android/keystore/olivia-release.jks`（别名 `olivia`，示例口令 `olivia-tarot`）。
**这块密钥只用于本仓库的自测包，自己发布请换一把**：

```powershell
keytool -genkeypair -v -keystore my-olivia.jks -alias myolivia `
  -keyalg RSA -keysize 2048 -validity 10000 `
  -storepass <你的口令> -dname "CN=Olivia"
```

再用参数指过去：`-Keystore my-olivia.jks -StorePass <你的口令> -KeyAlias myolivia`。
换了密钥的包不能覆盖安装旧包，先卸载。

## 装到手机 / 模拟器

```powershell
adb install -r android\build\Olivia-release.apk
adb shell am start -n com.olivia.tarot/.MainActivity
```

- **真机**：手机和电脑同 Wi-Fi，App 里填电脑内网 IP；连不上会在 App 内显示错误页直接改地址。
- **模拟器**：默认地址是 `http://10.0.2.2:8765`（也就是模拟器里的宿主机）。
  如果模拟器 NAT 不稳（页面卡在半截、牌图偶发加载失败），改用 adb 反向代理更可靠：

  ```powershell
  adb reverse tcp:8765 tcp:8765
  adb shell am start -n com.olivia.tarot/.MainActivity -e url "http://127.0.0.1:8765"
  ```

  `-e url` 会把地址写进 SharedPreferences 记住，下次直接打开也在。

## 调试

- `WebView.setWebContentsDebuggingEnabled(true)` 已开，Chrome 打开 `chrome://inspect` 就能看到页面。
- 命令行可用 CDP：`adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>`
  （`pid` 用 `adb shell pidof com.olivia.tarot` 取），然后 `http://127.0.0.1:9222/json`。
- 抓图：`adb shell screencap -p /sdcard/s.png` 再 `adb pull`；**不要用** `adb exec-out screencap -p > file`，PowerShell 会把换行改坏导致 PNG 失效。

## 已知边界

- 只在 Android 14（x86_64 模拟器、Pixel 6 尺寸）上实测过；minSdk 24，更低版本没测。
- 系统 TTS 若有中文语音包才发声；没有会提示「语音引擎没有中文发音，朗读不可用」。
  模拟器常见情况是只装了联网发音人（`cmn-cn-x-ssa-*`），没网就不出声，但按钮仍会自己复位。
- 页面「分享图 / 存这次解读」都走 `data:` URL + `DownloadListener` 落盘，不经过系统下载管理器，
  所以桌面上不会留下载通知，文件直接在相册里。
