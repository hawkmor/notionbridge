# NotionBridge 技术更新文档

## 概述

本文档记录 NotionBridge 项目在 2026年5月26-27日 的重大技术更新，主要涉及反检测方案升级和 Notion API 兼容性修复。

---

## 2026-05-28 更新

### 小红书收藏夹分页修复

旧抓取逻辑用当前 DOM 中的 `note-item` 数量判断收藏夹条目数。小红书收藏夹页面会虚拟化列表，DOM 中通常只保留首屏或当前可视区域附近的卡片，因此 135 条收藏夹可能只抓到约 29 条。

新逻辑改为：
- 从页面首屏 HTML 的 `boardFeedsMap` 中读取首批笔记和 cursor
- 监听页面真实触发的 `/api/sns/web/v1/board/note` 分页响应
- 滚动页面触发后续分页加载，并累计唯一 note id
- 使用接口返回的 `xsec_token` 打开详情页，避免裸 `/explore/<id>` 直链返回 404

### 视频上传保护

新增配置：

```env
SYNC_VIDEO_UPLOADS=true
MAX_VIDEO_UPLOAD_MB=100
```

`SYNC_VIDEO_UPLOADS=false` 时跳过视频上传，并把视频 URL 保留为 Notion bookmark。`MAX_VIDEO_UPLOAD_MB` 会跳过超大视频上传，避免 300MB+ 视频拖慢或中断同步。

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

**解决方案：** 读取数据库 schema 后，仅在 `Tags` 属性真实存在且类型为 Multi-select 时写入

```python
tags_name = _find_property(database_properties, ["Tags", "Tag", "标签"], "multi_select")
if tags_name and tags:
    properties[tags_name] = {
        "multi_select": [{"name": tag[:100]} for tag in tags[:20]]
    }
```

### 2.4 字段与内容块写入修复

同步前会读取 Notion 数据库 schema，只写入实际存在且类型匹配的属性：

- `Name` / `Title` / `标题`：Title
- `URL` / `Link` / `链接`：URL
- `Author` / `作者`：Rich text
- `Tags` / `标签`：Multi-select
- `Content` / `Description` / `正文`：Rich text
- `Publish Date` / `Date` / `日期`：Date

注意：如果数据库里的 `Created Date` 是 Notion 的 `created_time` 自动字段，API 不能手动写入小红书发布日期。需要保存原始发布日期时，请新增一个真正的 Date 属性，例如 `Publish Date`。

正文、图片、视频封面块已统一改为 raw HTTP：

```python
_notion_request("PATCH", f"/blocks/{page_id}/children", {
    "children": blocks
})
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
- `archive/` 目录

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
