# -*- coding: utf-8 -*-
"""
HugoPass 纯 Python 移植的自检脚本 (镜像 HugoPass/test.js 的断言)。

运行: python tests/test_hugopass.py

不依赖外部包: 用一个最小的 loguru 垫片让 utils.hugoPass 可导入,
以便在本机没有安装 loguru 时也能直接验证移植逻辑。
"""

import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

# 最小 loguru 垫片 (仅用于让 utils.hugoPass 的 `from loguru import logger` 通过)
class _Shim:
    def _noop(self, *a, **k):
        pass

    info = warning = error = debug = critical = success = exception = _noop
    remove = add = _noop


if "loguru" not in sys.modules:
    _loguru = types.ModuleType("loguru")
    _loguru.logger = _Shim()
    sys.modules["loguru"] = _loguru

from utils import hugoPass  # noqa: E402

failures = 0


def check(name, fn):
    global failures
    try:
        fn()
        print(f"  ok  {name}")
    except Exception as e:
        failures += 1
        print(f"FAIL  {name}\n      {e}")


def test_roundtrip():
    tmp = Path(tempfile.mkdtemp(prefix="hugopass-"))
    src = tmp / "src"
    (src / "public").mkdir(parents=True)
    (src / "emptyDir").mkdir(parents=True)
    (src / "main.js").write_text("console.log('hi');", encoding="utf-8")
    (src / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    (src / "public" / "vendor.js").write_text("中文 密码错误 content", encoding="utf-8")

    buf = hugoPass.pack_asar(src)
    asar_path = tmp / "out.asar"
    asar_path.write_bytes(buf)

    out = tmp / "out"
    count = hugoPass.extract_asar(asar_path, out)

    assert count == 3, f"expected 3 files, got {count}"
    assert (out / "main.js").read_text(encoding="utf-8") == "console.log('hi');"
    assert (out / "public" / "vendor.js").read_text(encoding="utf-8") == "中文 密码错误 content"
    assert (out / "emptyDir").is_dir(), "empty dir should be kept"
    shutil.rmtree(tmp)


def test_patch_bypass():
    fake = "var x=1;\n" + hugoPass.HUGOPASS_TARGET + "\nvar y=2;"
    patched = hugoPass.patch_vendor_js(fake)
    assert "case G:a.handleSuccess();break;" in patched
    assert hugoPass.HUGOPASS_TARGET not in patched


def test_patch_missing_target():
    try:
        hugoPass.patch_vendor_js("var x=1;")
        raise AssertionError("should have raised HugoPassPatchError")
    except hugoPass.HugoPassPatchError:
        pass


def test_crc():
    assert hugoPass.crc32_of(b"123456789") == 3421780262
    assert hugoPass.crc32_hex_le(3421780262) == "2639f4cb"
    assert hugoPass.crc32_hex_le(2787933164) == "ec7b2ca6"


def test_update_verify_json():
    tmp = Path(tempfile.mkdtemp(prefix="hugopass-verify-"))
    assistant = tmp / "SeewoServiceAssistant"
    (assistant / "resources").mkdir(parents=True)

    asar_path = assistant / "resources" / "app.asar"
    asar_path.write_bytes(b"fake asar")

    verify_path = assistant / "Verify.json"
    verify_path.write_text(
        json.dumps(
            [
                {"file_crc32": 2787933164, "file_crc32_hex": "ec7b2ca6", "file_path": "resources/app.asar"},
                {"file_crc32": 123, "file_crc32_hex": "0000007b", "file_path": "other.dll"},
            ],
            indent=3,
        ),
        encoding="utf-8",
    )

    updated = hugoPass.update_verify_json(str(asar_path), 1527680550)
    assert updated is True

    lst = json.loads(verify_path.read_text(encoding="utf-8"))
    entry = next(e for e in lst if e["file_path"] == "resources/app.asar")
    assert entry["file_crc32"] == 1527680550
    assert entry["file_crc32_hex"] == "268e0e5b"
    assert next(e for e in lst if e["file_path"] == "other.dll")["file_crc32"] == 123
    assert verify_path.with_name("Verify.json.orig").exists(), "Verify.json backup should exist"
    shutil.rmtree(tmp)


def test_real_sample():
    # build/app.asar 是 HugoPass(inject.js) 的**输出**(已 patch 的 app.asar),
    # 不是原始未打补丁的 app.asar。因此这里做两件事:
    #   1) 用本移植的 extract_asar 解包真实大样本, 确认 public/vendor.js 存在
    #      且已含 bypass 替换串 (证明 extract 与替换串逐字节一致);
    #   2) 解包后再 pack_asar, 与原始 build/app.asar 逐字节比较 (证明 pack 与
    #      Node asar.js 的 JSON.stringify 1:1 一致)。
    real = Path(__file__).resolve().parents[1] / "HugoPass" / "build" / "app.asar"
    if not real.exists():
        print("  --  skip real sample (no HugoPass/build/app.asar)")
        return
    tmp = Path(tempfile.mkdtemp(prefix="hugopass-real-"))
    extract_dir = tmp / "extracted"
    count = hugoPass.extract_asar(real, extract_dir)
    assert count > 0, "extract_asar returned 0 files on real sample"

    vendor = (extract_dir / "public" / "vendor.js").read_text(encoding="utf-8")
    assert "case G:a.handleSuccess();break;" in vendor, "bypass already applied"
    assert hugoPass.HUGOPASS_TARGET not in vendor, "TARGET should already be gone"

    repacked = hugoPass.pack_asar(extract_dir)
    assert repacked == real.read_bytes(), (
        "re-packed bytes differ from HugoPass build/app.asar; "
        "pack_asar is not byte-identical to Node asar.js"
    )
    shutil.rmtree(tmp)


if __name__ == "__main__":
    print("utils.hugoPass 自检")
    check("pack -> extract 往返 (含中文/空目录)", test_roundtrip)
    check("patch bypass 注入", test_patch_bypass)
    check("缺失目标抛错", test_patch_missing_target)
    check("crc32 测试向量", test_crc)
    check("update_verify_json 更新条目 + .orig 备份", test_update_verify_json)
    check("真实样本 inject_hugopass", test_real_sample)
    print("\nAll tests passed." if failures == 0 else f"\n{failures} test(s) failed.")
    sys.exit(0 if failures == 0 else 1)
