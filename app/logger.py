"""
User-friendly logging utility for Xiaohongshu to Notion sync.

Log Levels:
- user: Only show status summaries and critical info (default)
- debug: Show sync flow and important steps
- verbose: Show all technical details
"""

import os
from enum import Enum
from typing import Optional, List
from collections import deque
from app.config import Config
from datetime import datetime


class LogLevel(Enum):
    USER = "user"
    DEBUG = "debug"
    VERBOSE = "verbose"


class Logger:
    """Centralized logger with level control and log queue for frontend."""
    
    def __init__(self):
        # Allow runtime override via env var (useful for Raycast/Warp)
        level_str = os.getenv("LOG_LEVEL") or os.getenv("NOTIONBRIDGE_LOG_LEVEL") or Config.LOG_LEVEL
        try:
            self.level = LogLevel(level_str)
        except ValueError:
            self.level = LogLevel.USER
        
        # Log queue for frontend (max 100 recent logs)
        self.log_queue = deque(maxlen=100)
        self.enable_queue = False  # Only enable when daemon is running
    
    def _add_to_queue(self, message: str, level: str):
        """Add log to queue for frontend retrieval."""
        if self.enable_queue:
            self.log_queue.append({
                'timestamp': datetime.now().isoformat(),
                'level': level,
                'message': message
            })
    
    def user(self, message: str):
        """Always shown - critical user-facing messages."""
        print(message)
        self._add_to_queue(message, 'user')
    
    def debug(self, message: str):
        """Shown in debug and verbose modes."""
        if self.level in [LogLevel.DEBUG, LogLevel.VERBOSE]:
            print(message)
        # Always add to queue (frontend can filter)
        self._add_to_queue(message, 'debug')
    
    def verbose(self, message: str):
        """Only shown in verbose mode."""
        if self.level == LogLevel.VERBOSE:
            print(message)
        # Don't add verbose logs to queue (too noisy for frontend)
    
    def get_recent_logs(self, count: int = 50) -> List[dict]:
        """Get recent logs for frontend display."""
        logs = list(self.log_queue)
        return logs[-count:] if len(logs) > count else logs
    
    def clear_logs(self):
        """Clear log queue."""
        self.log_queue.clear()
    
    def sync_summary(self, added: int, skipped: int, failed: int):
        """Print unified sync status summary."""
        print()  # Blank line for separation
        
        if failed > 0 and added == 0:
            # Complete failure
            self.user("❌ 同步失败")
            self.user("检测到登录或网络问题。")
            self.user("请检查凭据后重试。")
        
        elif failed > 0:
            # Partial failure
            self.user("⚠️ 同步完成,有少量问题")
            self.user(f"已添加 {added} 条,跳过 {skipped} 条,失败 {failed} 条。")
            self.user("如需要可稍后重试。")
        
        elif added > 0:
            # Success with new items
            self.user("✨ 同步完成")
            if skipped > 0:
                self.user(f"已添加 {added} 条,跳过 {skipped} 条,失败 {failed} 条。")
            else:
                self.user(f"已添加 {added} 条新内容到你的 Notion 数据库。")
        
        else:
            # No new items (still report what happened)
            self.user("✨ 同步完成")
            if skipped > 0:
                self.user(f"无新增内容。已跳过 {skipped} 条(已存在/已同步),失败 {failed} 条。")
            else:
                self.user("你的 Notion 数据库已是最新状态,无需任何操作。")
        
        print()  # Blank line after summary


# Global logger instance
logger = Logger()
