# NotionBridge - MVP

小红书笔记同步到 Notion 的最小可行产品（MVP）

## 功能

- 从小红书专辑/收藏抓取笔记
- 自动下载视频和图片
- 同步到 Notion 数据库
- 增量同步（避免重复）

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 配置

复制 `.env.example` 到 `.env` 并填写配置：

```bash
cp .env.example .env
nano .env
```

必需配置：
- `NOTION_API_KEY`: Notion Integration API Key
- `NOTION_DATABASE_ID`: Notion 数据库 ID
- `XHS_BOARD_URL`: 小红书专辑/收藏 URL

### 3. 获取 Cookies

```bash
python get_cookies.py
```

在打开的浏览器中登录小红书，脚本会自动保存 Cookies。

### 4. 运行同步

```bash
python app/main.py
```

## Notion 数据库设置

数据库需要包含以下属性：
- **Name** (Title): 笔记标题
- **URL** (URL): 笔记链接

可选属性：
- **Author** (Rich Text): 作者
- **Created Date** (Date): 创建日期
- **Tags** (Multi-select): 标签

## 项目结构

```
xiaohongshu-to-notion/
├── app/
│   ├── main.py          # 主程序入口
│   ├── xhs.py           # 小红书爬虫
│   ├── notion.py        # Notion API
│   ├── config.py        # 配置管理
│   ├── logger.py        # 日志
│   ├── utils.py         # 工具函数
│   └── media.py         # 媒体处理
├── get_cookies.py       # Cookie 获取工具
├── .env                 # 配置文件
├── requirements.txt     # Python 依赖
└── README.md           # 本文件
```

## 常见问题

### Cookie 过期

Cookies 通常 1-2 个月后过期，需要重新获取：

```bash
rm cookies.json
python get_cookies.py
```

### 修改专辑 URL

编辑 `.env` 文件中的 `XHS_BOARD_URL`

### 查看详细日志

```bash
LOG_LEVEL=verbose python app/main.py
```

## 下一步

本项目正在进行系统性重构，当前版本为最小可行产品（MVP）。

前端代码已归档到 `archive/` 目录。

## License

MIT
