# HugoPass-Install

希沃管家（Seewo Hugo）管理员密码绕过安装器

> [!TIP]
>
> 感谢 [@Vistaminc](https://github.com/Vistaminc) 的贡献, 目前 HugoPass-Install 已支持 GUI 图形化界面安装!

## 简介

这是一个完全**离线**的希沃管家（Seewo Hugo）管理员密码绕过工具。它采用 [HugoPass]的「解包 `app.asar` → 补丁 `public/vendor.js` → 重新打包 → 更新 `Verify.json`」逻辑，实现**任意非空密码即可通过管理员验证**。

- **零云端下载**：运行时完全离线。
- **零 Node.js 依赖**：HugoPass 逻辑已移植为纯 Python（仅 stdlib），并内置进 EXE。
- **幂等**：重复安装/卸载可安全执行，原始 `app.asar` 备份为 `app.asar.orig`。

## 工作原理

管理员密码验证发生在渲染进程的 `public/vendor.js`：

```
用户输入密码 → handleConfirm 发送 IPC "adminPasswordValidation"
            → 主进程校验 → 回复 action 码
            → handleListenPasswordValidation 按 action 分发:
                H = passwordSuccess → handleSuccess()（解锁）
                G = passwordFail    → 显示「密码错误」并清空输入
```

本工具只把 `case G:` 这一句替换为 `case G:a.handleSuccess();break;`，任意密码直接解锁。

## 使用方法

### 基本用法

1. 下载最新的 [Release](https://github.com/HugoPass/HugoPass-Install/releases) EXE 包
2. 以管理员身份运行 `PassInstaller.exe`
3. 选择希沃管家安装目录（通常可自动找到），点击安装

### 命令行参数

```
usage: PassInstaller.exe [--cli] [-h] [-d DIR] [-y] [--dry-run] [--list-exit-codes]

options:
  --cli                 以 CLI (无 GUI) 模式启动
  -h, --help            显示帮助信息并退出
  -d DIR, --dir DIR     指定希沃管家安装目录
  -y, --yes             非交互模式, 自动确认所有操作
  --dry-run             不进行实际安装操作, 仅执行解包 / 打包流程
  --list-exit-codes     显示所有退出代码及其释义
```

### 非交互式安装示例

```bash
# 自动查找安装目录并安装
PassInstaller.exe --cli -y

# 指定安装目录
PassInstaller.exe --cli -d "C:\Program Files (x86)\Seewo\SeewoService\SeewoService_1.5.8\SeewoServiceAssistant\resources" -y

# 演练 (仅解包 / 打包, 不真正替换文件)
PassInstaller.exe --cli --dry-run
```

### 退出代码释义

安装程序会根据不同的情况返回以下退出代码：

```
0: 安装成功
1: 安装失败 (一般错误)
2: 权限不足, 需要管理员权限
3: 未找到希沃管家安装目录
4: ASAR 文件解包或重新打包失败
5: 找不到密码校验目标 (vendor.js 不匹配, 希沃版本可能过新)
6: 文件系统操作失败
7: 参数错误
```

您可以通过检查退出代码来判断安装是否成功以及失败的原因。

## 注意事项

1. 安装前，安装器会自动尝试卸载希沃的文件系统过滤驱动 (`SeewoKeLiteLady`) 并结束相关进程。
2. 安装后若需恢复，运行卸载流程：从 `app.asar.orig` 还原原始 `app.asar`，并还原 `Verify.json.orig`。
3. 已验证希沃管家（Seewo Hugo）**v1.5.8**；若希沃更新后 `case G:` 文本变化，安装器会明确报错（退出代码 5），需更新 `src/utils/hugoPass.py` 中的 `HUGOPASS_TARGET` 常量。

## 面向开发者

### 预先准备

- [Poetry](https://python-poetry.org/)（或直接使用 `requirements.txt`）
- Python 3.13.X

### 构建方法

1. 创建 venv & 安装依赖：`poetry install`（或 `pip install -r requirements.txt`）
2. 进入 venv: `poetry shell`（或激活 venv）
3. 运行构建脚本：`scripts\build.bat`，产物为 `dist\PassInstaller.exe`


### 贡献代码

欢迎提交 Issues 和 Pull Request!