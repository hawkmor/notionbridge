# 使用 CloakBrowser 官方 Docker 镜像（已预装 stealth Chromium 和所有依赖）
FROM cloakhq/cloakbrowser

WORKDIR /app

# 安装项目依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p data/downloaded_videos data/downloaded_covers logs browser_profile

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV USE_REAL_SCRAPER=true
ENV HEADLESS_MODE=true
ENV CLOAKBROWSER_HUMANIZE=true

# 默认运行同步逻辑
CMD ["python", "app/main.py"]
