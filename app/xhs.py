import os
import json
import time
import random
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

        # 1. Extract URL (Clean)
        url = page.url.split('?')[0]
        if '/explore/' not in url:
            # Try to find a link inside modal if page URL hasn't updated
            link_elem = modal.query_selector('a[href*="/explore/"]')
            if link_elem:
                href = link_elem.get_attribute('href')
                url = f"https://www.xiaohongshu.com{href}" if href.startswith('/') else href
        
        # 2. Extract Title
        title_elem = _try_selectors(modal, SELECTORS["title"])
        title = title_elem.inner_text().strip() if title_elem else "Untitled"
        
        # 3. Extract Author
        author = _extract_author(modal)
        
        # 4. Extract Content (Text Blocks)
        content = []
        desc_area = _try_selectors(modal, SELECTORS["desc"])
        if desc_area:
            # We want paragraphs but also keep it simple
            text_lines = desc_area.inner_text().split('\n')
            for line in text_lines:
                clean_line = line.strip()
                if clean_line:
                    content.append({"type": "text", "content": clean_line})

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
        img_elements = _try_selectors(modal, SELECTORS["image"], all=True)
        seen_urls = set()
        
        for img in img_elements:
            try:
                # Skip swiper clones/duplicates (critical for XHS)
                is_duplicate = img.evaluate("el => el.closest('.swiper-slide-duplicate') !== null")
                if is_duplicate: continue

                src = img.get_attribute('src')
                if not src or 'avatar' in src.lower(): continue
                
                clean_img_url = src.split('?')[0]
                if clean_img_url not in seen_urls:
                    content.append({"type": "image", "url": clean_img_url})
                    seen_urls.add(clean_img_url)
            except:
                continue

        # 6. Extract Tags & Date
        tags = []
        tag_elems = _try_selectors(modal, SELECTORS["tags"], all=True)
        if tag_elems:
            tags = [t.inner_text().strip().replace('#', '') for t in tag_elems if t.inner_text().strip()]
            
        date_elem = _try_selectors(modal, SELECTORS["date"])
        created_date = date_elem.inner_text().strip() if date_elem else ""

        # Close Modal (Press ESC or Click)
        try:
            page.keyboard.press('Escape')
            # Wait for modal to disappear
            page.wait_for_timeout(300)
        except:
            close_btn = _try_selectors(modal, SELECTORS["close_button"])
            if close_btn: close_btn.click()

        return {
            "title": title,
            "url": url,
            "author": author,
            "created_date": created_date,
            "content": content,
            "tags": list(set(tags)), # unique
            "cover_image": next((c["url"] for c in content if c["type"] == "image"), "")
        }
        
    except Exception as e:
        print(f"    ✗ Extraction Error: {e}")
        try: page.keyboard.press('Escape') 
        except: pass
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
        max_process = int(os.getenv('XHS_MAX_ITEMS', '80'))
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
