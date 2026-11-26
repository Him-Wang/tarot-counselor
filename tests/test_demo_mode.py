# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""test_demo_mode.py — 只读演示模式自查（独立运行，无第三方依赖）。

    python tests/test_demo_mode.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.normpath(os.path.join(HERE, "..", "agent"))
if AGENT not in sys.path:
    sys.path.insert(0, AGENT)

import demo_mode  # noqa: E402

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  ok   %s" % name)
    else:
        failed += 1
        print("  FAIL %s%s" % (name, (" — " + str(detail)) if detail else ""))


def section(title):
    print("\n--- %s ---" % title)


def main():
    print("\n" + "=" * 46)
    print(" demo_mode.py 只读演示模式自查")
    print("=" * 46)

    original_env = os.environ.get(demo_mode.ENV_VAR)
    original_cli = demo_mode._CLI_ENABLED

    try:
        # ---- 1. enabled()  honor env / CLI flag ----
        section("enabled() 环境变量与 CLI 开关")
        demo_mode.set_enabled(False)
        os.environ[demo_mode.ENV_VAR] = "1"
        check("OLIVIA_DEMO=1 开启", demo_mode.enabled() is True)
        for truthy in ("true", "TRUE", "yes", "On", " 1 "):
            os.environ[demo_mode.ENV_VAR] = truthy
            check("真值 %r 开启" % truthy, demo_mode.enabled() is True)
        for falsy in ("", "0", "false", "no", "off"):
            os.environ[demo_mode.ENV_VAR] = falsy
            check("假值 %r 关闭" % falsy, demo_mode.enabled() is False)
        os.environ.pop(demo_mode.ENV_VAR, None)
        check("未设置时默认关闭", demo_mode.enabled() is False)
        demo_mode.set_enabled(True)
        check("set_enabled(True) 开启（--demo 等价）", demo_mode.enabled() is True)
        demo_mode.set_enabled(False)
        check("set_enabled(False) 关闭", demo_mode.enabled() is False)

        # ---- 2. enforce() 固定安全配置 ----
        section("enforce() 固定安全配置")
        # enforce() 只在演示模式开启时加固（这样 load_config() 可以无条件调用它，
        # 普通模式仍拿到原值）；普通模式只返回浅拷贝的行为在下面单独校验。
        os.environ[demo_mode.ENV_VAR] = "1"
        hostile = {
            "backend": "deepseek-flash",
            "protocol": "anthropic",
            "base_url": "https://attacker.example/v1",
            "api_key": "sk-real-secret-123456",
            "api_key_enc": "gAAAAA-encrypted-secret",
            "model": "claude-sonnet-4-5",
            "temperature": 0.1,
            "timeout": 999,
            "tools_enabled": False,
            "tone_enabled": False,
            "two_phase_draw": False,
            "memory_enabled": True,
            "prophecy_enabled": True,
            "occult_enabled": True,
            "safety_second_check": True,
            "language": "en",
            "max_history_messages": 5,
            "daily_token_budget": 100,
        }
        before = dict(hostile)
        safe = demo_mode.enforce(hostile)
        check("不修改传入 cfg", hostile == before)
        check("返回新 dict", safe is not hostile)
        check("去掉 api_key", safe.get("api_key") == "")
        check("去掉 api_key_enc", "api_key_enc" not in safe)
        check("base_url 为空（无法发网络请求）", safe.get("base_url") == "")
        check("model 为空", safe.get("model") == "")
        check("protocol=auto", safe.get("protocol") == "auto")
        check("backend=offline", safe.get("backend") == "offline")
        check("demo 标记为 True", safe.get("demo") is True)
        for key in ("memory_enabled", "prophecy_enabled", "occult_enabled",
                    "safety_second_check"):
            check("%s 强制关闭" % key, safe.get(key) is False)
        for key in ("tools_enabled", "tone_enabled", "two_phase_draw"):
            check("%s 强制开启" % key, safe.get(key) is True)
        check("保留非敏感偏好 language=en", safe.get("language") == "en")
        check("保留非敏感偏好 max_history_messages=5",
              safe.get("max_history_messages") == 5)
        empty = demo_mode.enforce()
        check("enforce(None) 不抛错且安全", empty["api_key"] == ""
              and empty["memory_enabled"] is False)
        os.environ.pop(demo_mode.ENV_VAR, None)
        normal = demo_mode.enforce(hostile)
        check("普通模式 enforce 保留原配置（可无条件接入 load_config）",
              normal == hostile and normal is not hostile)

        # ---- 3. guard_write / should_persist / reset ----
        section("写入守卫与状态重置")
        os.environ[demo_mode.ENV_VAR] = "1"
        demo_mode.set_enabled(False)
        try:
            demo_mode.guard_write("api/archive")
            check("演示模式 guard_write 拒绝写入", False)
        except demo_mode.DemoReadOnly:
            check("演示模式 guard_write 拒绝写入", True)
        check("演示模式 should_persist() 为 False",
              demo_mode.should_persist() is False)
        os.environ.pop(demo_mode.ENV_VAR, None)
        check("普通模式 guard_write 放行", demo_mode.guard_write("test") is True)
        check("普通模式 should_persist() 为 True",
              demo_mode.should_persist() is True)

        state = {"s1": {"result": "x"}}
        other = {"s2": 1}
        check("reset_in_memory_state 清空所有传入 dict",
              demo_mode.reset_in_memory_state(state, other, "not-a-dict") == 2
              and not state and not other)

        # ---- 4. public_config() 形状 ----
        section("public_config() 输出形状")
        demo_mode.set_enabled(True)
        cfg = demo_mode.public_config()
        check("形状键齐全",
              set(cfg) == {"demo", "notice", "restrictions", "reset"}, sorted(cfg))
        check("demo: true", cfg["demo"] is True)
        check("notice 非空（含中文说明）",
              isinstance(cfg["notice"], str) and len(cfg["notice"]) > 10)
        check("restrictions 六项全为 True（不可用）",
              set(cfg["restrictions"]) == {
                  "model_calls", "persistence", "memory", "occult",
                  "prophecy", "safety_second_check",
              } and all(cfg["restrictions"].values()), cfg["restrictions"])
        check("reset=every_request", cfg["reset"] == "every_request")
        check("不含任何密钥字段",
              "api_key" not in str(cfg) and "secret" not in str(cfg).lower())
        demo_mode.set_enabled(False)
        off = demo_mode.public_config()
        check("普通模式 demo: false / notice 空 / reset None",
              off["demo"] is False and off["notice"] == ""
              and off["reset"] is None
              and not any(off["restrictions"].values()))
        check("startup_notice 在普通模式为空", demo_mode.startup_notice() == "")
        demo_mode.set_enabled(True)
        check("startup_notice 在演示模式有提示",
              "[DEMO]" in demo_mode.startup_notice())
    finally:
        demo_mode.set_enabled(original_cli)
        if original_env is None:
            os.environ.pop(demo_mode.ENV_VAR, None)
        else:
            os.environ[demo_mode.ENV_VAR] = original_env

    print("\n" + "=" * 46)
    print(" demo_mode 自查：%d 通过 / %d 失败" % (passed, failed))
    print("=" * 46 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
