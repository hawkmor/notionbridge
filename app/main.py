import os
import sys
import json


# Add project root AND app directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from xhs import fetch_xhs_favorites
    from notion import push_to_notion
    from logger import logger
except ImportError:
    from app.xhs import fetch_xhs_favorites
    from app.notion import push_to_notion
    from app.logger import logger

def _as_bool(v, default=False):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _pick(d, keys):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _compact_item(item):
    """Return a compact, privacy-safe dict for debugging ordering / missing items."""
    if not isinstance(item, dict):
        return {"type": type(item).__name__}

    note_id = _pick(item, ["note_id", "id", "xhs_id", "item_id", "nid"]) 
    title = _pick(item, ["title", "desc", "description", "content"]) 
    url = _pick(item, ["url", "link", "note_url", "share_url"]) 
    # Try a few common time fields; keep raw value to avoid wrong parsing assumptions
    t = _pick(item, ["favorite_time", "fav_time", "collect_time", "collected_at", "create_time", "publish_time", "time", "timestamp"]) 

    compact = {
        "note_id": note_id,
        "title": (str(title)[:60] + "…") if title and len(str(title)) > 60 else title,
        "url": url,
        "time": t,
    }
    # Drop empty keys
    return {k: v for k, v in compact.items() if v not in (None, "")}


def _log_favorites_debug(favorites):
    """Log a small sample of scraped items to diagnose missing/ordering issues."""
    try:
        n = len(favorites) if favorites else 0
        logger.debug(f"🧾 Favorites debug: total={n}")
        if not favorites:
            return

        # Detect duplicates by note_id if present
        ids = []
        for it in favorites:
            cid = _pick(it, ["note_id", "id", "xhs_id", "item_id", "nid"]) if isinstance(it, dict) else None
            if cid:
                ids.append(str(cid))
        if ids:
            dup = len(ids) - len(set(ids))
            if dup > 0:
                logger.debug(f"⚠️ Favorites debug: duplicates detected by id: {dup}")

        head = [_compact_item(x) for x in favorites[:3]]
        tail = [_compact_item(x) for x in favorites[-3:]] if n > 3 else []
        logger.debug("🧾 Favorites debug: head=" + json.dumps(head, ensure_ascii=False))
        if tail:
            logger.debug("🧾 Favorites debug: tail=" + json.dumps(tail, ensure_ascii=False))
    except Exception as e:
        logger.debug(f"⚠️ Favorites debug logging failed: {e}")

def run_sync_logic(incremental=True, log_callback=None):
    """
    Main orchestration logic, can be called by CLI or Web UI.
    """
    # Allow forcing a full resync/backfill when incremental sync misses items
    # Set FULL_SYNC=1 to disable incremental mode.
    full_sync = _as_bool(os.getenv("FULL_SYNC"), default=False)
    incremental = False if full_sync else incremental

    def _log(msg, level="info"):
        # Still support log_callback for web UI
        if log_callback:
            log_callback(msg, level)
    
    # User-level: Simple start message
    logger.user("🔄 开始同步...")
    
    # 1. Fetch favorites
    try:
        logger.debug("🔍 抓取小红书收藏...")
        favorites = fetch_xhs_favorites()
        
        _log_favorites_debug(favorites)
        
        if not favorites:
            logger.user("❌ 同步失败")
            logger.user("未找到任何内容,请检查配置。")
            _log("⚠️ No items found", "error")
            return False
        
        logger.debug(f"  ✓ 找到 {len(favorites)} 个笔记")
        _log(f"✅ Found {len(favorites)} items")
        
    except Exception as e:
        logger.user("❌ 同步失败")
        logger.user("抓取小红书时出错,请检查 Cookies 是否有效。")
        logger.debug(f"Error: {e}")
        _log(f"❌ Error fetching from XHS: {e}", "error")
        return False

    # 2. Push to Notion
    try:
        logger.debug("📤 同步到 Notion...")
        
        logger.debug(f"⚙️ Notion sync mode: incremental={incremental}")
        success_count, skip_count, fail_count = push_to_notion(
            favorites,
            incremental=incremental,
            log_callback=log_callback,
        )
        
        # Print unified summary
        logger.sync_summary(success_count, skip_count, fail_count)
        
        _log(f"🏁 Sync completed. {success_count} new items added.")
        return fail_count == 0
        
    except Exception as e:
        logger.user("❌ 同步失败")
        logger.user("同步到 Notion 时出错,请检查 API 配置。")
        logger.debug(f"Error: {e}")
        _log(f"❌ Error syncing to Notion: {e}", "error")
        import traceback
        logger.verbose(traceback.format_exc())
        return False

def main():
    # Config is loaded on import or by web_app
    inc = True
    if any(arg in ("--full", "--backfill") for arg in sys.argv[1:]):
        inc = False
    ok = run_sync_logic(incremental=inc)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
