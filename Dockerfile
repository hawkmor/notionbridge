# 使用 Playwright 官方提供的 Python 运行环境（已预装所有浏览器依赖）
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 安装项目依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p data/downloaded_videos data/downloaded_covers logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV USE_REAL_SCRAPER=true
ENV HEADLESS_MODE=true

# 默认运行同步逻辑
CMD ["python", "app/main.py"]
