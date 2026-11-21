package com.olivia.tarot;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.text.InputType;
import android.util.Base64;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.JsPromptResult;
import android.webkit.JsResult;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.Locale;

/**
 * Olivia 的安卓外壳：一层 WebView，指向本机的 Olivia 服务。
 *
 * 服务跑在电脑上（python server.py，默认 8765），手机只是显示与输入。
 * 模拟器里电脑的地址是 10.0.2.2；真机上填电脑在局域网里的 IP。
 */
public class MainActivity extends Activity {

    private static final String PREF = "olivia";
    private static final String KEY_URL = "server_url";
    private static final String DEFAULT_URL = "http://10.0.2.2:8765";

    private WebView web;
    private FrameLayout root;
    private LinearLayout errView;
    private TextView errDetail;
    private EditText urlInput;
    private SharedPreferences prefs;
    private TextToSpeech tts;
    private boolean ttsReady;
    private int speakGen;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences(PREF, Context.MODE_PRIVATE);
        // adb 调试用：am start -e url http://… 可以把服务地址临时改掉并记住
        String override = getIntent() == null ? null : getIntent().getStringExtra("url");
        if (override != null && !override.trim().isEmpty()) {
            prefs.edit().putString(KEY_URL, override.trim()).apply();
        }

        // 允许 chrome://inspect 连进来调试页面（仅本机 adb 转发可达）
        if (Build.VERSION.SDK_INT >= 19) WebView.setWebContentsDebuggingEnabled(true);

        root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(243, 245, 250));

        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(243, 245, 250));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);
        s.setLoadWithOverviewMode(false);
        s.setUseWideViewPort(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        // 安卓 WebView 没有 Web Speech API：页面「朗读」按钮走这里的原生 TTS
        web.addJavascriptInterface(new TtsBridge(), "OliviaNative");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView v, String url) {
                hideError();
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                if (req != null && req.isForMainFrame()) {
                    showError(String.valueOf(err.getDescription()));
                }
            }

            @SuppressWarnings("deprecation")
            @Override
            public void onReceivedError(WebView v, int code, String desc, String failingUrl) {
                showError(desc);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                String scheme = u.getScheme() == null ? "" : u.getScheme();
                if (scheme.equals("http") || scheme.equals("https")) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) {}
                return true;
            }
        });

        // 页面里用了 alert / confirm（补牌、每日一牌都要弹），没有这个就什么都不弹
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onJsAlert(WebView v, String url, String msg, final JsResult r) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(msg)
                        .setPositiveButton("好", (d, w) -> r.confirm())
                        .setOnCancelListener(d -> r.cancel())
                        .show();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView v, String url, String msg, final JsResult r) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(msg)
                        .setPositiveButton("确定", (d, w) -> r.confirm())
                        .setNegativeButton("取消", (d, w) -> r.cancel())
                        .setOnCancelListener(d -> r.cancel())
                        .show();
                return true;
            }

            @Override
            public boolean onJsPrompt(WebView v, String url, String msg, String def,
                                      final JsPromptResult r) {
                final EditText et = new EditText(MainActivity.this);
                et.setText(def == null ? "" : def);
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(msg)
                        .setView(et)
                        .setPositiveButton("确定", (d, w) -> r.confirm(et.getText().toString()))
                        .setNegativeButton("取消", (d, w) -> r.cancel())
                        .setOnCancelListener(d -> r.cancel())
                        .show();
                return true;
            }
        });

        // 「存这次解读 / 分享图」是 canvas.toDataURL 的 data: 链接，WebView 自己不会存，这里接住
        web.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String ua, String cd, String mime, long len) {
                if (url != null && url.startsWith("data:")) saveDataUrl(url);
                else toast("这个链接没法在 App 里直接下载：" + url);
            }
        });

        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(buildErrorView(), new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        load(prefs.getString(KEY_URL, DEFAULT_URL));
    }

    private View buildErrorView() {
        errView = new LinearLayout(this);
        errView.setOrientation(LinearLayout.VERTICAL);
        errView.setGravity(Gravity.CENTER_VERTICAL);
        errView.setBackgroundColor(Color.rgb(243, 245, 250));
        int pad = dp(24);
        errView.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("连不上 Olivia");
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        title.setTextColor(Color.rgb(90, 72, 130));
        errView.addView(title);

        TextView hint = new TextView(this);
        hint.setText("Olivia 的服务跑在电脑上。先在电脑上启动它：\n\n"
                + "    python server.py\n\n"
                + "然后在下面填电脑的地址。模拟器用 10.0.2.2，真机填电脑的局域网 IP（例如 192.168.1.5）。");
        hint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f);
        hint.setTextColor(Color.rgb(110, 106, 124));
        hint.setPadding(0, dp(12), 0, dp(6));
        errView.addView(hint);

        urlInput = new EditText(this);
        urlInput.setSingleLine(true);
        urlInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        urlInput.setHint("http://10.0.2.2:8765");
        urlInput.setText(prefs.getString(KEY_URL, DEFAULT_URL));
        urlInput.setImeOptions(EditorInfo.IME_ACTION_GO);
        errView.addView(urlInput, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        errDetail = new TextView(this);
        errDetail.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        errDetail.setTextColor(Color.rgb(150, 110, 120));
        errDetail.setPadding(0, dp(8), 0, dp(8));
        errView.addView(errDetail);

        Button go = new Button(this);
        go.setText("连接");
        go.setOnClickListener(v -> {
            String u = urlInput.getText().toString().trim();
            if (u.isEmpty()) u = DEFAULT_URL;
            if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://" + u;
            prefs.edit().putString(KEY_URL, u).apply();
            hideError();
            load(u);
        });
        errView.addView(go);

        Button reset = new Button(this);
        reset.setText("用模拟器默认地址");
        reset.setOnClickListener(v -> {
            prefs.edit().putString(KEY_URL, DEFAULT_URL).apply();
            urlInput.setText(DEFAULT_URL);
            hideError();
            load(DEFAULT_URL);
        });
        errView.addView(reset);

        urlInput.setOnEditorActionListener((v, actionId, ev) -> {
            if (actionId == EditorInfo.IME_ACTION_GO) { go.performClick(); return true; }
            return false;
        });

        ScrollView sc = new ScrollView(this);
        sc.addView(errView);
        errView.setVisibility(View.GONE);
        return sc;
    }

    private void load(String url) {
        web.loadUrl(url);
    }

    /** 暴露给页面的原生语音：window.OliviaNative.speak(text) / .stop() */
    private class TtsBridge {
        @JavascriptInterface
        public void speak(final String text) {
            if (text == null || text.trim().isEmpty()) return;
            runOnUiThread(() -> speakNative(text));
        }

        @JavascriptInterface
        public void stop() {
            runOnUiThread(MainActivity.this::stopNative);
        }
    }

    private void speakNative(final String text) {
        speakGen++;
        if (tts == null) {
            tts = new TextToSpeech(this, status -> {
                ttsReady = status == TextToSpeech.SUCCESS;
                if (!ttsReady) {
                    toast("这台设备没有可用的语音引擎");
                    stopNative();
                    return;
                }
                int lang = tts.setLanguage(Locale.SIMPLIFIED_CHINESE);
                if (lang == TextToSpeech.LANG_MISSING_DATA || lang == TextToSpeech.LANG_NOT_SUPPORTED) {
                    toast("语音引擎没有中文发音，朗读不可用");
                    stopNative();
                    return;
                }
                tts.setSpeechRate(1.0f);
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String id) { }
                    @Override public void onDone(String id) { onSpeakFinished(); }
                    @Override public void onError(String id) { onSpeakFinished(); }
                });
                tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "olivia");
                watchSpeechEnd(speakGen, 1200);
            });
            return;
        }
        if (ttsReady) {
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "olivia");
            watchSpeechEnd(speakGen, 1200);
        }
    }

    /** 有的引擎不回调 onDone，这里兜底轮询 isSpeaking，念完复位页面按钮 */
    private void watchSpeechEnd(final int gen, long delayMs) {
        web.postDelayed(new Runnable() {
            @Override public void run() {
                if (gen != speakGen) return;
                if (tts == null) { onSpeakFinished(); return; }
                boolean speaking;
                try { speaking = tts.isSpeaking(); } catch (Exception e) { speaking = false; }
                if (!speaking) onSpeakFinished();
                else web.postDelayed(this, 700);
            }
        }, delayMs);
    }

    private void stopNative() {
        speakGen++;
        try { if (tts != null) tts.stop(); } catch (Exception ignored) { }
    }

    /** 念完让页面把按钮复位成「朗读」 */
    private void onSpeakFinished() {
        runOnUiThread(() -> {
            if (web != null) web.evaluateJavascript("window.__ttsDone && window.__ttsDone()", null);
        });
    }

    private void showError(String detail) {
        if (errView == null) return;
        if (urlInput != null && urlInput.getText().length() == 0) {
            urlInput.setText(prefs.getString(KEY_URL, DEFAULT_URL));
        }
        if (errDetail != null) {
            errDetail.setText("上次尝试：" + prefs.getString(KEY_URL, DEFAULT_URL)
                    + (detail == null || detail.isEmpty() ? "" : "\n" + detail));
        }
        errView.setVisibility(View.VISIBLE);
    }

    private void hideError() {
        if (errView != null) errView.setVisibility(View.GONE);
    }

    /** 把页面导出的 data:image/png;base64 存进相册（Pictures/Olivia）。 */
    private void saveDataUrl(String url) {
        try {
            int comma = url.indexOf(',');
            if (comma < 0) { toast("图片数据是空的"); return; }
            byte[] bytes = Base64.decode(url.substring(comma + 1), Base64.DEFAULT);
            String name = "olivia-" + System.currentTimeMillis() + ".png";
            if (Build.VERSION.SDK_INT >= 29) {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Images.Media.DISPLAY_NAME, name);
                v.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
                v.put(MediaStore.Images.Media.RELATIVE_PATH,
                        Environment.DIRECTORY_PICTURES + "/Olivia");
                Uri uri = getContentResolver()
                        .insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v);
                if (uri == null) { toast("相册写入失败"); return; }
                OutputStream os = getContentResolver().openOutputStream(uri);
                os.write(bytes);
                os.close();
                toast("已存进相册 Pictures/Olivia/" + name);
            } else {
                File dir = new File(Environment.getExternalStoragePublicDirectory(
                        Environment.DIRECTORY_PICTURES), "Olivia");
                if (!dir.exists() && !dir.mkdirs()) { toast("建目录失败：" + dir); return; }
                File f = new File(dir, name);
                FileOutputStream fo = new FileOutputStream(f);
                fo.write(bytes);
                fo.close();
                toast("已保存：" + f.getAbsolutePath());
            }
        } catch (Exception e) {
            toast("保存失败：" + e);
        }
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
    }

    private int dp(int v) {
        return Math.round(getResources().getDisplayMetrics().density * v);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent ev) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (errView != null && errView.getVisibility() == View.VISIBLE) { hideError(); return true; }
            if (web != null && web.canGoBack()) { web.goBack(); return true; }
        }
        return super.onKeyDown(keyCode, ev);
    }

    @Override
    protected void onDestroy() {
        if (tts != null) {
            try { tts.stop(); tts.shutdown(); } catch (Exception ignored) { }
            tts = null;
        }
        if (web != null) {
            root.removeView(web);
            web.destroy();
        }
        super.onDestroy();
    }
}
