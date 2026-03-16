import os
import json
import asyncio
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import set_key
from app.config import Config

# Add project root AND app directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import internal modules
# Note: we assume app.xhs and app.main work because we are running as a module 'app.web_app'
# But if running as script, we need care. Use relative imports if possible or path hacks.
try:
    from app.xhs import interactive_login
    from app.main import run_sync_logic
except ImportError:
    # Fallback shouldn't be needed with correct path
    from app.xhs import interactive_login
    from app.main import run_sync_logic

app = FastAPI()

# Configuration storage
ENV_PATH = Config.ENV_PATH

class SyncConfig(BaseModel):
    NOTION_API_KEY: Optional[str] = None
    NOTION_DATABASE_ID: Optional[str] = None
    XHS_BOARD_URL: Optional[str] = None
    XHS_COOKIES: Optional[str] = None # JSON string

@app.get("/api/config")
async def get_config():
    """Get current configuration with masked secrets."""
    Config.reload()
    
    # Get values with empty string defaults (never None)
    api_key = Config.NOTION_API_KEY
    db_id = Config.NOTION_DATABASE_ID
    board_url = Config.XHS_BOARD_URL
    
    # Mask secrets if they exist
    if api_key and len(api_key) > 6:
        api_key = api_key[:3] + "*" * (len(api_key) - 6) + api_key[-3:]
    
    if db_id and len(db_id) > 6:
        db_id = db_id[:3] + "*" * (len(db_id) - 6) + db_id[-3:]
    
    # Check for cookies
    has_cookies = False
    masked_cookies = ""
    if os.path.exists(Config.COOKIE_FILE):
        try:
            with open(Config.COOKIE_FILE, 'r') as f:
                cookies = json.load(f)
                if cookies and len(cookies) > 0:
                    has_cookies = True
                    masked_cookies = "********"
        except Exception as e:
            print(f"Warning: Failed to load cookies.json: {e}")
    
    return {
        "NOTION_API_KEY": api_key,
        "NOTION_DATABASE_ID": db_id,
        "XHS_BOARD_URL": board_url,
        "XHS_COOKIES": masked_cookies,
        "HAS_COOKIES": has_cookies
    }

@app.post("/api/config")
async def update_config(config: SyncConfig):
    """Update configuration. Skips masked values (containing asterisks)."""
    try:
        # Only save if value is provided and NOT masked (doesn't contain *)
        if config.NOTION_API_KEY and '*' not in config.NOTION_API_KEY:
            set_key(ENV_PATH, "NOTION_API_KEY", config.NOTION_API_KEY)
        if config.NOTION_DATABASE_ID and '*' not in config.NOTION_DATABASE_ID:
            set_key(ENV_PATH, "NOTION_DATABASE_ID", config.NOTION_DATABASE_ID)
        if config.XHS_BOARD_URL and '*' not in config.XHS_BOARD_URL:
            set_key(ENV_PATH, "XHS_BOARD_URL", config.XHS_BOARD_URL)
        
        # Only update cookies if provided and valid (not empty string or masked)
        if config.XHS_COOKIES and '*' not in config.XHS_COOKIES:
            try:
                cookies_data = config.XHS_COOKIES
                if isinstance(cookies_data, str):
                    cookies_data = json.loads(cookies_data)
                with open(Config.COOKIE_FILE, 'w') as f:
                    json.dump(cookies_data, f, indent=2)
            except json.JSONDecodeError:
                pass # Ignore invalid json, might be masked string sent back
                
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/login")
async def trigger_login():
    """Triggers interactive login flow (desktop only)"""
    try:
        # Run in thread executor to not block async loop
        success = await asyncio.to_thread(interactive_login)
        if success:
            return {"status": "ok", "message": "Login successful"}
        else:
             return {"status": "error", "message": "Login failed or timed out"}
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cookies/manual")
async def save_manual_cookies(data: dict):
    """Save manually pasted cookies (for mobile/remote users)"""
    cookies_text = data.get("cookies")
    if not cookies_text:
        raise HTTPException(status_code=400, detail="Cookies are required")
    
    try:
        # Parse cookies (support both JSON array and JSON string)
        if isinstance(cookies_text, str):
            cookies_data = json.loads(cookies_text)
        else:
            cookies_data = cookies_text
        
        # Validate it's a list
        if not isinstance(cookies_data, list):
            raise ValueError("Cookies must be a JSON array")
        
        # Save to cookies.json
        with open(Config.COOKIE_FILE, 'w') as f:
            json.dump(cookies_data, f, indent=2)
        
        # Automatically verify the cookies
        from app.web_app import verify_xhs
        verification = await verify_xhs({"cookies": json.dumps(cookies_data)})
        
        return {
            "status": "ok",
            "message": "Cookies saved successfully",
            "verification": verification
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save cookies: {str(e)}")

@app.post("/api/verify/notion")
async def verify_notion(data: dict):
    """Verify Notion connection using saved credentials from .env file."""
    # Force reload .env to get latest values
    Config.reload()
    
    # Always read from environment (credentials are already saved there)
    api_key = Config.NOTION_API_KEY
    db_id = Config.NOTION_DATABASE_ID
    
    if not api_key:
        return {"status": "error", "message": "Notion API Key 未配置"}
    if not db_id:
        return {"status": "error", "message": "Notion Database ID 未配置"}
    
    try:
        from notion_client import Client
        notion = Client(auth=api_key)
        # Try to retrieve database to verify both API key and database ID
        db = notion.databases.retrieve(database_id=db_id)
        db_title = db.get('title', [{}])[0].get('plain_text', 'Untitled')
        return {"status": "ok", "message": f"已连接到数据库: {db_title}"}
    except Exception as e:
        error_msg = str(e)
        if "unauthorized" in error_msg.lower():
            return {"status": "error", "message": "API Key 无效"}
        elif "not_found" in error_msg.lower() or "could not find" in error_msg.lower():
            return {"status": "error", "message": "数据库未找到 - 请检查 Database ID"}
        else:
            return {"status": "error", "message": f"连接失败: {error_msg}"}

@app.post("/api/verify/xhs")
async def verify_xhs(data: dict):
    cookies_str = data.get("cookies")
    # If no cookies provided, try reading from file (support validating stored cookies)
    if not cookies_str and os.path.exists(Config.COOKIE_FILE):
        with open(Config.COOKIE_FILE, 'r') as f:
            cookies_str = f.read()
            
    if not cookies_str:
        raise HTTPException(status_code=400, detail="Cookies are required")
    
    try:
        if isinstance(cookies_str, str):
            cookies_data = json.loads(cookies_str)
        else:
            cookies_data = cookies_str

        # Briefly check if cookies work using playwright
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_cookies(cookies_data)
            page = await context.new_page()
            # Navigate to a simple page that requires login or shows profile
            await page.goto("https://www.xiaohongshu.com/explore", timeout=15000)
            # Check for profile or logout indicator
            is_logged_in = await page.query_selector('[class*="user-icon"], [class*="avatar"]')
            await browser.close()
            
            if is_logged_in:
                return {"status": "ok", "message": "小红书 Cookies 验证成功"}
            else:
                return {"status": "error", "message": "Cookies 可能已失效或不完整"}
    except Exception as e:
        return {"status": "error", "message": f"验证出错: {str(e)}"}

# ============================================================================
# Background Sync Daemon Endpoints (New)
# ============================================================================

@app.post("/api/daemon/start")
async def start_daemon(data: dict = None):
    """Start background sync daemon."""
    from app.daemon import daemon
    
    incremental = True
    if data:
        incremental = data.get("incremental", True)
    
    result = daemon.start(incremental=incremental)
    return result

@app.post("/api/daemon/stop")
async def stop_daemon():
    """Stop background sync daemon."""
    from app.daemon import daemon
    
    result = daemon.stop()
    return result

@app.get("/api/daemon/status")
async def get_daemon_status():
    """Get current daemon status."""
    from app.daemon import daemon
    
    status = daemon.get_status()
    return status

@app.get("/api/daemon/logs")
async def get_daemon_logs(count: int = 50):
    """Get recent daemon logs for frontend display."""
    from logger import logger
    
    logs = logger.get_recent_logs(count=count)
    return {"logs": logs}

@app.post("/api/history/clear")
async def clear_sync_history():
    """Clear the sync history file (synced_ids.json)."""
    try:
        if os.path.exists(Config.SYNCED_IDS_FILE):
            os.remove(Config.SYNCED_IDS_FILE)
            return {"status": "ok", "message": "History cleared"}
        else:
            return {"status": "ok", "message": "History already empty"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Chat API Endpoint (CodeX)
# ============================================================================

class ChatRequest(BaseModel):
    message: str
    history: Optional[list] = None

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """AI chat endpoint for CodeX interface."""
    try:
        user_message = request.message
        history = request.history or []
        
        # 简单的响应逻辑（可以后续集成真实的 AI 服务）
        # 这里先实现一个基础的助手功能
        response_text = ""
        
        # 检查是否是系统相关的问题
        user_lower = user_message.lower()
        
        if any(keyword in user_lower for keyword in ['状态', 'status', '运行', 'running']):
            from app.daemon import daemon
            status = daemon.get_status()
            if status.get('running'):
                response_text = f"✅ 同步守护进程正在运行中\n\n📊 状态信息：\n- 运行状态：运行中\n- 同步周期：{status.get('cycle_count', 0)}\n- 最后同步：{status.get('last_sync', 'N/A')}\n- 下次同步：{status.get('next_sync', 'N/A')}"
            else:
                response_text = "⏸️ 同步守护进程当前未运行。您可以通过前端界面启动同步。"
        elif any(keyword in user_lower for keyword in ['帮助', 'help', '功能', 'feature']):
            response_text = """🤖 CodeX AI 助手

我可以帮助您：
- 查看同步状态（输入"状态"或"status"）
- 查看配置信息（输入"配置"或"config"）
- 获取使用帮助（输入"帮助"或"help"）

更多功能正在开发中..."""
        elif any(keyword in user_lower for keyword in ['配置', 'config', '设置']):
            Config.reload()
            has_cookies = os.path.exists(Config.COOKIE_FILE)
            response_text = f"""⚙️ 当前配置信息：

- Notion API Key: {'已配置' if Config.NOTION_API_KEY else '未配置'}
- Notion Database ID: {'已配置' if Config.NOTION_DATABASE_ID else '未配置'}
- 小红书收藏夹链接: {'已配置' if Config.XHS_BOARD_URL else '未配置'}
- Cookies: {'已配置' if has_cookies else '未配置'}

您可以通过前端界面修改这些配置。"""
        else:
            response_text = f"我收到了您的消息：{user_message}\n\n目前我还在学习中，您可以尝试问我：\n- \"状态\" - 查看同步状态\n- \"配置\" - 查看配置信息\n- \"帮助\" - 获取帮助信息"
        
        return {
            "status": "ok",
            "response": response_text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"处理请求时出错: {str(e)}"
        }

# ============================================================================
# Legacy EventSource Sync (Deprecated - kept for compatibility)
# ============================================================================


# Serve React Frontend
# Get project root directory dynamically
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "dist")

if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    print(f"WARNING: React build directory not found at {STATIC_DIR}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2522)
