"""
主窗口 UI
"""

from logging import WARN
from version import __appVer__
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk_bs
from ttkbootstrap.constants import *
from tkinter.font import ITALIC
from typing import Callable, Optional
import ctypes
import os
from pathlib import Path


def _enable_high_dpi_awareness():
    """
    在 Windows 上启用高 DPI 感知, 避免高缩放比例下窗口被放大裁剪。

    需要在创建 Tk 根窗口之前调用。
    """
    try:
        if os.name != "nt":
            return

        # 优先使用 shcore 接口 (Windows 8.1+)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return
        except Exception:
            pass

        # 回退到较旧的 DPIAware 接口
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        # DPI 设置失败时静默忽略, 不影响程序其他逻辑
        pass


class MainWindow:
    """主窗口UI类"""

    def __init__(self, theme="flatly"):
        # 在创建根窗口前启用高 DPI 感知, 解决高缩放比例下窗口显示异常的问题
        _enable_high_dpi_awareness()

        # 创建根窗口
        self.root = ttk_bs.Window(themename=theme)
        self.root.title("HugoAura 安装器")

        self.geometry_info = {
            "BASELINE_HEIGHT": 400,  # 增加基准高度以确保内容完整显示
            "BASELINE_WIDTH": 400,   # 增加基准宽度以提供更好的显示效果
            "scaleFactor": ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
        }

        # 初始大小, 允许后续根据内容和屏幕大小自动调整
        self.root.geometry(
            f"{int(self.geometry_info["BASELINE_WIDTH"] * self.geometry_info["scaleFactor"])}x{int(self.geometry_info["BASELINE_HEIGHT"] * self.geometry_info["scaleFactor"])}"
        )
        self.root.tk.call("tk", "scaling", self.geometry_info["scaleFactor"] * 100 / 75)
        # 允许窗口缩放和最大化, 方便在小分辨率/高 DPI 下查看完整内容
        self.root.resizable(True, True)
        self.root.iconbitmap(
            os.path.join(
                Path(os.path.dirname(__file__)).parents[1],
                "public",
                "installer.ico",
            )
        )

        # 居中显示窗口
        self._center_window()

        # 回调函数
        self.install_callback: Optional[Callable] = None
        self.uninstall_callback: Optional[Callable] = None
        self.cancel_callback: Optional[Callable] = None

        # 控件变量
        self.install_directory_var = tk.StringVar()
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value="就绪")
        self.step_var = tk.StringVar()

        # 创建界面
        self._create_widgets()

        # 初始状态
        self.is_installing = False

    def _center_window(self):
        """窗口居中显示"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = int((self.root.winfo_screenwidth() // 2) - (width // 2))
        y = int((self.root.winfo_screenheight() // 2) - (height // 1.5))
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _on_scrollable_frame_configure(self, event):
        """
        当内部内容尺寸变化时, 更新画布的滚动区域, 并自适应宽度。
        """
        if not hasattr(self, "_canvas") or not hasattr(self, "_canvas_window"):
            return

        canvas = self._canvas
        # 更新滚动区域
        canvas.configure(scrollregion=canvas.bbox("all"))

        # 更新内容居中位置
        self._update_content_center()

    def _on_canvas_configure(self, event):
        """当画布大小变化时, 更新内容居中位置和滚动区域"""
        if not hasattr(self, "_canvas") or not hasattr(self, "_canvas_window"):
            return

        canvas = self._canvas
        # 更新滚动区域
        canvas.configure(scrollregion=canvas.bbox("all"))

        # 更新内容居中位置
        self._update_content_center()

    def _update_content_center(self):
        """
        更新内容在画布中的水平居中位置，确保垂直位置始终从顶部开始
        修复窗口最大化/还原时内容飘到视口外的：Canvas窗口的y坐标必须始终为0
        """
        if not hasattr(self, "_canvas") or not hasattr(self, "_canvas_window"):
            return

        canvas = self._canvas
        canvas.update_idletasks()

        # 获取画布实际宽度
        canvas_width = canvas.winfo_width()
        if canvas_width <= 1:  # 画布尚未初始化
            return

        # 限制内容最大宽度, 保持 UI 不会过宽
        max_content_width = 640
        content_width = min(canvas_width - 40, max_content_width)

        # 设置内容宽度
        canvas.itemconfigure(self._canvas_window, width=content_width)

        # 计算水平居中位置: (画布宽度 - 内容宽度) / 2
        center_x = max(0, (canvas_width - content_width) / 2)

        # 获取当前滚动位置，以便在更新后恢复
        try:
            current_scroll = canvas.yview()
        except:
            current_scroll = (0.0, 1.0)

        # 关键修复：确保Canvas窗口的y坐标始终为0
        # 如果y坐标不是0，内容会飘到视口外
        # 滚动应该通过Canvas的yview实现，而不是移动Canvas窗口的位置
        canvas.coords(self._canvas_window, center_x, 0)

        # 更新滚动区域（必须在设置坐标之后）
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        # 恢复之前的滚动位置
        try:
            canvas.yview_moveto(current_scroll[0])
        except:
            pass

    def _on_window_configure(self, event):
        """当窗口大小变化时（包括最大化/还原），更新Canvas内容位置"""
        # 只处理根窗口的配置事件
        if event.widget != self.root:
            return

        # 延迟更新，确保窗口大小已经稳定
        # 这会确保Canvas窗口的y坐标始终为0，防止内容飘到视口外
        self.root.after_idle(self._update_content_center)

    def _on_mousewheel(self, event):
        """鼠标滚轮垂直滚动"""
        if not hasattr(self, "_canvas"):
            return
        # Windows 上 event.delta 通常为 120 的倍数
        delta = int(-1 * (event.delta / 120))
        self._canvas.yview_scroll(delta, "units")

    def _create_widgets(self):
        """创建界面控件"""
        # ===== 可滚动主容器 =====
        container = ttk_bs.Frame(self.root)
        container.pack(fill=BOTH, expand=True)

        # 使用 Canvas + Scrollbar 实现垂直滚动
        canvas = tk.Canvas(container, highlightthickness=0)
        v_scrollbar = ttk_bs.Scrollbar(
            container, orient="vertical", command=canvas.yview
        )
        canvas.configure(yscrollcommand=v_scrollbar.set)

        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=BOTH, expand=True)

        self._canvas = canvas

        # 真正放控件的主 Frame, 嵌入到 Canvas 中
        main_frame = ttk_bs.Frame(canvas, padding=(20,))
        self._canvas_window = canvas.create_window(
            (0, 0), window=main_frame, anchor="nw"
        )

        # 内容尺寸变化时更新滚动区域和居中位置
        main_frame.bind("<Configure>", self._on_scrollable_frame_configure)

        # 画布大小变化时也更新居中位置
        canvas.bind("<Configure>", self._on_canvas_configure)

        # 绑定窗口大小变化事件，确保最大化/还原时正确更新
        self.root.bind("<Configure>", self._on_window_configure)

        # 绑定鼠标滚轮滚动
        canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 标题
        title_label = ttk_bs.Label(
            main_frame,
            text="HugoAura 安装器",
            font=("Microsoft YaHei UI", 20, "bold"),
            bootstyle=PRIMARY,
        )
        title_label.pack(pady=(0, 10))

        # 权限状态显示
        self._create_permission_status(main_frame)

        # 功能说明区域
        self._create_hugopass_section(main_frame)

        # 安装目录选择区域
        self._create_directory_section(main_frame)

        # 进度显示区域
        self._create_progress_section(main_frame)

        # 按钮区域
        self._create_button_section(main_frame)

    def _create_permission_status(self, parent):
        """创建权限状态显示区域"""
        # 检查管理员权限
        is_admin = self._check_admin_privileges()

        status_frame = ttk_bs.Frame(parent)
        status_frame.pack(fill=X, pady=(0, 15))

        # 权限图标和文本
        if is_admin:
            status_text = "✅ 已获得管理员权限"
            status_style = SUCCESS
        else:  # 理论上来说这种场景不会被触发
            status_text = "⚠ 需要管理员权限"
            status_style = WARNING

        status_label = ttk_bs.Label(
            status_frame,
            text=status_text,
            font=("Microsoft YaHei UI", 10),
            bootstyle=status_style,
        )
        status_label.pack()

    def _check_admin_privileges(self):
        """检查是否有管理员权限"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def _create_hugopass_section(self, parent):
        """创建功能说明区域 (HugoPass 密码绕过)"""
        info_frame = ttk_bs.LabelFrame(parent, text="功能说明")
        info_frame.pack(fill=X, pady=(0, 15))

        desc = (
            "安装后将为希沃管家注入「管理员密码绕过」补丁：\n"
            "在任何管理员验证界面，输入任意非空密码即可通过。\n\n"
            "安装会自动备份原始 app.asar 为 app.asar.orig，\n"
            "卸载时自动恢复原始文件与 Verify.json。"
        )
        ttk_bs.Label(
            info_frame,
            text=desc,
            justify=LEFT,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=W, padx=15, pady=15)

    def _create_directory_section(self, parent):
        """创建安装目录选择区域"""
        directory_frame = ttk_bs.LabelFrame(
            parent, text="安装目录 (可选)"
        )
        directory_frame.pack(fill=X, pady=(0, 15))

        dir_input_frame = ttk_bs.Frame(directory_frame)
        dir_input_frame.pack(fill=X, padx=15, pady=(15, 5))

        ttk_bs.Label(dir_input_frame, text="目录路径:").pack(side=LEFT)
        self.directory_entry = ttk_bs.Entry(
            dir_input_frame, textvariable=self.install_directory_var, width=40
        )
        self.directory_entry.pack(side=LEFT, padx=(10, 5))

        self.browse_dir_btn = ttk_bs.Button(
            dir_input_frame,
            text="浏览",
            command=self._browse_directory,
            bootstyle=OUTLINE,
        )
        self.browse_dir_btn.pack(side=LEFT)

        # 提示文本
        hint_label = ttk_bs.Label(
            directory_frame,
            text="留空则自动检测希沃管家安装目录",
            font=("Microsoft YaHei UI", 9),
            bootstyle=(SECONDARY, ITALIC),
        )
        hint_label.pack(anchor=W, padx=15, pady=(0, 15))

    def _create_progress_section(self, parent):
        """创建进度显示区域"""
        progress_frame = ttk_bs.LabelFrame(
            parent, text="安装进度"
        )
        progress_frame.pack(fill=X, pady=(0, 15))

        # 状态标签
        self.status_label = ttk_bs.Label(
            progress_frame,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.status_label.pack(anchor=W, padx=15, pady=(15, 5))

        # 进度条
        self.progress_bar = ttk_bs.Progressbar(
            progress_frame,
            variable=self.progress_var,
            length=400,
            mode="determinate",
            bootstyle=INFO,
        )
        self.progress_bar.pack(fill=X, padx=15, pady=(0, 5))

        # 当前步骤
        self.step_label = ttk_bs.Label(
            progress_frame,
            textvariable=self.step_var,
            font=("Microsoft YaHei UI", 9),
            bootstyle=SECONDARY,
        )
        self.step_label.pack(anchor=W, padx=15, pady=(0, 15))

    def _create_button_section(self, parent):
        """创建按钮区域"""
        button_frame = ttk_bs.Frame(parent)
        button_frame.pack(fill=X, pady=(10, 0))

        # 安装按钮
        self.install_btn = ttk_bs.Button(
            button_frame,
            text="开始安装",
            command=self._on_install_click,
            bootstyle=(INFO, "outline"),
            width=14,
        )
        self.install_btn.pack(side=LEFT, padx=(0, 10))

        # 卸载按钮
        self.uninstall_btn = ttk_bs.Button(
            button_frame,
            text="开始卸载",
            command=self._on_uninstall_click,
            bootstyle=(WARNING, "outline"),
            width=15,
        )
        self.uninstall_btn.pack(side=LEFT, padx=(0, 10))

        # 取消按钮
        self.cancel_btn = ttk_bs.Button(
            button_frame,
            text="取消",
            command=self._on_cancel_click,
            bootstyle=(DANGER, "outline"),
            width=14,
            state=DISABLED,
        )
        self.cancel_btn.pack(side=LEFT)

        about_btn_frame = ttk_bs.Frame(parent)
        about_btn_frame.pack(fill=X, pady=(10, 0))

        # 关于按钮
        about_btn = ttk_bs.Button(
            about_btn_frame,
            text="关于",
            command=self._show_about,
            bootstyle=(SECONDARY, "link"),
            width=14,
        )
        about_btn.pack(side=BOTTOM)

    def _browse_directory(self):
        """浏览目录"""
        directory = filedialog.askdirectory(title="选择安装目录")
        if directory:
            self.install_directory_var.set(directory)

    def _on_install_click(self):
        """安装按钮点击事件"""
        if self.install_callback:
            # 收集安装选项
            options = {
                "install_directory": self.install_directory_var.get(),
                "non_interactive": True,
            }
            self.install_callback(options)

    def _on_uninstall_click(self):
        """卸载按钮点击事件"""
        # 显示确认对话框
        confirm = messagebox.askyesno(
            "确认卸载",
            "确定要卸载HugoAura吗?\n\n卸载后希沃管家将恢复到原始状态\n此操作不可逆, 请确认",
            icon="warning",
        )

        if confirm and self.uninstall_callback:
            # 收集卸载选项
            uninstall_options = {
                "keep_user_data": False,  # TO DO
                "force": False,
                "dry_run": False,
            }
            self.uninstall_callback(uninstall_options)

    def _on_cancel_click(self):
        """取消按钮点击事件"""
        if self.cancel_callback:
            self.cancel_callback()

    def _show_about(self):
        """显示关于对话框"""
        about_text = f"""HugoAura-Install {__appVer__}

这是一个用于安装和管理 HugoPass 的工具。
HugoPass 是针对希沃管家 (Seewo Hugo) 的管理员密码绕过补丁。

主要功能:
• 一键安装密码绕过补丁
• 智能检测希沃管家
• 自动备份原始 app.asar
• 自动更新 Verify.json 完整性校验
• 一键完全卸载恢复

作者: HugoAura Devs
GUI 基于: ttkbootstrap & tkinter
GitHub 主仓库: HugoAura/Seewo-HugoAura
Install 主仓库: HugoAura/HugoAura-Install"""

        messagebox.showinfo("关于 HugoAura-Install", about_text)

    def set_install_callback(self, callback: Callable):
        """设置安装回调函数"""
        self.install_callback = callback

    def set_cancel_callback(self, callback: Callable):
        """设置取消回调函数"""
        self.cancel_callback = callback

    def set_uninstall_callback(self, callback: Callable):
        """设置卸载回调函数"""
        self.uninstall_callback = callback

    def update_progress(self, progress: int, step: str = "", status: str | None = None):
        """更新进度"""
        self.progress_var.set(progress)
        if step:
            self.step_var.set(step)
        if status:
            match status:
                case "success":
                    self.progress_bar.config(bootstyle=SUCCESS)
                case "info":
                    self.progress_bar.config(bootstyle=INFO)
                case "error":
                    self.progress_bar.config(bootstyle=DANGER)
                case "warn":
                    self.progress_bar.config(bootstyle=WARNING)
                case _:
                    pass
        self.root.update_idletasks()

    def update_status(self, status: str):
        """更新状态"""
        self.status_var.set(status)
        self.root.update_idletasks()

    def set_installing_state(self, installing: bool, operation: str = "安装"):
        """设置安装/卸载状态"""
        self.is_installing = installing
        if installing:
            if operation == "卸载":
                self.install_btn.config(state=DISABLED)
                self.uninstall_btn.config(state=DISABLED, text="卸载中...")
            else:
                self.install_btn.config(state=DISABLED, text="安装中...")
                self.uninstall_btn.config(state=DISABLED)
            self.cancel_btn.config(state=NORMAL)
            # 禁用输入控件
            for widget in [
                self.directory_entry,
                self.browse_dir_btn,
            ]:
                widget.config(state=DISABLED)
        else:
            self.install_btn.config(state=NORMAL, text="开始安装")
            self.uninstall_btn.config(state=NORMAL, text="开始卸载")
            self.cancel_btn.config(state=DISABLED)
            # 恢复输入控件状态
            self.directory_entry.config(state=NORMAL)
            self.browse_dir_btn.config(state=NORMAL)

    def set_install_button_state(self, enabled: bool, text: str = "开始安装"):
        """设置安装按钮状态"""
        if enabled:
            self.install_btn.config(state=NORMAL, text=text)
        else:
            self.install_btn.config(state=DISABLED, text=text)

    def show_message(self, title: str, message: str, msg_type: str = "info"):
        """显示消息对话框"""
        if msg_type == "error":
            messagebox.showerror(title, message)
        elif msg_type == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showinfo(title, message)

    def run(self):
        """运行主窗口"""
        self.root.mainloop()

    def destroy(self):
        """销毁窗口"""
        self.root.destroy()
