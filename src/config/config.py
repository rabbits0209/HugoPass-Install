import os
import tempfile

# 应用信息
APP_NAME = "HugoAura"
TARGET_PROCESS_NAME = ["SeewoServiceAssistant.exe", "SeewoCore.exe", "SeewoAbility.exe"]

# 文件名
TARGET_ASAR_NAME = "app.asar"
ASAR_BACKUP_NAME = "app.asar.orig"
VERIFY_BACKUP_NAME = "Verify.json.orig"

# 目标路径模式
SWASS_PATH_PATTERN = r"C:\\Program Files (x86)\\Seewo\\SeewoService\\SeewoService_*\\SeewoServiceAssistant\\resources"

# 临时目录信息
TEMP_DIR_NAME = "Aura-Install-Temp"
TEMP_INSTALL_DIR = os.path.join(tempfile.gettempdir(), TEMP_DIR_NAME)

# HugoAura 数据路径
HUGOAURA_USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "HugoAura")
HUGOAURA_REGISTRY_KEY = r"SOFTWARE\\HugoAura"

# 进程杀死间隔
PROCESS_KILL_INTERVAL_SECONDS = 0.5

# 退出代码释义
EXIT_CODES = {
    0: "安装成功",
    1: "安装失败 (一般错误)",
    2: "权限不足, 需要管理员权限",
    3: "未找到希沃管家安装目录",
    4: "ASAR 文件解包或重新打包失败",
    5: "找不到密码校验目标 (vendor.js 不匹配, 希沃版本可能过新)",
    6: "文件系统操作失败",
    7: "参数错误",
}
