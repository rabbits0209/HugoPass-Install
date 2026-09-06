import os
import shutil
import subprocess
import time
import winreg
from datetime import datetime
from pathlib import Path
from loguru import logger as log
from utils import dirSearch, killer, hugoPass
from config import config


def run_installation(args, installerClassIns=None):
    """
    运行安装流程 (HugoPass 密码绕过)

    参数:
        args: 命令行参数对象, 如果提供则尝试使用非交互式方式安装
        installerClassIns: InstallerModel 实例

    返回:
        dict: {"success": bool, "errorInfo": str}
    """
    install_success = False
    error_detail = ""

    # 获取进度回调函数
    progress_callback = getattr(args, "progress_callback", None)
    status_callback = getattr(args, "status_callback", None)

    def update_status(status):
        if status_callback:
            status_callback(status)

    def update_progress(progress, step, status=None):
        if installerClassIns:
            if not installerClassIns.is_installing:
                update_status("安装已取消")
                raise Exception("INSTALLATION_CANCELLED")
        if progress_callback:
            progress_callback(progress, step, status)
        log.info(step)

    try:
        update_progress(0, "[0 / 8] 准备")
        log.info(f"即将开始运行 {config.APP_NAME} 管理工具 (HugoPass 密码绕过)")

        # [1 / 8] 查找希沃管家安装目录
        update_progress(10, "[1 / 8] 查找希沃管家安装目录")
        if args and args.dir:
            install_dir_path_str = args.dir
            if not os.path.isdir(install_dir_path_str):
                log.critical(f"指定的安装目录不存在: {install_dir_path_str}")
                error_detail = "无效的管家安装目录"
                return {"success": False, "errorInfo": error_detail}
            log.info(f"使用指定的安装目录: {install_dir_path_str}")
        else:
            install_dir_path_str = dirSearch.find_seewo_resources_dir()
            if not install_dir_path_str:
                log.critical("未能找到 SeewoServiceAssistant 安装目录")
                if args and args.yes:
                    error_detail = "未找到希沃管家安装目录"
                    return {"success": False, "errorInfo": error_detail}
                log.info("您可以尝试手动输入安装目录:")
                install_dir_path_str = input()
                if not os.path.isdir(install_dir_path_str):
                    log.critical(f"指定的目录不存在: {install_dir_path_str}")
                    error_detail = "无效的管家安装目录"
                    return {"success": False, "errorInfo": error_detail}

        install_dir_path = Path(install_dir_path_str)
        app_asar_path = install_dir_path / config.TARGET_ASAR_NAME
        backup_asar_path = install_dir_path / config.ASAR_BACKUP_NAME

        # [2 / 8] 卸载文件系统过滤驱动
        update_progress(20, "[2 / 8] 卸载文件系统过滤驱动")
        try:
            if not args.dry_run:
                creationflags = subprocess.CREATE_NO_WINDOW
                command = ["fltmc", "unload", "SeewoKeLiteLady"]
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    creationflags=creationflags,
                )
                log.info(f"卸载命令执行成功, 返回值: {result.returncode}")
                if result.stdout:
                    log.debug(f"fltmc stdout: {result.stdout.strip()}")
                if result.stderr:
                    log.warning(f"fltmc stderr: {result.stderr.strip()}")
        except FileNotFoundError:
            log.error('未能找到 "fltmc" 命令, 请确保您的系统环境完整。')
        except Exception as e:
            log.error(f"调用 fltmc 时发生未知错误: {e}")

        # [3 / 8] 结束希沃管家进程
        update_progress(30, "[3 / 8] 结束希沃管家进程")
        if not args.dry_run:
            killer.start_killing_process()
            time.sleep(2.0)

        # [4 / 8] 备份原始 app.asar
        update_progress(40, "[4 / 8] 备份原始 app.asar")
        if not app_asar_path.exists():
            error_detail = f"未找到 {app_asar_path}"
            log.critical(error_detail)
            return {"success": False, "errorInfo": error_detail}
        if not backup_asar_path.exists():
            try:
                log.info(f"创建原始 ASAR 备份: {backup_asar_path}")
                if not args.dry_run:
                    shutil.copy2(str(app_asar_path), str(backup_asar_path))
                log.success("原始 ASAR 备份创建成功")
            except Exception as e:
                error_detail = f"创建 ASAR 备份失败: {e}"
                log.critical(error_detail)
                return {"success": False, "errorInfo": error_detail}
        else:
            log.info("检测到已存在的 app.asar.orig 备份, 直接使用 (保证重复安装幂等)")

        # [5 / 8] 注入 HugoPass 补丁
        update_progress(55, "[5 / 8] 注入 HugoPass 密码绕过补丁")
        work_dir = Path(config.TEMP_INSTALL_DIR) / "hugopass"
        ok, patched_asar_path, new_crc, err = hugoPass.inject_hugopass(
            str(backup_asar_path), str(work_dir)
        )
        if not ok:
            error_detail = err
            log.critical(error_detail)
            return {"success": False, "errorInfo": error_detail}

        # [6 / 8] 替换 app.asar
        update_progress(70, "[6 / 8] 替换 app.asar")
        try:
            log.info(f"正在将 {patched_asar_path} 替换到 {app_asar_path}...")
            if not args.dry_run:
                if app_asar_path.exists():
                    os.remove(app_asar_path)
                    time.sleep(0.2)
                shutil.move(str(patched_asar_path), str(app_asar_path))
            if app_asar_path.exists() or args.dry_run:
                log.success(f"替换 {config.TARGET_ASAR_NAME} 成功。")
            else:
                error_detail = f"移动到 {app_asar_path} 失败, ASAR 文件替换未成功"
                log.critical(error_detail)
                return {"success": False, "errorInfo": error_detail}
        except Exception as e:
            error_detail = f"替换 ASAR 文件时发生错误: {e}。请检查文件系统过滤驱动已被卸载, 并确认对希沃管家目录有写入权限。"
            log.critical(error_detail)
            return {"success": False, "errorInfo": error_detail}

        # [7 / 8] 更新 Verify.json 完整性校验
        update_progress(85, "[7 / 8] 更新 Verify.json 完整性校验")
        if not args.dry_run:
            hugoPass.update_verify_json(str(app_asar_path), new_crc)

        # [8 / 8] 写入注册表
        update_progress(90, "[8 / 8] 写入版本信息和安装时间到注册表")
        try:
            if not args.dry_run:
                with winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER, config.HUGOAURA_REGISTRY_KEY
                ) as key:
                    winreg.SetValueEx(
                        key, "Version", 0, winreg.REG_SZ, "hugopass"
                    )
                    winreg.SetValueEx(
                        key, "InstallTime", 0, winreg.REG_SZ, datetime.now().isoformat()
                    )
            log.info("版本信息和安装时间已写入注册表")
        except Exception as e:
            log.warning(f"写入注册表失败: {e}")

        install_success = True
    except Exception as e:
        error_detail = e
        if installerClassIns and not installerClassIns.is_installing:
            log.warning("用户取消了安装操作")
        else:
            log.exception(f"安装过程中发生未知错误: {e}")
        install_success = False
    finally:
        if not args.dry_run:
            killer.stop_killing_process()

        temp_dir = Path(config.TEMP_INSTALL_DIR)
        if temp_dir.exists():
            try:
                if not args.dry_run:
                    shutil.rmtree(temp_dir)
                else:
                    log.info(f"临时文件夹目录: {temp_dir}")
                    log.info("可前往该目录检查 Dry Run 解包 / 打包产物")
            except OSError as e:
                log.warning(f"临时文件夹清理失败: {e}")
                log.warning("请尝试手动清理")

        if install_success:
            log.success("-----------------------------------------")
            log.success(f"{config.APP_NAME} 安装完成 (HugoPass 密码绕过)")
            log.success("-----------------------------------------")
        else:
            log.error("---------------------------------------------")
            log.error(f"{config.APP_NAME} 安装失败")
            log.error("---------------------------------------------")

        try:
            update_progress(
                100,
                f"[8 / 8] 安装{"完成" if install_success else f"出错: {error_detail}"}",
                "success" if install_success else "error",
            )
        except Exception:
            pass

    return {"success": install_success, "errorInfo": error_detail}
