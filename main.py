#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import requests
import warnings
import random
import string
import os
import time
import re
import traceback
import threading
from datetime import datetime, timedelta
import subprocess
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QStackedWidget, QLabel, QPushButton,
                             QTextEdit, QTreeWidget, QTreeWidgetItem, QHeaderView,
                             QFrame, QSplitter, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPixmap, QPainter, QBrush, QPen

warnings.filterwarnings("ignore")

# ==================== SSL 适配器 ====================
class TlsAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_version'] = ssl.PROTOCOL_TLSv1_2
        kwargs['ssl_context'] = ssl.create_default_context()
        kwargs['ssl_context'].set_ciphers('DEFAULT@SECLEVEL=1')
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount('https://', TlsAdapter())
session.verify = False
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# ==================== 配置（请修改为您的实际服务信息） ====================
MAIL_BASE_URL = "https://your-mail-server.com"          # 邮件服务器基础地址
ADMIN_EMAIL = "admin@your-mail-server.com"              # 管理员邮箱
ADMIN_PASSWORD = "your_admin_password"                  # 管理员密码
DOMAIN = "@your-mail-server.com"                        # 邮箱后缀（需包含@）

LOGIN_URL = MAIL_BASE_URL + "/api/login"
CREATE_USER_URL = MAIL_BASE_URL + "/api/user/add"
MAIL_LIST_URL = MAIL_BASE_URL + "/api/allEmail/list"

CODE_WINDOW_MINUTES = 5

# ==================== 核心功能 ====================
def parse_mail_time(time_val):
    if not time_val:
        return None
    if isinstance(time_val, datetime):
        return time_val
    if isinstance(time_val, (int, float)):
        if time_val > 1e12:
            return datetime.fromtimestamp(time_val / 1000)
        else:
            return datetime.fromtimestamp(time_val)
    if isinstance(time_val, str):
        try:
            return datetime.fromisoformat(time_val.replace('Z', '+00:00'))
        except:
            pass
        try:
            return datetime.strptime(time_val, "%Y-%m-%d %H:%M:%S")
        except:
            pass
        try:
            return datetime.strptime(time_val, "%Y-%m-%dT%H:%M:%S")
        except:
            pass
    return None

def get_admin_token():
    resp = session.post(LOGIN_URL, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    token = data.get("data", {}).get("token")
    if not token:
        raise Exception(f"登录失败: {data}")
    return token

def create_mailbox(token):
    local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email = local + DOMAIN
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    payload = {"email": email, "suffix": DOMAIN, "password": password, "type": 1}
    headers = {"Authorization": token, "Content-Type": "application/json"}
    resp = session.post(CREATE_USER_URL, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise Exception(f"创建邮箱失败: {data.get('message')}")
    return email, password

def generate_username():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

def generate_password():
    return ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*", k=16))

def get_mail_list(token):
    try:
        params = {"size": 10, "timeSort": 0, "type": "receive"}
        headers = {"Authorization": token}
        resp = session.get(MAIL_LIST_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise Exception(f"API返回错误: {data}")
        result = data.get("data")
        if isinstance(result, dict):
            return result.get("list", [])
        elif isinstance(result, list):
            return result
        else:
            return []
    except Exception as e:
        return []

def extract_link(content):
    if not content:
        return None
    pattern = r'https://store\.steampowered\.com/account/newaccountverification\?[^\s"\'<>]+'
    match = re.search(pattern, content)
    return match.group(0) if match else None

def extract_code(content):
    if not content:
        return None
    clean = re.sub(r'<[^>]+>', ' ', content)
    clean = re.sub(r'\s+', ' ', clean)
    pattern = r'\b([A-Z0-9]{5})\b'
    match = re.search(pattern, clean)
    return match.group(1) if match else None

def extract_username(content, subject):
    if not content:
        return None
    clean = re.sub(r'<[^>]+>', ' ', content)
    clean = re.sub(r'\s+', ' ', clean)
    patterns = [
        r'[Hh]ello[,:\s]+([A-Za-z0-9_]+)',
        r'[Dd]ear[,:\s]+([A-Za-z0-9_]+)',
        r'[Aa]ccount[:\s]+([A-Za-z0-9_]+)',
        r'[Uu]sername[:\s]+([A-Za-z0-9_]+)',
        r'[Nn]ame[:\s]+([A-Za-z0-9_]+)',
        r'尊敬的([A-Za-z0-9_]+)',
        r'用户[:\s]+([A-Za-z0-9_]+)',
    ]
    for pat in patterns:
        m = re.search(pat, clean)
        if m:
            return m.group(1)
    if subject:
        m = re.search(r'for\s+([A-Za-z0-9_]+)', subject)
        if m:
            return m.group(1)
    return None

# ==================== 监听线程 ====================
class WatcherThread(QThread):
    log_signal = pyqtSignal(str, bool)
    code_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        self.log_signal.emit(f"邮件监听已启动，正在登录邮箱后台...（只处理最近{CODE_WINDOW_MINUTES}分钟内的Steam邮件）", False)
        try:
            token = get_admin_token()
            self.log_signal.emit("后台登录成功，开始监听邮件（每5秒检查一次）", False)
        except Exception as e:
            self.log_signal.emit(f"监听线程登录失败: {e}", True)
            traceback.print_exc()
            return

        processed = set()
        while self.running:
            try:
                mails = get_mail_list(token)
                if not mails:
                    time.sleep(5)
                    continue

                now = datetime.now()
                cutoff = now - timedelta(minutes=CODE_WINDOW_MINUTES)

                for mail in mails:
                    mail_id = mail.get("id") or mail.get("emailId") or mail.get("_id")
                    if not mail_id:
                        mail_id = f"{mail.get('subject', '')}_{mail.get('time', '')}"
                    if mail_id in processed:
                        continue

                    time_str = mail.get("time") or mail.get("createTime") or mail.get("sendTime")
                    mail_time = parse_mail_time(time_str)
                    if mail_time is None:
                        is_recent = False
                        self.log_signal.emit(f"⚠️ 无法解析邮件时间，跳过处理 (ID: {mail_id})", True)
                    else:
                        is_recent = mail_time >= cutoff

                    subject = mail.get("subject", "")
                    if "steam" not in subject.lower():
                        processed.add(mail_id)
                        continue

                    if not is_recent:
                        time_str_fmt = mail_time.strftime('%Y-%m-%d %H:%M:%S') if mail_time else '未知'
                        self.log_signal.emit(f"⏭️ 跳过超时Steam邮件（时间: {time_str_fmt}）— 不点击链接，不提取验证码", False)
                        processed.add(mail_id)
                        continue

                    self.log_signal.emit(f"📨 发现最近Steam邮件: {subject} (时间: {mail_time.strftime('%Y-%m-%d %H:%M:%S')})", False)
                    content = mail.get("text") or mail.get("content") or mail.get("html") or ""
                    if not content:
                        self.log_signal.emit("⚠️ 邮件内容为空", True)
                        processed.add(mail_id)
                        continue

                    link = extract_link(content)
                    if link:
                        self.log_signal.emit(f"🔗 验证链接: {link}", False)
                        try:
                            resp = session.get(link, timeout=10)
                            self.log_signal.emit(f"✅ 已点击验证链接 (状态码: {resp.status_code})", False)
                        except Exception as e:
                            self.log_signal.emit(f"❌ 点击链接失败: {e}", True)
                    else:
                        self.log_signal.emit("ℹ️ 未找到验证链接", False)

                    code = extract_code(content)
                    if code:
                        username = extract_username(content, subject)
                        if username:
                            display = f"用户名: {username}  验证码: {code}"
                        else:
                            display = f"验证码: {code}  (未提取到用户名)"
                        self.code_signal.emit(display)
                        self.log_signal.emit(f"✅ 捕获验证码: {code}" + (f" (用户名: {username})" if username else ""), False)
                    else:
                        preview = content[:200].replace('\n', ' ')
                        self.log_signal.emit(f"⚠️ 未提取到5位验证码，内容预览: {preview}...", True)

                    processed.add(mail_id)

            except Exception as e:
                self.log_signal.emit(f"监听循环发生错误: {e}", True)
                traceback.print_exc()
            time.sleep(5)

        self.log_signal.emit("邮件监听已停止", False)

# ==================== Toast 通知（右下角，无置顶） ====================
class ToastNotification(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                border-radius: 10px;
                border: 1px solid #444444;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
                padding: 8px 12px;
                background: transparent;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.labels = []
        self.parent_window = parent
        self.update_position()
        if parent:
            parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.parent_window and event.type() == event.Move:
            self.update_position()
        return super().eventFilter(obj, event)

    def update_position(self):
        if not self.parent_window:
            return
        x = self.parent_window.x() + self.parent_window.width() - self.width() - 30
        y = self.parent_window.y() + self.parent_window.height() - self.height() - 30
        screen = QApplication.primaryScreen().geometry()
        x = max(0, min(x, screen.width() - self.width()))
        y = max(0, min(y, screen.height() - self.height()))
        self.move(x, y)

    def add_message(self, message):
        label = QLabel(message)
        label.setWordWrap(True)
        self.layout().addWidget(label)
        self.labels.append((label, None))
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.remove_message(label))
        timer.start(5000)
        for i, (lbl, tmr) in enumerate(self.labels):
            if lbl == label:
                self.labels[i] = (lbl, timer)
                break
        self.adjust_size()
        self.update_position()
        self.show()

    def remove_message(self, label):
        for i, (lbl, tmr) in enumerate(self.labels):
            if lbl == label:
                self.layout().removeWidget(lbl)
                lbl.deleteLater()
                if tmr:
                    tmr.stop()
                self.labels.pop(i)
                break
        self.adjust_size()
        self.update_position()
        if not self.labels:
            self.hide()

    def adjust_size(self):
        if not self.labels:
            self.resize(320, 50)
            return
        total_height = 10
        for label, _ in self.labels:
            total_height += label.sizeHint().height() + 4
        total_height = max(50, min(total_height, 300))
        self.resize(320, total_height)
        for label, _ in self.labels:
            label.setFixedWidth(300)

    def update_theme(self, is_dark):
        if is_dark:
            bg = "#2d2d2d"
            fg = "#e0e0e0"
            border = "#444444"
        else:
            bg = "#ffffff"
            fg = "#1a1a1a"
            border = "#bbbbbb"
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-radius: 10px;
                border: 1px solid {border};
            }}
            QLabel {{
                color: {fg};
                font-size: 12px;
                padding: 8px 12px;
                background: transparent;
            }}
        """)
        for label, _ in self.labels:
            label.setStyleSheet(f"color: {fg};")

# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_theme = "dark"
        self.accounts_data = []
        self.watcher_thread = None
        self.toast = None
        self.init_ui()
        self.load_accounts()
        self.start_watcher()

    def init_ui(self):
        self.setWindowTitle("Steam 工具 · 邮件监听 & 账号生成")
        self.setGeometry(100, 100, 1100, 750)
        self.setMinimumSize(950, 600)

        self.toast = ToastNotification(self)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 10, 20, 20)
        main_layout.setSpacing(10)

        # ---------- 侧边栏 ----------
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: none;
            }
        """)
        main_layout.addWidget(self.sidebar)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(5)

        label_func = QLabel("功能")
        label_func.setStyleSheet("color: #aaaaaa; font-size: 14px; font-weight: bold;")
        sidebar_layout.addWidget(label_func)
        self.func_label = label_func

        self.nav_btns = []
        self.nav_frames = {}

        btn_style = """
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                border-radius: 8px;
                padding: 10px 15px;
                text-align: left;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QPushButton:checked {
                background-color: #4a9eff;
                color: white;
            }
        """

        for text, name in [("📧 账号生成", "generate"), ("📡 邮件监听", "monitor"), ("📂 账号管理", "accounts")]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda checked, n=name: self.switch_page(n))
            sidebar_layout.addWidget(btn)
            self.nav_btns.append((btn, name))

        sidebar_layout.addStretch()

        self.current_view_label = QLabel("当前: 生成")
        self.current_view_label.setStyleSheet("color: #888888; font-size: 11px;")
        sidebar_layout.addWidget(self.current_view_label)

        # ---------- 右侧内容 ----------
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(content_widget, 1)

        # 顶部栏：标题 + 打开注册页按钮 + 打开官网按钮 + 主题切换
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 10)

        self.title_label = QLabel("🎮 Steam 账号工具")
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #e0e0e0;")
        top_bar_layout.addWidget(self.title_label)

        self.btn_register = QPushButton("🌐 打开注册页")
        self.btn_register.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.btn_register.clicked.connect(lambda: self.open_url("https://store.steampowered.com/join/"))
        top_bar_layout.addWidget(self.btn_register)

        top_bar_layout.addStretch()

        self.btn_website = QPushButton("🌐 打开官网")
        self.btn_website.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.btn_website.clicked.connect(lambda: self.open_url("https://store.steampowered.com"))
        top_bar_layout.addWidget(self.btn_website)

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                border-radius: 18px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar_layout.addWidget(self.theme_btn)

        content_layout.addWidget(top_bar)

        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.HLine)
        self.sep.setStyleSheet("background-color: #444444; max-height: 1px;")
        content_layout.addWidget(self.sep)

        self.stacked = QStackedWidget()
        content_layout.addWidget(self.stacked)

        # ---------- 页面1: 账号生成 ----------
        page_generate = QWidget()
        page_generate_layout = QVBoxLayout(page_generate)
        page_generate_layout.setContentsMargins(0, 10, 0, 0)

        self.gen_btn = QPushButton("✨ 生成 Steam 账号")
        self.gen_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 30px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a8aef;
            }
        """)
        self.gen_btn.clicked.connect(self.generate_steam_account)
        page_generate_layout.addWidget(self.gen_btn, 0, Qt.AlignCenter)

        self.generate_log = QTextEdit()
        self.generate_log.setReadOnly(True)
        self.generate_log.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
        """)
        page_generate_layout.addWidget(QLabel("📝 生成记录"))
        page_generate_layout.addWidget(self.generate_log)

        self.code_log = QTextEdit()
        self.code_log.setReadOnly(True)
        self.code_log.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
        """)
        page_generate_layout.addWidget(QLabel("🔑 验证码捕获（仅最近5分钟）"))
        page_generate_layout.addWidget(self.code_log)
        self.stacked.addWidget(page_generate)

        # ---------- 页面2: 邮件监听 ----------
        page_monitor = QWidget()
        page_monitor_layout = QVBoxLayout(page_monitor)
        page_monitor_layout.setContentsMargins(0, 10, 0, 0)

        self.monitor_log = QTextEdit()
        self.monitor_log.setReadOnly(True)
        self.monitor_log.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
        """)
        page_monitor_layout.addWidget(QLabel("📡 邮件监听日志"))
        page_monitor_layout.addWidget(self.monitor_log)
        self.stacked.addWidget(page_monitor)

        # ---------- 页面3: 账号管理 ----------
        page_accounts = QWidget()
        page_accounts_layout = QVBoxLayout(page_accounts)
        page_accounts_layout.setContentsMargins(0, 10, 0, 0)

        acc_toolbar = QWidget()
        acc_toolbar_layout = QHBoxLayout(acc_toolbar)
        acc_toolbar_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_reload = QPushButton("🔄 重新导入")
        self.btn_reload.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.btn_reload.clicked.connect(self.load_accounts)
        acc_toolbar_layout.addWidget(self.btn_reload)

        self.btn_delete = QPushButton("🗑 删除选中")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
        """)
        self.btn_delete.clicked.connect(self.delete_selected_account)
        acc_toolbar_layout.addWidget(self.btn_delete)

        acc_toolbar_layout.addStretch()
        self.tip_label = QLabel("💡 双击任意列复制内容（序号/时间除外）")
        self.tip_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        acc_toolbar_layout.addWidget(self.tip_label)

        page_accounts_layout.addWidget(acc_toolbar)

        self.accounts_tree = QTreeWidget()
        self.accounts_tree.setColumnCount(6)
        self.accounts_tree.setHeaderLabels(["序号", "Steam用户名", "密码", "邮箱", "邮箱密码", "创建时间"])
        self.accounts_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                alternate-background-color: #3a3a3a;
            }
            QTreeWidget::item {
                height: 28px;
            }
            QTreeWidget::item:selected {
                background-color: #4a9eff;
                color: white;
            }
            QHeaderView::section {
                background-color: #1a1a1a;
                color: #e0e0e0;
                padding: 6px;
                border: none;
            }
        """)
        self.accounts_tree.setAlternatingRowColors(True)
        self.accounts_tree.setSortingEnabled(True)
        self.accounts_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.accounts_tree.itemDoubleClicked.connect(self.copy_cell_content)
        page_accounts_layout.addWidget(self.accounts_tree)
        self.stacked.addWidget(page_accounts)

        self.switch_page("generate")
        self.apply_theme()

    def switch_page(self, page_name):
        if page_name == "generate":
            self.stacked.setCurrentIndex(0)
            self.current_view_label.setText("当前: 生成")
        elif page_name == "monitor":
            self.stacked.setCurrentIndex(1)
            self.current_view_label.setText("当前: 监听")
        elif page_name == "accounts":
            self.stacked.setCurrentIndex(2)
            self.current_view_label.setText("当前: 管理")
            self.load_accounts()

        for btn, name in self.nav_btns:
            btn.setChecked(name == page_name)

    # ---------- 主题切换 ----------
    def toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme()

    def apply_theme(self):
        if self.current_theme == "dark":
            bg = "#1a1a1a"
            fg = "#e0e0e0"
            card_bg = "#2d2d2d"
            card_fg = "#e0e0e0"
            accent = "#4a9eff"
            btn_bg = "#2d2d2d"
            btn_fg = "#e0e0e0"
            sep_color = "#444444"
            theme_icon = "🌙"
            border_color = "#3a3a3a"
            alt_bg = "#3a3a3a"
            header_bg = "#1a1a1a"
            tip_color = "#aaaaaa"
            toast_bg = "#2d2d2d"
            toast_fg = "#e0e0e0"
            toast_border = "#444444"
        else:
            bg = "#f0f0f0"
            fg = "#1a1a1a"
            card_bg = "#ffffff"
            card_fg = "#1a1a1a"
            accent = "#0078d7"
            btn_bg = "#e0e0e0"
            btn_fg = "#1a1a1a"
            sep_color = "#bbbbbb"
            theme_icon = "☀️"
            border_color = "#cccccc"
            alt_bg = "#e8e8e8"
            header_bg = "#f0f0f0"
            tip_color = "#666666"
            toast_bg = "#ffffff"
            toast_fg = "#1a1a1a"
            toast_border = "#bbbbbb"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {bg};
                color: {fg};
            }}
        """)

        self.sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: none;
            }}
        """)

        self.func_label.setStyleSheet(f"color: {tip_color}; font-size: 14px; font-weight: bold;")

        nav_style = f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_fg};
                border: none;
                border-radius: 8px;
                padding: 10px 15px;
                text-align: left;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {btn_bg if self.current_theme=="dark" else "#d0d0d0"};
            }}
            QPushButton:checked {{
                background-color: {accent};
                color: white;
            }}
        """
        for btn, _ in self.nav_btns:
            btn.setStyleSheet(nav_style)

        self.current_view_label.setStyleSheet(f"color: {tip_color}; font-size: 11px;")
        self.title_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {fg};")

        self.btn_register.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_fg};
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {btn_bg if self.current_theme=="dark" else "#d0d0d0"};
            }}
        """)

        self.btn_website.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_fg};
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {btn_bg if self.current_theme=="dark" else "#d0d0d0"};
            }}
        """)

        self.theme_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_fg};
                border: none;
                border-radius: 18px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: {btn_bg if self.current_theme=="dark" else "#d0d0d0"};
            }}
        """)
        self.theme_btn.setText(theme_icon)

        self.sep.setStyleSheet(f"background-color: {sep_color}; max-height: 1px;")

        self.gen_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 30px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {accent if self.current_theme=="dark" else "#006ac7"};
            }}
        """)

        log_style = f"""
            QTextEdit {{
                background-color: {card_bg};
                color: {card_fg};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }}
        """
        self.generate_log.setStyleSheet(log_style)
        self.code_log.setStyleSheet(log_style)
        self.monitor_log.setStyleSheet(log_style)

        for child in self.findChildren(QLabel):
            if child not in [self.title_label, self.current_view_label, self.func_label, self.tip_label]:
                if child.parent() and isinstance(child.parent(), QVBoxLayout):
                    child.setStyleSheet(f"color: {fg}; font-size: 13px; font-weight: bold;")

        self.btn_reload.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_fg};
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
            }}
            QPushButton:hover {{
                background-color: {btn_bg if self.current_theme=="dark" else "#d0d0d0"};
            }}
        """)
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
        """)
        self.tip_label.setStyleSheet(f"color: {tip_color}; font-size: 11px;")

        tree_style = f"""
            QTreeWidget {{
                background-color: {card_bg};
                color: {card_fg};
                border: 1px solid {border_color};
                border-radius: 8px;
                alternate-background-color: {alt_bg};
            }}
            QTreeWidget::item {{
                height: 28px;
            }}
            QTreeWidget::item:selected {{
                background-color: {accent};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {fg};
                padding: 6px;
                border: none;
            }}
        """
        self.accounts_tree.setStyleSheet(tree_style)

        self.toast.update_theme(self.current_theme == "dark")

    # ---------- 打开链接 ----------
    def open_url(self, url):
        try:
            subprocess.Popen(['start', url], shell=True)
            self.toast.add_message(f"🌐 已打开: {url}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开链接: {e}")

    # ---------- 功能函数 ----------
    def generate_steam_account(self):
        self.generate_log.append("🔄 开始生成 Steam 账号...")
        try:
            token = get_admin_token()
            self.generate_log.append("后台登录成功")

            email, email_pwd = create_mailbox(token)
            self.generate_log.append(f"📧 临时邮箱: {email}  密码: {email_pwd}")

            steam_user = generate_username()
            steam_pass = generate_password()
            self.generate_log.append(f"👤 Steam 用户名: {steam_user}")
            self.generate_log.append(f"🔑 Steam 密码: {steam_pass}")

            script_dir = os.path.dirname(os.path.abspath(__file__))
            logs_dir = os.path.join(script_dir, "logs")
            os.makedirs(logs_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}.txt"
            filepath = os.path.join(logs_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write("邮箱网站: 请替换为您的邮件服务器地址\n")
                f.write(f"{steam_user}----------{steam_pass}----------{email}----------{email_pwd}\n")

            self.generate_log.append(f"✅ 结果已保存到: {filepath}")
            self.generate_log.append(f"📄 内容: {steam_user}----------{steam_pass}----------{email}----------{email_pwd}")
            self.generate_log.append("")

            self.toast.add_message(f"✅ 账号已生成: {steam_user}")
            self.load_accounts()

        except Exception as e:
            self.generate_log.append(f"❌ 生成账号失败: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"生成失败: {e}")

    def load_accounts(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(script_dir, "logs")
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir, exist_ok=True)

        self.accounts_data = []
        for fname in os.listdir(logs_dir):
            if fname.endswith(".txt"):
                filepath = os.path.join(logs_dir, fname)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        if len(lines) < 2:
                            continue
                        data_line = lines[1].strip()
                        parts = data_line.split("----------")
                        if len(parts) != 4:
                            continue
                        steam_user, steam_pass, email, email_pwd = parts
                        base = os.path.splitext(fname)[0]
                        try:
                            create_time = datetime.strptime(base, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            create_time = "未知"
                        self.accounts_data.append({
                            "file": fname,
                            "steam_user": steam_user,
                            "steam_pass": steam_pass,
                            "email": email,
                            "email_pwd": email_pwd,
                            "create_time": create_time,
                        })
                except Exception as e:
                    print(f"解析文件 {fname} 失败: {e}")

        self.refresh_accounts_table()

    def refresh_accounts_table(self):
        self.accounts_tree.clear()
        for idx, acc in enumerate(self.accounts_data, start=1):
            item = QTreeWidgetItem(self.accounts_tree)
            item.setText(0, str(idx))
            item.setText(1, acc["steam_user"])
            item.setText(2, acc["steam_pass"])
            item.setText(3, acc["email"])
            item.setText(4, acc["email_pwd"])
            item.setText(5, acc["create_time"])

    def delete_selected_account(self):
        selected = self.accounts_tree.selectedItems()
        if not selected:
            self.toast.add_message("⚠️ 请先选中要删除的账号")
            return
        indices = []
        for item in selected:
            index = self.accounts_tree.indexOfTopLevelItem(item)
            if index >= 0:
                indices.append(index)
        indices.sort(reverse=True)
        for idx in indices:
            if idx < len(self.accounts_data):
                del self.accounts_data[idx]
        self.refresh_accounts_table()
        self.toast.add_message("🗑 已删除选中账号")

    def copy_cell_content(self, item, column):
        if column == 0 or column == 5:
            return
        content = item.text(column)
        if content:
            clipboard = QApplication.clipboard()
            clipboard.setText(content)
            self.toast.add_message(f"📋 已复制: {content}")

    def start_watcher(self):
        self.watcher_thread = WatcherThread()
        self.watcher_thread.log_signal.connect(self.append_monitor_log)
        self.watcher_thread.code_signal.connect(self.append_code_log)
        self.watcher_thread.start()

    def append_monitor_log(self, msg, is_error):
        self.monitor_log.append(msg)

    def append_code_log(self, msg):
        self.code_log.append(msg)

    def closeEvent(self, event):
        if self.watcher_thread and self.watcher_thread.isRunning():
            self.watcher_thread.stop()
            self.watcher_thread.quit()
            self.watcher_thread.wait()
        event.accept()

# ==================== 入口 ====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())