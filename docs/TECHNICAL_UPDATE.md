# NotionBridge 技术更新文档

## 概述

本文档记录 NotionBridge 项目在 2026年5月26-27日 的重大技术更新，主要涉及反检测方案升级和 Notion API 兼容性修复。

---

## 一、CloakBrowser 反检测集成

### 1.1 背景

原项目使用 Playwright 进行浏览器自动化，但存在以下问题：
- `navigator.webdriver` 属性为 `true`，易被检测
- 无反指纹补丁，Canvas/WebGL/Audio 指纹可被追踪
- TLS 指纹与真实 Chrome 不一致

### 1.2 解决方案

采用 [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) 替代 Playwright：

| 特性 | Playwright | CloakBrowser |
|------|-----------|--------------|
| 反检测层级 | JS 注入 | C++ 源码级 |
| `navigator.webdriver` | `true` | `false` |
| reCAPTCHA v3 评分 | 0.1 | 0.9 |
| Canvas/WebGL 指纹 | 可检测 | 随机化 |
| TLS 指纹 | 不匹配 | 与 Chrome 一致 |
| 人类行为模拟 | 无 | `humanize=True` |

### 1.3 核心改动

**app/xhs.py**

```python
# 原代码
from playwright.sync_api import sync_playwright
browser = p.chromium.launch(headless=headless)

# 新代码
from cloakbrowser import launch, launch_persistent_context
context = launch_persistent_context(
    profile_dir,
    headless=headless,
    humanize=True,
    viewport={'width': 1280, 'height': 720},
)
```

**关键点：**
- 使用 `launch_persistent_context` 保持登录状态
- `humanize=True` 启用贝塞尔曲线鼠标移动和逐字输入
- 每次启动后从 `cookies.json` 加载 cookies

### 1.4 登录流程

1. 首次运行 `get_cookies.py`，弹出浏览器
2. 手动扫码登录
3. 脚本自动检测登录状态（`data-logged="1"`）
4. 保存 cookies 到 `cookies.json` 和 `browser_profile/`
5. 后续运行自动恢复 session

---

## 二、Notion API 兼容性修复

### 2.1 问题描述

`notion-client 2.7.0` 版本 API 发生变化：
- `notion.databases.query()` 方法不可用
- `notion.pages.create()` 方法不可用
- `notion.blocks.children.append()` 方法不可用

### 2.2 解决方案

改用 raw HTTP requests 替代 SDK 方法：

```python
# 新增辅助函数
def _notion_request(method: str, path: str, body: dict = None) -> dict:
    api_key = Config.NOTION_API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    url = f"https://api.notion.com/v1{path}"
    response = requests.request(method, url, headers=headers, json=body, timeout=30)
    response.raise_for_status()
    return response.json()
```

### 2.3 Tags 写入修复

**问题：** Tags 属性未写入 Notion 数据库

**原因：** 原代码在创建页面时直接包含 Tags，若属性不存在会验证失败

**解决方案：** 分两步操作

```python
# 1. 先创建页面（不含 Tags）
page = _notion_request("POST", "/pages", body)

# 2. 单独更新 Tags（失败则跳过）
try:
    _notion_request("PATCH", f"/pages/{page_id}", {
        "properties": {
            "Tags": {
                "multi_select": [{"name": tag} for tag in tags]
            }
        }
    })
except Exception:
    logger.debug("Tags update skipped")
```

---

## 三、其他修复

### 3.1 Notion API 超时

所有 HTTP 请求添加超时防止卡死：

```python
requests.post(url, json=data, timeout=30)   # API 调用
requests.post(url, files=files, timeout=60)  # 文件上传
```

### 3.2 变量名冲突

```python
# 原代码（变量被覆盖）
has_images = any(item["type"] == "image" for item in item.get("content", []))

# 修复后
has_images = any(c["type"] == "image" for c in item.get("content", []))
```

### 3.3 项目清理

删除文件：
- `app/xhs.py.original`, `app/xhs.py.old_backup`, `app/xhs.py.new`
- `app/config.py.bak`, `get_cookies.py.bak_new`
- `REFACTORING_PLAN.md`, `archive/` 目录

---

## 四、配置说明

### 4.1 环境变量

```env
# CloakBrowser 配置
CLOAKBROWSER_HUMANIZE=true    # 启用人类行为模拟
CLOAKBROWSER_PROFILE_DIR=./browser_profile  # 持久化目录

# Notion API
NOTION_API_KEY=ntn_xxx
NOTION_DATABASE_ID=xxx

# 小红书
XHS_BOARD_URL=https://www.xiaohongshu.com/board/xxx
USE_REAL_SCRAPER=true
HEADLESS_MODE=true
```

### 4.2 文件结构

```
NotionBridge/
├── app/
│   ├── config.py          # 配置管理
│   ├── logger.py          # 日志
│   ├── main.py            # 主入口
│   ├── media.py           # 视频下载/帧提取
│   ├── notion.py          # Notion API（raw requests）
│   ├── utils.py           # 工具函数
│   ├── xhs.py             # 小红书爬虫（CloakBrowser）
│   └── xhs_selectors.py   # CSS 选择器
├── browser_profile/       # CloakBrowser 持久化（已 gitignore）
├── cookies.json           # Cookies（已 gitignore）
├── get_cookies.py         # 登录工具
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 五、部署建议

### 5.1 推荐方案：本地运行

```bash
cd /Users/hawkmor/Documents/NotionBridge
source .venv/bin/activate
python app/main.py
```

**优点：**
- 住宅 IP，低风控风险
- CloakBrowser 原生支持
- 调试方便

### 5.2 不推荐：Docker 部署

服务器 IP 容易触发小红书风控。

### 5.3 Raycast 快捷脚本

```
/Users/hawkmor/Documents/RaycastScripts/
├── NotionBridge Get Cookies.command  # 获取 Cookies
└── notionbridge.command              # 运行同步
```

---

## 六、测试验证

### 6.1 CloakBrowser 测试

```bash
python -c "
from cloakbrowser import launch
browser = launch(headless=False)
page = browser.new_page()
page.goto('https://www.xiaohongshu.com')
print('登录状态:', page.evaluate('() => document.querySelector(\"#global\")?.getAttribute(\"data-logged\") == \"1\"'))
browser.close()
"
```

### 6.2 Tags 写入测试

```bash
python -c "
from app.notion import push_to_notion
test_item = {
    'title': '测试',
    'tags': ['标签A', '标签B'],
    'content': [{'type': 'text', 'content': '#测试标签'}]
}
success, skip, fail = push_to_notion([test_item], incremental=False)
print(f'结果: 成功={success}')
"
```

---

## 七、已知问题

1. 少数笔记点击时会弹出登录框（XHS 弹窗遮挡），已自动跳过
2. `notion-client 2.7.0` API 变更，已改用 raw requests 兼容
3. CloakBrowser 首次运行需下载 Chromium（约 200MB）

---

*文档更新时间：2026-05-27*
