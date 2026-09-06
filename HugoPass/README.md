# HugoPass

一个**极简**的希沃管家（Seewo Hugo）管理员密码注入工具，只做两件事：

- **密码绕过（`bypass`）** —— 随便输一个非空密码就能通过管理员验证。
- **自定义密码（`customPassword`）** —— 只有你设定的密码能通过，其它密码照常报错。


---

## 工作原理

管理员密码验证发生在渲染进程，流程如下：

```
用户输入密码 → handleConfirm 发送 IPC "adminPasswordValidation"
            → 主进程校验 → 回复 "adminPasswordValidationResult"（action 码）
            → handleListenPasswordValidation 按 action 分发：
                H = passwordSuccess → handleSuccess()（解锁）
                G = passwordFail    → 显示「密码错误」并清空输入
                W = requestLimit    → 限流提示
                J = requestError    → 请求出错
```

本项目只把 `case G:` 这一句替换掉：

| 模式 | 替换后 `case G:` 行为 |
|------|----------------------|
| `bypass` | 直接 `a.handleSuccess()`，任意密码解锁 |
| `customPassword` | `String(a.state.password) === 你设定的密码 ? a.handleSuccess() : 原失败逻辑` |

---

## 目录结构

```
HugoPass/
├── config.json       # 配置（模式、自定义密码、asar 路径）
├── inject.js         # 入口：解包 → 补丁 → 重新打包 → 更新 Verify.json
├── test.js           # 自检（无外部依赖）
├── lib/
│   ├── asar.js       # 无依赖的 asar 解包 / 打包
│   ├── patch.js      # vendor.js 的 case G: 补丁逻辑
│   └── verify.js     # Verify.json 完整性清单（CRC32）更新
└── build/            # 输出目录（自动生成，已在 .gitignore 中）
```

---

## 使用方法

### 1. 修改配置 `config.json`

```json
{
  "enabled": true,
  "mode": "bypass",          // "bypass" 或 "customPassword"
  "customPassword": "123456", // 仅 mode 为 customPassword 时生效
  "asarPath": ""             // 留空则自动查找已安装的希沃管家
}
```

### 2. 运行

```bash
node inject.js                        # 输出到 build/app.asar
node inject.js --install              # 直接覆盖原 app.asar（保留 .orig 备份）
node inject.js D:\path\to\app.asar    # 手动指定 asar 路径
```

脚本会自动在 `C:\Program Files (x86)\Seewo\SeewoService\SeewoService_*` 下寻找最新版本的 `SeewoServiceAssistant\app.asar`；找不到时用命令行参数或 `asarPath` 指定。

### 3. 部署

希沃管家的主程序位于（新版在 `resources` 子目录下）：

```
C:\Program Files (x86)\Seewo\SeewoService\SeewoService_<版本>\SeewoServiceAssistant\resources\app.asar
```

> 旧版本可能直接位于 `SeewoServiceAssistant\app.asar`，`inject.js` 会自动识别两种位置。

- 用 `--install` 直接替换（会自动备份原文件为 `app.asar.orig`），或手动把 `build/app.asar` 覆盖过去。
- 替换前先结束 `SeewoServiceAssistant.exe` 进程。
- 恢复：把 `app.asar.orig` 改回 `app.asar` 即可。
- 只替换 `app.asar` 本身，`resources\addons`、`resources\assets`、`_extraResources` 等兄弟目录无需改动。

### 4. 完整性校验（Verify.json）

希沃的启动器会用 `SeewoServiceAssistant\Verify.json` 里的 CRC32 校验 `resources/app.asar`。替换 asar 后若不更新该清单，启动器可能拒绝启动或自动还原原文件。

`--install` 会**自动**：

1. 计算新 `app.asar` 的 CRC32；
2. 更新 `Verify.json` 中 `resources/app.asar` 对应的 `file_crc32` 与 `file_crc32_hex`；
3. 更新前备份 `Verify.json` 为 `Verify.json.orig`。

手动部署时，`inject.js`（不带 `--install`）会在结束时打印新 CRC32，并提示同步修改 `Verify.json`。

---

## 配置说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | `boolean` | 总开关，`false` 时不产生任何改动 |
| `mode` | `string` | `"bypass"`（密码绕过）或 `"customPassword"`（自定义密码） |
| `customPassword` | `string` | 自定义密码明文，仅 `customPassword` 模式使用 |
| `asarPath` | `string` | 手动指定 app.asar 路径；留空则自动查找 |

---

## 已验证版本

- 希沃管家（Seewo Hugo）**v1.5.8**（`package.json` 内 `version` 字段）。

Seewo 更新后如果 `case G:` 的文本变了，`inject.js` 会明确报错：

```
Patch target not found in vendor.js. This Seewo Hugo version is probably newer ...
```

此时打开 `lib/patch.js`，把 `TARGET` 常量更新为新版本里对应的 `case G:...break;` 原文即可。

---

## 免责声明

本项目仅用于研究或教育目的，请勿将其用于可能违反当地法律、侵犯著作权或其它软件 EULA 的用途。若将本项目用于非法用途，一切后果由使用者自行承担。
