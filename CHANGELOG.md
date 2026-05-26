# Changelog

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
- 删除 `REFACTORING_PLAN.md`（过时的重构计划）
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
