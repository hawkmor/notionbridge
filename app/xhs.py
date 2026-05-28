import os
import json
import time
import random
from urllib.parse import urlparse, quote
from typing import List, Dict, Optional
from cloakbrowser import launch, launch_persistent_context
try:
    from logger import logger
except ImportError:
    from app.logger import logger
from app.config import Config

# Cookie storage file
COOKIE_FILE = Config.COOKIE_FILE


def save_cookies(page):
    """Save browser cookies to file for session persistence."""
    cookies = page.context.cookies()
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    logger.verbose(f"✅ Cookies saved to {COOKIE_FILE}")

def interactive_login(timeout: int = 300) -> bool:
    """
    Launches a headed CloakBrowser for the user to log in manually.
    Polls for login success (cookies/local storage) and saves cookies.
    Returns True if login was successful.
    """
    print("\n" + "="*50)
    logger.user("🔐 STARTING INTERACTIVE LOGIN (CloakBrowser)")
    logger.user("="*50)
    
    try:
        # Use persistent context for better anti-detection and session persistence
        profile_dir = os.path.abspath(Config.CLOAKBROWSER_PROFILE_DIR)
        os.makedirs(profile_dir, exist_ok=True)
        
        context = launch_persistent_context(
            profile_dir,
            headless=False,
            humanize=Config.CLOAKBROWSER_HUMANIZE,
            viewport={'width': 1280, 'height': 800},
        )
        page = context.new_page()
        
        # Load existing cookies if available
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                print(f"✅ Loaded cookies from {COOKIE_FILE}")
            except Exception as e:
                logger.verbose(f"⚠️ Failed to load cookies: {e}")
        
        logger.verbose("🚀 Navigating to Xiaohongshu...")
        page.goto("https://www.xiaohongshu.com")
        
        logger.user(f"⏳ Waiting for login (timeout: {timeout}s)...")
        start_time = time.time()
        is_logged_in = False
        
        while time.time() - start_time < timeout:
            # Check for login indicators
            try:
                # 1. Check data-logged attribute
                logged_val = page.get_attribute("#global", "data-logged")
                
                # 2. Check for avatar/user icon
                user_icon = page.query_selector('[class*="user-icon"], [class*="avatar"]')
                
                # 3. Check for cookies directly
                cookies = context.cookies()
                sid_cookie = next((c for c in cookies if c["name"] == "web_session"), None)
                
                if logged_val == "1" or user_icon or sid_cookie:
                    logger.user("✅ Login detected!")
                    # Wait a moment for fully settled state
                    page.wait_for_timeout(2000)
                    save_cookies(page)
                    is_logged_in = True
                    break
                    
                # Check if user closed the browser
                if page.is_closed():
                    logger.user("⚠️ Browser closed by user")
                    break
                    
            except Exception:
                # Page might be closed or navigating
                if page.is_closed():
                    break
                pass
            
            time.sleep(1)
        
        if not is_logged_in and not page.is_closed():
            logger.user("⏰ Login timed out")
        
        try:
            context.close()
        except:
            pass
            
        return is_logged_in
        
    except Exception as e:
        logger.user(f"❌ Error during interactive login: {e}")
        return False


from app.xhs_selectors import SELECTORS

def _try_selectors(root, selector_list, all=False):
    """Helper to try multiple selectors until one works."""
    if isinstance(selector_list, str):
        selector_list = [selector_list]
    
    for sel in selector_list:
        try:
            if all:
                elems = root.query_selector_all(sel)
                if elems: return elems
            else:
                elem = root.query_selector(sel)
                if elem: return elem
        except:
            continue
    return [] if all else None


def _clean_author_text(text: str) -> str:
    """Normalize author text extracted from XHS profile links."""
    if not text:
        return ""

    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return ""

    ignored = {
        "关注", "已关注", "粉丝", "获赞与收藏", "小红书号", "作者",
        "赞", "收藏", "评论", "分享",
    }
    for line in lines:
        if line in ignored:
            continue
        if line.startswith("@"):
            line = line[1:].strip()
        if line:
            return line[:200]

    return ""


def _extract_author(modal) -> str:
    """Extract author from the note modal with profile-link fallbacks."""
    author_elem = _try_selectors(modal, SELECTORS["author"])
    author = _clean_author_text(author_elem.inner_text()) if author_elem else ""
    if author:
        return author

    profile_links = _try_selectors(modal, 'a[href*="/user/profile/"]', all=True)
    for link in profile_links:
        try:
            author = _clean_author_text(link.inner_text())
            if author:
                return author
        except Exception:
            continue

    # Some XHS builds put the visible nickname near the avatar but outside the anchor text.
    profile_containers = _try_selectors(
        modal,
        [
            '[class*="author"]',
            '[class*="user"]',
            '[class*="creator"]',
            '[class*="nickname"]',
        ],
        all=True,
    )
    for elem in profile_containers:
        try:
            author = _clean_author_text(elem.inner_text())
            if author:
                return author
        except Exception:
            continue

    return ""

def _first_cover_url(cover: Dict) -> str:
    """Return the best usable cover URL from XHS API cover data."""
    if not isinstance(cover, dict):
        return ""
    for key in ("url_default", "urlDefault", "url_pre", "urlPre", "url"):
        value = cover.get(key)
        if value:
            return value
    for item in cover.get("info_list") or cover.get("infoList") or []:
        if isinstance(item, dict) and item.get("url"):
            return item["url"]
    return ""


def _note_id_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "explore":
        return parts[-1]
    return ""


def _board_id_from_url(board_url: str) -> str:
    parsed = urlparse(board_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "board":
        return parts[-1]
    return ""


def _normalize_api_note(raw_note: Dict) -> Optional[Dict]:
    """Convert XHS board API note data into a stable summary object."""
    if not isinstance(raw_note, dict):
        return None

    note_id = raw_note.get("noteId") or raw_note.get("note_id")
    if not note_id:
        return None

    xsec_token = raw_note.get("xsecToken") or raw_note.get("xsec_token") or ""
    clean_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    detail_url = clean_url
    if xsec_token:
        detail_url = f"{clean_url}?xsec_token={quote(xsec_token, safe='')}&xsec_source=pc_collect"

    user = raw_note.get("user") or {}
    return {
        "note_id": note_id,
        "title": raw_note.get("displayTitle") or raw_note.get("display_title") or "Untitled",
        "url": clean_url,
        "detail_url": detail_url,
        "author": user.get("nickName") or user.get("nick_name") or "",
        "cover_image": _first_cover_url(raw_note.get("cover") or {}),
        "type": raw_note.get("type", ""),
    }


def _fetch_board_note_summaries(page, board_url: str) -> List[Dict]:
    """
    Fetch board notes from XHS initial state plus the board/note pagination API.

    The board grid is virtualized, so DOM element count is not a reliable item count.
    """
    board_id = _board_id_from_url(board_url)
    if not board_id:
        logger.debug("  ⚠️ Could not parse board id from XHS_BOARD_URL")
        return []

    feed = None
    try:
        # The first page is SSR-hydrated into HTML. Reading it from HTML is more
        # reliable than reading Vue's reactive proxy from Playwright.
        html = page.content()
        marker = f'"{board_id}":{{"cursor"'
        marker_index = html.find(marker)
        if marker_index >= 0:
            start = html.find("{", marker_index + len(f'"{board_id}":') - 1)
            if start >= 0:
                feed, _ = json.JSONDecoder().raw_decode(html[start:])
    except Exception as e:
        logger.debug(f"  ⚠️ Failed to parse XHS initial board state: {e}")

    if not feed or not feed.get("notes"):
        logger.debug("  ⚠️ XHS initial board state missing; falling back to DOM scraping")
        return []

    api_notes: List[Dict] = []
    api_pages = 0
    api_has_more = bool(feed.get("hasMore"))

    def capture_board_notes(response):
        nonlocal api_pages, api_has_more
        try:
            if "/api/sns/web/v1/board/note" not in response.url:
                return
            payload = response.json()
            data = payload.get("data") or {}
            batch = data.get("notes") or []
            if batch:
                api_notes.extend(batch)
            api_pages += 1
            api_has_more = bool(data.get("has_more"))
            logger.verbose(
                f"   API page {api_pages}: {len(batch)} notes "
                f"(has_more={api_has_more})"
            )
        except Exception as e:
            logger.verbose(f"   ⚠️ Failed to read board/note response: {e}")

    page.on("response", capture_board_notes)

    max_api_scrolls = int(os.getenv("XHS_API_SCROLLS", "80"))
    stable_needed = int(os.getenv("XHS_API_STABLE_ROUNDS", "8"))
    stable_rounds = 0
    last_seen_count = len(feed.get("notes") or [])

    for i in range(max_api_scrolls):
        try:
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.2)")
            page.wait_for_timeout(1200)
        except Exception as e:
            logger.verbose(f"   ⚠️ API scroll {i+1} failed: {e}")
            page.wait_for_timeout(800)

        current_seen_count = len(feed.get("notes") or []) + len(api_notes)
        if current_seen_count > last_seen_count:
            stable_rounds = 0
            last_seen_count = current_seen_count
            logger.verbose(f"   API scroll {i+1}/{max_api_scrolls}: {current_seen_count} notes seen")
        else:
            stable_rounds += 1

        at_bottom = False
        try:
            at_bottom = page.evaluate(
                "() => Math.ceil(window.scrollY + window.innerHeight) >= document.documentElement.scrollHeight - 4"
            )
        except Exception:
            pass

        if stable_rounds >= stable_needed and (at_bottom or not api_has_more):
            break

    seen = set()
    summaries = []
    all_notes = list(feed.get("notes") or []) + api_notes
    for raw_note in all_notes:
        summary = _normalize_api_note(raw_note)
        if not summary or summary["note_id"] in seen:
            continue
        seen.add(summary["note_id"])
        summaries.append(summary)

    logger.debug(
        f"  ✓ Board API collected {len(summaries)} unique notes "
        f"(pages={api_pages}, has_more={api_has_more})"
    )
    return summaries


def _extract_note_from_root(page, root, fallback: Optional[Dict] = None) -> Dict:
    """Extract note data from an already-open note detail page or modal."""
    fallback = fallback or {}

    url = fallback.get("url") or page.url.split("?")[0]
    if "/explore/" not in url:
        link_elem = root.query_selector('a[href*="/explore/"]') if root else None
        if link_elem:
            href = link_elem.get_attribute("href")
            url = f"https://www.xiaohongshu.com{href}" if href.startswith("/") else href
            url = url.split("?")[0]

    title_elem = _try_selectors(root, SELECTORS["title"])
    title = title_elem.inner_text().strip() if title_elem else fallback.get("title", "Untitled")

    author = _extract_author(root) or fallback.get("author", "")

    content = []
    desc_area = _try_selectors(root, SELECTORS["desc"])
    if desc_area:
        text_lines = desc_area.inner_text().split("\n")
        for line in text_lines:
            clean_line = line.strip()
            if clean_line:
                content.append({"type": "text", "content": clean_line})

    img_elements = _try_selectors(root, SELECTORS["image"], all=True)
    seen_urls = set()
    for img in img_elements:
        try:
            is_duplicate = img.evaluate("el => el.closest('.swiper-slide-duplicate') !== null")
            if is_duplicate:
                continue
            src = img.get_attribute("src")
            if not src or "avatar" in src.lower():
                continue
            clean_img_url = src.split("?")[0]
            if clean_img_url not in seen_urls:
                content.append({"type": "image", "url": clean_img_url})
                seen_urls.add(clean_img_url)
        except Exception:
            continue

    fallback_cover = fallback.get("cover_image", "")
    if fallback_cover and not any(c.get("type") == "image" for c in content):
        content.append({"type": "image", "url": fallback_cover})

    tags = []
    tag_elems = _try_selectors(root, SELECTORS["tags"], all=True)
    if tag_elems:
        tags = [t.inner_text().strip().replace("#", "") for t in tag_elems if t.inner_text().strip()]

    date_elem = _try_selectors(root, SELECTORS["date"])
    created_date = date_elem.inner_text().strip() if date_elem else ""

    return {
        "title": title,
        "url": url,
        "author": author,
        "created_date": created_date,
        "content": content,
        "tags": list(set(tags)),
        "cover_image": next((c["url"] for c in content if c["type"] == "image"), fallback_cover),
    }


def scrape_note_from_modal(page, item_element, captured_video_urls: List[str] = None) -> Dict:
    """
    Extract content from Xiaohongshu note modal/popup with improved robustness.
    """
    try:
        # Click the item to open modal
        logger.verbose(f"  📄 Clicking item to open modal...")
        item_element.click()
        
        # Smart wait for modal
        modal = None
        for sel in SELECTORS["modal_container"]:
            try:
                modal = page.wait_for_selector(sel, state="visible", timeout=5000)
                if modal: break
            except:
                continue
        
        if not modal:
            logger.verbose(f"    ⚠️ Modal container not detected via primary selectors")
            # Fallback to general dialog/role check
            modal = page.query_selector('[role="dialog"], .note-detail-mask')
            
        if not modal:
            print(f"    ✗ Could not find modal container after clicking")
            return None
        
        logger.verbose(f"    ✓ Modal opened")
        page.wait_for_timeout(500) # Short breath for layout to settle

        note_data = _extract_note_from_root(page, modal)
        content = note_data["content"]

        # 5. Extract Media (Images & Video)
        # Use captured video URLs if available (most reliable for video)
        video_found = False
        if captured_video_urls:
            # Filter for real video URLs (usually sns-video-qc or similar)
            valid_videos = [u for u in captured_video_urls if '.mp4' in u or 'video' in u]
            if valid_videos:
                content.insert(0, {"type": "video", "url": valid_videos[-1]})
                video_found = True
                logger.verbose(f"    🎥 Video captured from network")

        # Fallback to scanning video tag
        if not video_found:
            video_tag = _try_selectors(modal, SELECTORS["video_tag"])
            if video_tag:
                v_src = video_tag.get_attribute('src')
                if v_src and not v_src.startswith('blob:'):
                    content.insert(0, {"type": "video", "url": v_src})
                    video_found = True
        
        # Images (with strict de-duplication)
        # Close Modal (Press ESC or Click)
        try:
            page.keyboard.press('Escape')
            # Wait for modal to disappear
            page.wait_for_timeout(300)
        except:
            close_btn = _try_selectors(modal, SELECTORS["close_button"])
            if close_btn: close_btn.click()

        note_data["content"] = content
        note_data["cover_image"] = next((c["url"] for c in content if c["type"] == "image"), "")
        return note_data
        
    except Exception as e:
        print(f"    ✗ Extraction Error: {e}")
        try: page.keyboard.press('Escape') 
        except: pass
        return None


def scrape_note_from_url(page, summary: Dict, captured_video_urls: List[str] = None) -> Optional[Dict]:
    """Open a note detail URL with xsec_token and extract its full content."""
    try:
        detail_url = summary.get("detail_url") or summary.get("url")
        page.goto(detail_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)

        root = None
        for sel in SELECTORS["modal_container"]:
            try:
                root = page.query_selector(sel)
                if root:
                    break
            except Exception:
                continue
        if not root:
            root = page.query_selector("main") or page.query_selector("#app") or page

        note_data = _extract_note_from_root(page, root, summary)
        content = note_data["content"]

        if captured_video_urls:
            valid_videos = [u for u in captured_video_urls if ".mp4" in u or "video" in u]
            if valid_videos and not any(c.get("type") == "video" for c in content):
                content.insert(0, {"type": "video", "url": valid_videos[-1]})
                logger.verbose("    🎥 Video captured from network")

        video_tag = _try_selectors(root, SELECTORS["video_tag"])
        if video_tag and not any(c.get("type") == "video" for c in content):
            v_src = video_tag.get_attribute("src")
            if v_src and not v_src.startswith("blob:"):
                content.insert(0, {"type": "video", "url": v_src})

        note_data["content"] = content
        note_data["url"] = summary.get("url") or note_data["url"]
        note_data["cover_image"] = next(
            (c["url"] for c in content if c["type"] == "image"),
            summary.get("cover_image", ""),
        )
        return note_data
    except Exception as e:
        print(f"    ✗ URL Extraction Error: {e}")
        return None


def scrape_board_items(page, board_url: str) -> List[Dict]:
    """
    Scrape items from a Xiaohongshu board/album.
    """
    print(f"🔍 Scraping board: {board_url}...")
    
    favorites = []
    
    # Set up video URL capture
    captured_video_urls = []
    
    def capture_video_request(response):
        """Capture video URLs from network responses."""
        try:
            url = response.url
            content_type = response.headers.get('content-type', '')
            # Look for .mp4 files from xhscdn
            if ('.mp4' in url and 'xhscdn.com' in url) or 'video/mp4' in content_type:
                if url not in captured_video_urls:
                    captured_video_urls.append(url)
                    print(f"    🎥 Captured video URL: {url[:80]}...")
        except:
            pass
    
    # Attach response listener
    page.on('response', capture_video_request)
    
    try:
        # Navigate to the board URL
        print(f"Navigating to board page...")
        page.goto(board_url)
        page.wait_for_timeout(3000)
        
        current_url = page.url
        print(f"Current URL: {current_url}")

        # Preferred path: use XHS board pagination API to avoid virtualized DOM loss.
        board_summaries = _fetch_board_note_summaries(page, board_url)
        if board_summaries:
            max_process = int(os.getenv("XHS_MAX_ITEMS", "200"))
            if len(board_summaries) > max_process:
                logger.verbose(f"ℹ️ Capping API notes to first {max_process} (from {len(board_summaries)})")
                board_summaries = board_summaries[:max_process]

            logger.debug(f"Found {len(board_summaries)} API notes, will fetch full content for each...\n")

            for idx, summary in enumerate(board_summaries):
                try:
                    print(f"\n[{idx+1}/{len(board_summaries)}] Processing item {idx+1}...")
                    captured_video_urls.clear()
                    note_data = scrape_note_from_url(page, summary, captured_video_urls)
                    if note_data:
                        favorites.append(note_data)
                    else:
                        print(f"    ⚠️ Skipping item {idx+1} (failed to extract)")

                    if idx < len(board_summaries) - 1:
                        wait_time = random.uniform(1.0, 2.0)
                        logger.verbose(f"    ⏳ Waiting {wait_time:.1f}s before next item...")
                        time.sleep(wait_time)
                except Exception as e:
                    print(f"  ⚠️ Failed to process item {idx}: {e}")
                    continue

            if favorites:
                logger.debug(f"✅ Successfully extracted {len(favorites)} favorites")
            else:
                print("⚠️ No valid items extracted from API note list")
            return favorites
        
        # Scroll to load lazy-loaded content
        logger.verbose("📜 Scrolling to load all items...")

        def _query_items():
            # Try a few common selectors; keep the first non-empty result
            selectors = [
                'section.note-item',
                'div.note-item',
                'section[class*="note-item"]',
                'a[href*="/explore/"]',
            ]
            for sel in selectors:
                elems = page.query_selector_all(sel)
                if elems:
                    return sel, elems
            return 'section.note-item', []

        # Some XHS pages scroll within a container instead of window
        scroll_container = page.query_selector('main') or page.query_selector('[class*="content"]')

        max_items = 0
        stable_rounds = 0
        max_scrolls = int(os.getenv('XHS_MAX_SCROLLS', '80'))
        stable_needed = int(os.getenv('XHS_STABLE_ROUNDS', '6'))

        # Step-scroll (more reliable than jumping to bottom)
        for i in range(max_scrolls):
            try:
                if scroll_container:
                    page.evaluate(
                        "(el) => { el.scrollTop = el.scrollTop + (window.innerHeight * 0.9); }",
                        scroll_container,
                    )
                else:
                    page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")

                # Allow network / DOM to settle
                try:
                    page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(1200)

                sel_used, current_items = _query_items()
                item_count = len(current_items)

                if item_count > max_items:
                    max_items = item_count
                    stable_rounds = 0
                    logger.verbose(f"   Scroll {i+1}/{max_scrolls}: {item_count} items loaded (selector={sel_used})")
                else:
                    stable_rounds += 1
                    logger.verbose(f"   Scroll {i+1}/{max_scrolls}: {item_count} items loaded (stable {stable_rounds}/{stable_needed}, selector={sel_used})")

                # If we haven't seen new items for a while, stop scrolling
                if stable_rounds >= stable_needed:
                    break

                # Occasionally scroll up a bit to trigger different lazy-load zones
                if i % 10 == 9:
                    if scroll_container:
                        page.evaluate(
                            "(el) => { el.scrollTop = Math.max(0, el.scrollTop - (window.innerHeight * 0.6)); }",
                            scroll_container,
                        )
                    else:
                        page.evaluate("window.scrollBy(0, -(window.innerHeight * 0.6))")
                    page.wait_for_timeout(800)

            except Exception as e:
                logger.verbose(f"   ⚠️ Scroll {i+1} failed: {e}")
                page.wait_for_timeout(800)

        logger.verbose(f"   ✓ Scrolling complete, max items found: {max_items}")
        
        # Find items using the same selector set as the scroller
        logger.verbose("🔎 Searching for items with different selectors...")

        items = []
        selector_used = None

        for sel in [
            'section.note-item',
            'div.note-item',
            'section[class*="note-item"]',
        ]:
            items = page.query_selector_all(sel)
            if items:
                selector_used = sel
                logger.verbose(f"✓ Found {len(items)} items using {sel} selector")
                break

        # Fallback: Generic links to /explore/ (wrap into clickable containers)
        if not items:
            links = page.query_selector_all('a[href*="/explore/"]')
            if links:
                logger.verbose(f"✓ Found {len(links)} explore links; wrapping into containers")
                parent_items = []
                for link in links:
                    try:
                        parent = link.evaluate_handle('el => el.closest("section, div, li")')
                        if parent:
                            el = parent.as_element()
                            if el:
                                parent_items.append(el)
                    except Exception:
                        continue
                # De-duplicate by JSHandle identity (best-effort)
                items = parent_items
                selector_used = 'a[href*="/explore/"] (wrapped)'

        # Hard cap to avoid huge runs (configurable)
        max_process = int(os.getenv('XHS_MAX_ITEMS', '200'))
        if len(items) > max_process:
            logger.verbose(f"ℹ️ Capping items to first {max_process} (from {len(items)})")
            items = items[:max_process]

        if not items:
            print("\n⚠️ No items found with any selector strategy.")
            logger.verbose("📋 Debugging: Current page structure...")

            # Timestamp for unique filenames
            timestamp = int(time.time())

            # Get project root logs directory
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logs_dir = os.path.join(project_root, 'logs')
            os.makedirs(logs_dir, exist_ok=True)

            # 1. Take Screenshot
            try:
                screenshot_path = os.path.join(logs_dir, f"debug_failed_scrape_{timestamp}.png")
                page.screenshot(path=screenshot_path, full_page=True)
                logger.user(f"📸 Debug screenshot saved to: {screenshot_path}")
            except Exception as e:
                logger.user(f"❌ Failed to save screenshot: {e}")

            # 2. Dump HTML
            try:
                html_path = os.path.join(logs_dir, f"debug_failed_scrape_{timestamp}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page.content())
                logger.user(f"📝 Debug HTML saved to: {html_path}")
            except Exception as e:
                logger.user(f"❌ Failed to save HTML dump: {e}")

            # Get main content area
            main_content = page.query_selector('main, #app, [class*="content"]')
            if main_content:
                html_snippet = main_content.inner_html()[:500]
                logger.verbose(f"Main content HTML (first 500 chars):\n{html_snippet}\n")

            logger.user("💡 Please check:")
            logger.user("   1. Are you on the favorites/collections page?")
            logger.user("   2. Do you have any saved items?")
            logger.user("   3. Try clicking on '收藏' or '专辑' tab manually")
            return []

        logger.debug(f"Found {len(items)} items (selector={selector_used}), will fetch full content for each...\n")
        
        for idx, item in enumerate(items):
            try:
                print(f"\n[{idx+1}/{len(items)}] Processing item {idx+1}...")
                
                # Clear captured URLs for this note
                captured_video_urls.clear()
                
                # Click item to open modal and extract content
                note_data = scrape_note_from_modal(page, item, captured_video_urls)
                
                if note_data:
                    # Add to favorites list
                    favorites.append(note_data)
                else:
                    print(f"    ⚠️ Skipping item {idx+1} (failed to extract)")
                
                # Rate limiting: wait between requests to avoid being blocked
                if idx < len(items) - 1:  # Don't wait after last item
                    wait_time = random.uniform(1.5, 3.0)  # Random delay
                    logger.verbose(f"    ⏳ Waiting {wait_time:.1f}s before next item...")
                    time.sleep(wait_time)
                
            except Exception as e:
                print(f"  ⚠️ Failed to process item {idx}: {e}")
                continue
        
        if favorites:
            logger.debug(f"✅ Successfully extracted {len(favorites)} favorites")
        else:
            print("⚠️ No valid items extracted")
        
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    return favorites

def fetch_xhs_favorites() -> List[Dict]:
    """
    Main function to fetch Xiaohongshu board items.
    Uses CloakBrowser with anti-detection for stealth scraping.
    """
    use_real = Config.USE_REAL_SCRAPER
    headless = Config.HEADLESS_MODE
    board_url = Config.XHS_BOARD_URL
    
    if not use_real:
        logger.verbose("ℹ️ Using MOCK data (set USE_REAL_SCRAPER=true in .env to use real scraper)")
        return get_mock_data()
    
    if not board_url:
        logger.user("❌ XHS_BOARD_URL not set in .env file")
        raise ValueError("XHS_BOARD_URL is required when USE_REAL_SCRAPER=true")
    
    logger.verbose(f"🚀 Starting CloakBrowser scraper for board: {board_url}")
    
    try:
        # Use persistent context for better anti-detection
        profile_dir = os.path.abspath(Config.CLOAKBROWSER_PROFILE_DIR)
        os.makedirs(profile_dir, exist_ok=True)
        
        context = launch_persistent_context(
            profile_dir,
            headless=headless,
            humanize=Config.CLOAKBROWSER_HUMANIZE,
            viewport={'width': 1280, 'height': 720},
        )
        
        # Load cookies from cookies.json into the persistent context
        if os.path.exists(Config.COOKIE_FILE):
            try:
                with open(Config.COOKIE_FILE, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                logger.verbose(f"✅ Loaded {len(cookies)} cookies from {Config.COOKIE_FILE}")
            except Exception as e:
                logger.verbose(f"⚠️ Failed to load cookies: {e}")
        
        page = context.new_page()
        
        # 1. Verify Login State
        logger.verbose("🔐 Verifying login state...")
        page.goto("https://www.xiaohongshu.com")
        page.wait_for_timeout(3000)
        
        # Check for data-logged attribute (1 = logged in)
        is_logged_in = page.evaluate('() => document.querySelector("#global")?.getAttribute("data-logged") == "1"')
        
        if not is_logged_in:
            logger.user("⚠️ Login verification FAILED")
            
            # Take debug screenshot to see what's happening
            os.makedirs("logs", exist_ok=True)
            screenshot_path = f"logs/login_failed_{int(time.time())}.png"
            page.screenshot(path=screenshot_path)
            logger.user(f"📸 Screenshot saved to {screenshot_path}")
            
            if headless:
                logger.user("❌ Running in HEADLESS mode, cannot perform interactive login.")
                logger.user("💡 Please run 'python get_cookies.py' on your local machine.")
                context.close()
                raise RuntimeError("Xiaohongshu login verification failed in headless mode")
            else:
                logger.user("🔄 Attempting interactive login...")
                context.close()
                if not interactive_login():
                    raise RuntimeError("Interactive login failed")
                return fetch_xhs_favorites() # Recursive retry
        
        # 2. Access the board and scrape
        favorites = scrape_board_items(page, board_url)
        context.close()
        
        return favorites
        
    except Exception as e:
        logger.user(f"❌ Scraper error: {e}")
        raise

def get_mock_data() -> List[Dict]:
    """Returns mock data for testing."""
    return [
        {
            "title": "家居装修灵感 | 极简主义客厅设计",
            "url": "https://www.xiaohongshu.com/explore/123456789",
            "description": "这是一篇关于如何在小户型中实现极简主义风格的笔记，包含家具选择和配色方案。",
            "cover_image": "https://example.com/image1.jpg"
        },
        {
            "title": "Python 爬虫实战：从入门到精通",
            "url": "https://www.xiaohongshu.com/explore/987654321",
            "description": "详细讲解 Python Playwright 的使用方法，适合新手入门。",
            "cover_image": "https://example.com/image2.jpg"
        },
        {
            "title": "周末好去处 | 北京小众咖啡馆推荐",
            "url": "https://www.xiaohongshu.com/explore/1122334455",
            "description": "探店笔记：胡同里的静谧时光,咖啡和甜点都非常出色。",
            "cover_image": "https://example.com/image3.jpg"
        }
    ]

# For standalone testing
if __name__ == "__main__":
    print("Testing XHS Scraper...")
    items = fetch_xhs_favorites()
    print(f"\nFetched {len(items)} items:")
    for item in items:
        print(f"  - {item['title']}")
