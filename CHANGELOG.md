# Changelog

## 2026-05-27 - Tags 写入修复 + notion-client 兼容

### Bug 修复
- 修复 Tags 未写入 Notion 数据库的问题
- 兼容 `notion-client 2.7.0` API 变更（改用 raw HTTP requests）
- 移除 `notion.databases.query` 等已废弃方法调用
- Tags 仅在数据库存在 Multi-select 类型的 `Tags`/`标签` 属性时写入
- 修复页面正文、图片、视频封面仍调用旧 SDK 导致内容块丢失的问题
- 同步前读取 Notion 数据库 schema，只写入实际存在且类型匹配的字段
- 真实抓取失败时不再回落到 mock 数据，避免把示例数据写入 Notion

### 技术细节
- 新增 `_notion_request()` 辅助函数封装 Notion API 调用
- `find_existing_page_id_by_url()` 改用 raw POST 请求
- `create_notion_page_with_content()` 根据数据库 schema 构造字段，并用 raw API 追加内容块
- `upload_video_to_notion_api()` 改用 raw PATCH 请求
- `Created Date` 如果是 Notion `created_time` 自动字段，不会被手动写入；需要小红书发布日期时应新增 `Publish Date` Date 字段

---

## 2026-05-26 - CloakBrowser 集成

### 新增功能
- 集成 CloakBrowser 替代 Playwright 作为浏览器自动化方案
- 58 个 C++ 源码级补丁，通过所有 bot 检测测试
- `humanize=True` 启用人类行为模拟（贝塞尔曲线鼠标、逐字输入）
- 持久化 browser profile 保持登录状态
- reCAPTCHA v3 评分从 0.1 提升到 0.9

### Bug 修复
- 修复 Notion API `Created Date` 属性验证错误（属性不存在时跳过）
- 修复 `notion.py` 变量名冲突（`item` → `c`）
- 添加 `import traceback` 修复 NameError
- 添加 Notion API 请求超时（30s/60s）防止卡死
- 移除未使用的 `load_cookies` 函数和 `download_cover_image` 导入

### 项目清理
- 删除过期备份文件（`.bak`, `.original`, `.old_backup`, `.new`）
- 删除 `archive/` 目录（旧前端代码）

### 配置变更
- 新增 `CLOAKBROWSER_HUMANIZE` 环境变量（默认 true）
- 新增 `CLOAKBROWSER_PROFILE_DIR` 环境变量
- 更新 Dockerfile 基础镜像为 `cloakhq/cloakbrowser`
- 更新 `.gitignore` 添加 `browser_profile/`

### 文件变更
- `app/xhs.py` - 替换 Playwright 为 CloakBrowser
- `app/notion.py` - 修复 API 调用和导入
- `app/config.py` - 添加 CloakBrowser 配置
- `get_cookies.py` - 使用 CloakBrowser
- `requirements.txt` - 添加 cloakbrowser 依赖
- `Dockerfile` - 更新基础镜像
- `README.md` - 更新安装和配置说明
- `scripts/*.command` - 更新为 CloakBrowser

### 部署建议
- 推荐本地运行（住宅 IP，低风控风险）
- 不建议 Docker 部署（服务器 IP 高风控风险）
- 使用 Raycast 脚本快速触发同步
- 不需要前端（Raycast + Notion 足够）
