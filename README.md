markdown
# Steam 账号工具（半自动）

一个基于 PyQt5 的桌面应用，用于**半自动**生成和管理 Steam 账号。  
本工具依赖 **[CloudMail](https://github.com/Yuyuyang/cloudmail)** 邮件服务系统，通过其 REST API 创建临时邮箱并监听邮件。

**请注意**：本工具**不会**自动填写 Steam 注册表单，您需要手动将生成的用户名和密码填入注册页面，工具只负责：
- 生成随机账号信息
- 创建临时邮箱
- 自动点击验证链接
- 提取并显示 5 位验证码

注册的主体操作仍需您亲自完成。

---

## ✨ 功能概览

- **生成 Steam 账号信息**  
  调用 CloudMail API 创建临时邮箱，同时生成随机的 Steam 用户名和密码，并将信息保存到本地 `logs/` 目录。

- **邮件监听与验证码提取**  
  后台线程持续轮询邮箱，自动检测 Steam 发送的验证邮件。  
  若邮件在 **5 分钟内**到达，自动提取 **验证链接** 并点击，同时捕获 **5 位验证码** 显示在界面中。

- **账号信息管理**  
  导入本地 `logs/` 目录下所有已生成的账号，支持：
  - 查看详情（用户名、密码、邮箱、邮箱密码、创建时间）
  - 删除列表项（仅移除显示，不删除文件）
  - 双击复制任意列内容（序号和创建时间除外）

- **主题切换**  
  一键切换深色/浅色模式。

- **快捷链接**  
  快速打开 Steam 注册页和官网，方便您手动操作。

---

## 🚀 安装与运行

### 环境要求
- Python 3.8 或更高版本
- Windows / macOS / Linux（推荐 Windows）
- 已部署并运行的 **[CloudMail](https://github.com/Yuyuyang/cloudmail)** 服务

### 安装依赖
```bash
pip install PyQt5 requests
启动程序
bash
python main.py
📂 文件结构
text
SteamAccount/
├── main.py          # 主程序（您保存的文件名）
├── logs/            # 自动生成，存放所有账号信息（.txt 文件）
└── README.md        # 本文件
⚙️ 必填配置（使用前修改）
本工具需要连接一个正在运行的 CloudMail 实例。
请打开主程序文件，修改以下常量（位于代码开头）：

python
# CloudMail 服务地址（请替换为您的实际部署地址）
MAIL_BASE_URL = "https://your-cloudmail-server.com"

# CloudMail 管理员凭证（用于登录 API）
ADMIN_EMAIL = "admin@your-domain.com"
ADMIN_PASSWORD = "your_admin_password"

# 邮箱域名后缀（需与 CloudMail 配置一致，包含 @）
DOMAIN = "@your-domain.com"

# API 端点（CloudMail 默认路由，通常无需修改）
LOGIN_URL = MAIL_BASE_URL + "/api/login"
CREATE_USER_URL = MAIL_BASE_URL + "/api/user/add"
MAIL_LIST_URL = MAIL_BASE_URL + "/api/allEmail/list"
提示：如果您使用 CloudMail 的默认配置，请参考其 部署文档 设置好管理员账号和域名，确保 API 可正常访问。

🖥️ 使用流程（半自动）
1. 生成账号信息
点击 “✨ 生成 Steam 账号” 按钮，工具会：

登录 CloudMail，创建一个临时邮箱

生成随机的 Steam 用户名和密码

将信息保存到 logs/ 目录

此时您需要手动：

打开 Steam 注册页（点击界面上方的“打开注册页”按钮或访问 https://store.steampowered.com/join/）

将生成的用户名、密码填入注册表单（其他个人信息请自行填写）

提交注册，Steam 会向临时邮箱发送验证邮件

2. 自动监听与验证
工具会自动轮询邮箱，当检测到 Steam 验证邮件时：

自动点击邮件中的验证链接（完成邮箱验证）

提取 5 位验证码并显示在“验证码捕获”区域

您只需复制验证码，粘贴到 Steam 注册页面完成最后一步

3. 账号管理
所有生成的账号信息会出现在“账号管理”页面，方便您查阅和复制。

❓ 常见问题
Q: 为什么工具不自动填写 Steam 注册页？
A: 因为 Steam 注册页面的交互复杂（包括人机验证、地区选择等），自动化填写容易失败且违反 Steam 服务条款。本工具聚焦于“收件+验证”环节，将最繁琐的部分自动化，但仍保留手动操作以确保可靠性和安全性。

Q: 生成账号后，我该怎么做？
A: 您需要手动将生成的用户名和密码填入 Steam 注册页，并填写其他必要信息（如邮箱、出生日期等）。提交后，工具会自动处理验证邮件，您只需将获取的验证码输入页面即可完成注册。

Q: 监听不到邮件怎么办？
A: 检查 CloudMail 服务是否正常，以及管理员账号是否有权限查看所有邮件。同时请确保 Steam 确实向您的临时邮箱发送了邮件（查看邮箱列表确认）。

Q: 可以自定义验证码有效时间吗？
A: 可以。修改 CODE_WINDOW_MINUTES = 5 的数值（单位分钟）。

Q: 如何彻底删除某个账号文件？
A: 程序仅从列表中移除显示，不会删除物理文件。如需删除文件，请手动进入 logs/ 目录删除对应的 .txt 文件。

Q: 是否可以自定义 Toast 显示时长？
A: 可以。在 ToastNotification.add_message 方法中修改 timer.start(5000) 的毫秒值即可。

📄 开源许可
本项目仅供学习交流使用，不得用于商业或非法用途。使用本工具产生的任何后果由使用者自行承担。

🙏 致谢
邮件服务基于 CloudMail 开源项目，感谢作者 Yuyuyang 的优秀解决方案。

🤝 贡献
欢迎提交 Issue 或 Pull Request，共同完善这个工具。

Enjoy! 🎮
