"""
HugoPass 的纯 Python 移植 (仅 stdlib, 无 Node 依赖)

将 HugoPass/ 目录下的 lib/asar.js、lib/patch.js、lib/verify.js 1:1 移植到
Python, 用于在希沃管家 (Seewo Hugo) 的 app.asar 中注入「管理员密码绕过」补丁。

原理 (与 HugoPass 完全一致):
    app.asar 是 Electron 的 asar 归档, 布局为:
        [uint32 magic = 0x04]
        [uint32 size          = 8 + stringLen]
        [uint32 payloadSize   = 4 + stringLen]
        [uint32 stringLen]
        [JSON header: { "files": <tree> }]
        [拼接的文件内容]
    每个文件条目为 { size, offset }, 目录条目为 { files: {...} }。
    文件字节位于 (16 + stringLen + offset)。

    密码校验发生在渲染进程的 public/vendor.js:
        case H: passwordSuccess -> handleSuccess()
        case G: passwordFail    -> 显示「密码错误」并清空输入
        case W: requestLimit    -> 限流提示
        case J: requestError    -> 请求出错
    本模块只把 `case G:` 这一句替换为直接 `a.handleSuccess()`, 实现任意密码绕过。
"""

import json
import os
import shutil
import struct
import zlib
from pathlib import Path

from loguru import logger as log

# 与 HugoPass/lib/patch.js 的 TARGET 逐字一致 (v1.5.8)。
# 注意: 该字符串包含中文「密码错误」, 读写 vendor.js 时必须显式使用 UTF-8。
HUGOPASS_TARGET = (
    'case G:w.a.send("passwordInputLockError",{name:q,time:10}),'
    'a.setState({isError:!0,errorText:r.message||"密码错误"}),'
    'a.timeout=setTimeout(function(){a.sendMessageLock=!1,'
    'a.setState({password:"",isError:!1,errorText:""})},1e3);break;'
)

HUGOPASS_BYPASS_REPLACEMENT = "case G:a.handleSuccess();break;"


class HugoPassPatchError(Exception):
    """vendor.js 中找不到补丁目标时抛出 (希沃版本可能过新)。"""


def extract_asar(asar_path, dest_dir):
    """移植 lib/asar.js 的 extract。解包 asar 到 dest_dir, 保留空目录。

    返回写出的文件数。
    """
    asar_path = str(asar_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(asar_path, "rb") as f:
        head = f.read(8)
        size = struct.unpack_from("<I", head, 4)[0]

        header_buf = f.read(size)
        string_len = struct.unpack_from("<I", header_buf, 4)[0]
        json_bytes = header_buf[8 : 8 + string_len]
        header = json.loads(json_bytes.decode("utf-8"))

        data_start = 16 + string_len

        def walk(node, rel_dir):
            nonlocal count
            for name, entry in node.items():
                out_path = dest_dir / rel_dir / name
                if "files" in entry:
                    out_path.mkdir(parents=True, exist_ok=True)
                    walk(entry["files"], rel_dir / name)
                else:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    offset = int(entry["offset"])
                    f.seek(data_start + offset)
                    out_path.write_bytes(f.read(entry["size"]))
                    count += 1

        walk(header["files"], Path(""))

    return count


def pack_asar(src_dir):
    """移植 lib/asar.js 的 pack。将目录树打包为 asar 字节串。

    symlink 及其它特殊文件被有意跳过 (与 HugoPass 一致)。
    """
    src_dir = Path(src_dir)
    file_buffers = []
    offset = 0

    def build_node(rel_dir):
        nonlocal offset
        full_path = src_dir / rel_dir if rel_dir else src_dir
        entries = sorted(full_path.iterdir(), key=lambda e: e.name)

        node = {"files": {}}
        for ent in entries:
            child_rel = rel_dir / ent.name if rel_dir else Path(ent.name)
            if ent.is_dir():
                node["files"][ent.name] = build_node(child_rel)
            elif ent.is_file():
                buf = ent.read_bytes()
                node["files"][ent.name] = {"size": len(buf), "offset": str(offset)}
                file_buffers.append(buf)
                offset += len(buf)
            # symlinks 等特殊文件跳过。
        return node

    header = {"files": build_node(Path(""))["files"]}

    # 与 JS 的 JSON.stringify 逐字节一致: 无空格分隔符、不转义非 ASCII 字符。
    json_bytes = json.dumps(
        header, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    string_len = len(json_bytes)
    size = 8 + string_len
    payload_size = 4 + string_len
    data_start = 16 + string_len

    out = bytearray(data_start + offset)
    struct.pack_into("<I", out, 0, 4)
    struct.pack_into("<I", out, 4, size)
    struct.pack_into("<I", out, 8, payload_size)
    struct.pack_into("<I", out, 12, string_len)
    out[16 : 16 + string_len] = json_bytes

    pos = data_start
    for buf in file_buffers:
        out[pos : pos + len(buf)] = buf
        pos += len(buf)

    return bytes(out)


def patch_vendor_js(vendor_js):
    """移植 lib/patch.js 的 bypass 分支。

    找不到目标时抛 HugoPassPatchError。
    """
    if HUGOPASS_TARGET not in vendor_js:
        raise HugoPassPatchError(
            "Patch target not found in vendor.js. This Seewo Hugo version is "
            "probably newer than the one this tool was written for; update "
            "HUGOPASS_TARGET in utils/hugoPass.py."
        )
    return vendor_js.replace(HUGOPASS_TARGET, HUGOPASS_BYPASS_REPLACEMENT)


def crc32_of(data):
    """unsigned CRC32 (IEEE 802.3 / zlib), 十进制。"""
    return zlib.crc32(data) & 0xFFFFFFFF


def crc32_hex_le(crc):
    """CRC32 字节按小端写为 8 位 hex 字符串。"""
    return struct.pack("<I", crc).hex()


def locate_verify_json(asar_path):
    """移植 lib/verify.js 的 locateVerifyJson。

    新版布局: .../SeewoServiceAssistant/resources/app.asar -> Verify.json 在
               .../SeewoServiceAssistant/Verify.json
    旧版布局: .../SeewoServiceAssistant/app.asar -> Verify.json 在其旁边。
    """
    asar_path = Path(asar_path)
    candidates = [
        asar_path.parent.parent / "Verify.json",
        asar_path.parent / "Verify.json",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def update_verify_json(asar_path, crc):
    """更新 Verify.json 中 app.asar 对应的 CRC32 (保留 .orig 备份)。

    返回是否成功更新。
    """
    verify_path = locate_verify_json(asar_path)
    if not verify_path:
        log.warning("[HugoPass] Verify.json 未找到, 完整性清单保持不变。")
        return False

    verify_path = Path(verify_path)
    asar_rel = os.path.relpath(asar_path, verify_path.parent).replace("\\", "/")

    entry_list = json.loads(verify_path.read_text(encoding="utf-8"))

    verify_backup = verify_path.with_name(verify_path.name + ".orig")
    if not verify_backup.exists():
        shutil.copy2(str(verify_path), str(verify_backup))
        log.info(f"[HugoPass] Verify.json 已备份到 {verify_backup}")

    entry = next((e for e in entry_list if e.get("file_path") == asar_rel), None)
    if entry is None:
        entry_list.append(
            {
                "file_crc32": crc,
                "file_crc32_hex": crc32_hex_le(crc),
                "file_path": asar_rel,
            }
        )
        log.info(f"[HugoPass] Verify.json: 新增条目 {asar_rel}")
    else:
        entry["file_crc32"] = crc
        entry["file_crc32_hex"] = crc32_hex_le(crc)
        log.info(f"[HugoPass] Verify.json: 更新 {asar_rel} -> {crc32_hex_le(crc)}")

    # 与原始文件保持一致, 使用 3 空格缩进。
    verify_path.write_text(
        json.dumps(entry_list, indent=3, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return True


def inject_hugopass(app_asar_path, work_dir):
    """执行完整注入: 解包 -> patch vendor.js -> 重新打包。

    Args:
        app_asar_path: 输入 app.asar 路径 (通常是原始/备份的 app.asar)。
        work_dir: 工作目录 (解包与输出产物都放在这里)。

    Returns:
        (ok, 输出 asar 路径或 None, 新 CRC 或 None, 错误信息)。
    """
    app_asar_path = Path(app_asar_path)
    work_dir = Path(work_dir)

    try:
        if not app_asar_path.exists():
            return (False, None, None, f"app.asar 未找到: {app_asar_path}")

        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)

        extract_dir = work_dir / "extracted"
        extract_dir.mkdir(parents=True)

        file_count = extract_asar(app_asar_path, extract_dir)
        log.info(f"[HugoPass] 解包 {app_asar_path} 完成, 共 {file_count} 个文件。")

        vendor_path = extract_dir / "public" / "vendor.js"
        if not vendor_path.exists():
            return (
                False,
                None,
                None,
                "public/vendor.js 未找到, 目标可能不是希沃管家 app.asar。",
            )

        vendor_js = vendor_path.read_text(encoding="utf-8")
        patched = patch_vendor_js(vendor_js)
        vendor_path.write_text(patched, encoding="utf-8")
        log.info("[HugoPass] public/vendor.js 补丁注入成功。")

        packed = pack_asar(extract_dir)
        out_asar = work_dir / "app.asar"
        out_asar.write_bytes(packed)

        crc = crc32_of(packed)
        log.info(f"[HugoPass] 新 app.asar CRC32: {crc} ({crc32_hex_le(crc)})")
        return (True, str(out_asar), crc, "")

    except HugoPassPatchError as e:
        return (False, None, None, str(e))
    except Exception as e:
        log.exception(f"[HugoPass] 注入失败: {e}")
        return (False, None, None, f"HugoPass 注入失败: {e}")
