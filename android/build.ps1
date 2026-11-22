# Olivia Android shell -- built with the SDK's own aapt2 / d8 / apksigner, no gradle.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# Output: build\Olivia-release.apk
param(
    [string]$SdkRoot = "",
    [string]$Keystore = "keystore\olivia-release.jks",
    [string]$StorePass = "olivia-tarot",
    [string]$KeyAlias = "olivia"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not $SdkRoot) {
    foreach ($cand in @($env:ANDROID_SDK_ROOT, $env:ANDROID_HOME, "..\..\android\sdk")) {
        if ($cand -and (Test-Path (Join-Path $cand "platforms\android-34\android.jar"))) { $SdkRoot = $cand; break }
    }
    if (-not $SdkRoot) { throw "Android SDK not found: pass -SdkRoot or set ANDROID_SDK_ROOT" }
}

$sdk  = (Resolve-Path $SdkRoot).Path
$bt   = Join-Path $sdk "build-tools\34.0.0"
$jar  = Join-Path $sdk "platforms\android-34\android.jar"
$jdk  = Join-Path $sdk "jdk\jdk-17.0.21+9"
$javac = Join-Path $jdk "bin\javac.exe"
$keytool = Join-Path $jdk "bin\keytool.exe"
$aapt2 = Join-Path $bt "aapt2.exe"
$d8    = Join-Path $bt "d8.bat"
$zip   = Join-Path $bt "zipalign.exe"
$sign  = Join-Path $bt "apksigner.bat"

foreach ($p in @($javac, $aapt2, $d8, $zip, $sign, $jar)) {
    if (-not (Test-Path $p)) { throw "missing build tool: $p" }
}

# d8.bat / apksigner.bat look for java via JAVA_HOME
$env:JAVA_HOME = $jdk
$env:PATH = (Join-Path $jdk "bin") + ";" + $env:PATH

$build = Join-Path $here "build"
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Path (Join-Path $build "classes") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $build "dex")     | Out-Null

Write-Host "[1/6] javac"
& $javac -encoding UTF-8 -source 8 -target 8 -nowarn `
    -classpath $jar -d (Join-Path $build "classes") `
    (Join-Path $here "src\com\olivia\tarot\MainActivity.java")
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

Write-Host "[2/6] d8"
$classes = @(Get-ChildItem -Recurse -Filter *.class (Join-Path $build "classes") |
    ForEach-Object { $_.FullName })
& $d8 --lib $jar --min-api 24 --output (Join-Path $build "dex") $classes
if ($LASTEXITCODE -ne 0) { throw "d8 failed" }

Write-Host "[3/6] resources"
& $aapt2 compile --dir (Join-Path $here "res") -o (Join-Path $build "res.zip")
if ($LASTEXITCODE -ne 0) { throw "aapt2 compile failed" }
& $aapt2 link -o (Join-Path $build "base.apk") -I $jar `
    --manifest (Join-Path $here "AndroidManifest.xml") `
    --min-sdk-version 24 --target-sdk-version 34 `
    --version-code 2 --version-name 1.2.0 `
    (Join-Path $build "res.zip")
if ($LASTEXITCODE -ne 0) { throw "aapt2 link failed" }

Write-Host "[4/6] merge classes.dex"
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = "py" }
& $py (Join-Path $here "tools\merge_dex.py") `
    (Join-Path $build "base.apk") `
    (Join-Path $build "dex\classes.dex") `
    (Join-Path $build "unsigned.apk")
if ($LASTEXITCODE -ne 0) { throw "merge dex failed" }

Write-Host "[5/6] zipalign"
& $zip -f -p 4 (Join-Path $build "unsigned.apk") (Join-Path $build "aligned.apk")
if ($LASTEXITCODE -ne 0) { throw "zipalign failed" }

Write-Host "[6/6] sign"
$ks = Join-Path $here $Keystore
if (-not (Test-Path $ks)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ks) | Out-Null
    Write-Host "  generating signing key: $Keystore (pass: $StorePass)"
    & $keytool -genkeypair -v -keystore $ks -alias $KeyAlias `
        -keyalg RSA -keysize 2048 -validity 10000 `
        -storepass $StorePass -keypass $StorePass `
        -dname "CN=Olivia, OU=Personal, O=Olivia, L=Shanghai, ST=Shanghai, C=CN"
    if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
}
& $sign sign --ks $ks --ks-key-alias $KeyAlias `
    --ks-pass "pass:$StorePass" --key-pass "pass:$StorePass" `
    --out (Join-Path $build "Olivia-release.apk") (Join-Path $build "aligned.apk")
if ($LASTEXITCODE -ne 0) { throw "apksigner failed" }

& $sign verify (Join-Path $build "Olivia-release.apk")
if ($LASTEXITCODE -ne 0) { throw "signature verify failed" }

$apk = Join-Path $build "Olivia-release.apk"
$kb = [math]::Round((Get-Item $apk).Length / 1KB, 1)
Write-Host ""
Write-Host "OK -> $apk  ($kb KB)"
