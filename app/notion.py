import os
import requests
import math
import traceback
import re
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from typing import List, Dict, Optional, Callable, Any
try:
    from logger import logger
except ImportError:
    from app.logger import logger

from app.config import Config
from app.media import extract_video_frame, download_video
from app.utils import load_synced_ids, save_synced_ids

# Notion API helpers (using raw requests for compatibility with notion-client 2.7.0+)
NOTION_API_VERSION = "2022-06-28"

def _notion_request(method: str, path: str, body: dict = None) -> dict:
    """Make a raw Notion API request."""
    api_key = Config.NOTION_API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json"
    }
    url = f"https://api.notion.com/v1{path}"
    response = requests.request(method, url, headers=headers, json=body, timeout=30)
    response.raise_for_status()
    return response.json()


def _append_blocks(page_id: str, blocks: List[Dict[str, Any]]) -> None:
    """Append child blocks using raw Notion API requests."""
    for i in range(0, len(blocks), 100):
        _notion_request("PATCH", f"/blocks/{page_id}/children", {
            "children": blocks[i:i + 100]
        })


def _get_database_properties(database_id: str) -> Dict[str, Dict[str, Any]]:
    """Fetch database properties so writes match the user's actual schema."""
    database = _notion_request("GET", f"/databases/{database_id}")
    return database.get("properties", {}) or {}


def _find_property(properties: Dict[str, Dict[str, Any]], names: List[str], prop_type: str = None) -> Optional[str]:
    """Find a property by preferred names, optionally constrained by Notion type."""
    lowered = {name.lower(): name for name in properties}
    for name in names:
        actual = lowered.get(name.lower())
        if actual and (prop_type is None or properties[actual].get("type") == prop_type):
            return actual

    if prop_type == "title":
        for name, prop in properties.items():
            if prop.get("type") == "title":
                return name

    return None


def _parse_xhs_date(value: str) -> Optional[str]:
    """Parse common XHS date strings into YYYY-MM-DD for Notion date properties."""
    if not value:
        return None
    text = str(value).strip()

    match = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    match = re.search(r"(?<!\d)(\d{1,2})[./月-](\d{1,2})(?:日)?", text)
    if match:
        month, day = match.groups()
        year = datetime.now().year
        return f"{year:04d}-{int(month):02d}-{int(day):02d}"

    return None


def _text_property(value: str) -> Dict[str, Any]:
    return {
        "rich_text": [
            {
                "type": "text",
                "text": {"content": str(value)[:2000]}
            }
        ]
    }


def _plain_text_from_content(item: Dict[str, Any]) -> str:
    parts = []
    for content_item in item.get("content") or []:
        if content_item.get("type") == "text" and content_item.get("content"):
            parts.append(str(content_item["content"]))
    return "\n".join(parts).strip()


def _build_page_properties(item: Dict[str, Any], database_properties: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Build Notion page properties from scraped item data and actual DB schema."""
    properties: Dict[str, Any] = {}

    title_name = _find_property(database_properties, ["Name", "Title", "标题", "名称"], "title")
    if not title_name:
        raise ValueError("Notion database must contain a title property")
    properties[title_name] = {
        "title": [
            {
                "type": "text",
                "text": {"content": str(item.get("title") or "Untitled")[:2000]}
            }
        ]
    }

    url_name = _find_property(database_properties, ["URL", "Url", "Link", "链接", "原文链接"], "url")
    if url_name and item.get("url"):
        properties[url_name] = {"url": item["url"]}

    author_name = _find_property(database_properties, ["Author", "作者", "Creator", "博主"], "rich_text")
    if author_name and item.get("author"):
        properties[author_name] = _text_property(item["author"])

    date_name = _find_property(database_properties, ["Publish Date", "Published", "Date", "发布日期", "日期", "Created Date", "创建日期"], "date")
    parsed_date = _parse_xhs_date(item.get("created_date", ""))
    if date_name and parsed_date:
        properties[date_name] = {"date": {"start": parsed_date}}

    tags_name = _find_property(database_properties, ["Tags", "Tag", "标签"], "multi_select")
    tags = _collect_tags(item)
    if tags_name and tags:
        properties[tags_name] = {
            "multi_select": [{"name": tag[:100]} for tag in tags[:20]]
        }

    content_text = _plain_text_from_content(item)
    content_name = _find_property(database_properties, ["Content", "Description", "Desc", "正文", "描述", "内容"], "rich_text")
    if content_name and content_text:
        properties[content_name] = _text_property(content_text)

    return properties


def _page_icon_payload() -> Optional[Dict[str, Any]]:
    """Build a Notion page icon payload from configuration."""
    icon_url = (Config.NOTION_PAGE_ICON_URL or "").strip()
    if not icon_url or icon_url.lower() == "none":
        return None
    return {
        "type": "external",
        "external": {"url": icon_url},
    }


def update_existing_page_properties(
    page_id: str,
    item: Dict[str, Any],
    database_properties: Dict[str, Dict[str, Any]],
) -> None:
    """Refresh metadata for an already-synced page without touching page blocks."""
    properties = _build_page_properties(item, database_properties)
    payload: Dict[str, Any] = {}
    if properties:
        payload["properties"] = properties
    icon = _page_icon_payload()
    if icon:
        payload["icon"] = icon
    if payload:
        _notion_request("PATCH", f"/pages/{page_id}", payload)


def _collect_tags(item: Dict[str, Any]) -> List[str]:
    ignored_tags = {"作者"}
    tags_set = set(str(tag).strip().replace("#", "") for tag in item.get("tags", []) if str(tag).strip())
    tags_set = {tag for tag in tags_set if tag not in ignored_tags}

    for content_item in item.get("content") or []:
        if content_item.get("type") == "text":
            text = content_item.get("content", "")
            for tag in re.findall(r"#([^\s#]+)", text):
                tag = tag.strip()
                if tag and tag not in ignored_tags:
                    tags_set.add(tag)

    return sorted(tags_set)


# =======================
# Helper functions for URL normalization and Notion duplicate detection
# =======================

def normalize_xhs_url(url: str) -> str:
    """Normalize Xiaohongshu note URLs for stable de-dup (strip query/fragment, trim trailing slash)."""
    if not url:
        return ""
    try:
        u = url.strip()
        p = urlparse(u)
        # Keep scheme/netloc/path only
        normalized = urlunparse((p.scheme or "https", p.netloc, p.path.rstrip("/"), "", "", ""))
        return normalized
    except Exception:
        return url.strip().rstrip("/")


def find_existing_page_id_by_url(database_id: str, url: str, url_property: str = "URL") -> Optional[str]:
    """Return existing Notion page id whose URL property equals the given url (or normalized url)."""
    if not url:
        return None

    # Try both raw and normalized forms to be safe
    candidates = [url]
    nurl = normalize_xhs_url(url)
    if nurl and nurl != url:
        candidates.append(nurl)

    for candidate in candidates:
        try:
            resp = _notion_request("POST", f"/databases/{database_id}/query", {
                "filter": {
                    "property": url_property,
                    "url": {"equals": candidate}
                },
                "page_size": 1
            })
            results = resp.get("results") or []
            if results:
                return results[0].get("id")
        except Exception as e:
            # If the DB doesn't have a URL property, or query fails, ignore and fallback to synced_ids.
            logger.debug(f"  ⚠️ Query failed for {candidate}: {e}")
            continue

    return None

def upload_video_to_notion_api(page_id: str, video_path: str) -> bool:
    """
    Upload video to Notion using official API multi-part upload via HTTP requests.
    Returns True if successful, False otherwise.
    """
    try:
        print(f"  📤 Uploading video via Notion API...")
        
        # Get file size and API key
        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)
        api_key = Config.NOTION_API_KEY
        
        # Notion API requires multi-part upload for files > 20MB
        chunk_size = 10 * 1024 * 1024  # 10MB chunks
        num_parts = math.ceil(file_size / chunk_size)
        
        print(f"  📊 File size: {file_size / 1024 / 1024:.2f} MB, {num_parts} parts")
        
        # Step 1: Create file upload object
        print(f"  1️⃣ Creating file upload object...")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        create_payload = {
            "mode": "multi_part",
            "number_of_parts": num_parts,
            "filename": filename,
            "content_type": "video/mp4"
        }
        
        response = requests.post(
            "https://api.notion.com/v1/file_uploads",  # Correct endpoint!
            headers=headers,
            json=create_payload,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  ✗ API Error: {response.status_code}")
            print(f"  Response: {response.text}")
        
        response.raise_for_status()
        upload_data = response.json()
        
        upload_id = upload_data["id"]
        logger.verbose(f"  ✓ Upload ID: {upload_id[:8]}...")
        
        # Step 2: Upload each part
        logger.verbose(f"  2️⃣ Uploading {num_parts} parts...")
        send_headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28"
            # Note: Content-Type is set by requests for multipart/form-data
        }
        
        with open(video_path, 'rb') as f:
            for part_num in range(1, num_parts + 1):
                chunk = f.read(chunk_size)
                
                # Upload this part using multipart/form-data
                files = {
                    'file': (filename, chunk, 'video/mp4')
                }
                data = {
                    'part_number': str(part_num)
                }
                
                part_response = requests.post(
                    f"https://api.notion.com/v1/file_uploads/{upload_id}/send",  # Correct endpoint!
                    headers=send_headers,
                    files=files,
                    data=data,
                    timeout=60
                )
                part_response.raise_for_status()
                
                logger.verbose(f"  ✓ Part {part_num}/{num_parts} uploaded")
        
        # Step 3: Complete the upload
        print(f"  3️⃣ Completing upload...")
        complete_response = requests.post(
            f"https://api.notion.com/v1/file_uploads/{upload_id}/complete",
            headers=headers,
            timeout=30
        )
        complete_response.raise_for_status()
        print(f"  ✓ Upload completed")
        
        # Step 4: Add video block to page using raw API
        print(f"  4️⃣ Adding video block to page...")
        
        try:
            _notion_request("PATCH", f"/blocks/{page_id}/children", {
                "children": [
                    {
                        "object": "block",
                        "type": "video",
                        "video": {
                            "type": "file_upload",
                            "file_upload": {
                                "id": upload_id
                            }
                        }
                    }
                ]
            })
            
            print(f"  ✅ Video uploaded and added to page!")
            return True
            
        except Exception as e:
            print(f"  ✗ Failed to add video block: {e}")
            logger.debug(f"  Video block append error: {e}")
            return False
        
    except Exception as e:
        logger.debug(f"  ✗ Upload failed: {e}")
        logger.verbose(traceback.format_exc())
        return False


def create_notion_page_with_content(
    database_id: str,
    item: Dict,
    database_properties: Dict[str, Dict[str, Any]],
):
    """
    Create a Notion page with full content (text, images, videos).
    """
    properties = _build_page_properties(item, database_properties)
    
    # Cover image
    cover_data = None
    if item.get("cover_image"):
        cover_data = {
            "type": "external",
            "external": {
                "url": item["cover_image"]
            }
        }
    
    body = {
        "parent": {"database_id": database_id},
        "properties": properties
    }
    icon = _page_icon_payload()
    if icon:
        body["icon"] = icon
    if cover_data:
        body["cover"] = cover_data
    
    page = _notion_request("POST", "/pages", body)
    
    page_id = page["id"]
    logger.verbose(f"  ✓ Created page: {item.get('title', 'Untitled')}")
    
    # Now add content blocks
    if item.get("content"):
        # Note: URL is already in the page properties, no need for callout block
        
        # Separate content by type
        videos = []
        images = []
        texts = []
        
        for content_item in item["content"]:
            if content_item["type"] == "video":
                videos.append(content_item)
            elif content_item["type"] == "image":
                images.append(content_item)
            elif content_item["type"] == "text":
                texts.append(content_item)
        
        # STEP 1: Upload ALL videos FIRST (they'll appear at the top of the page)
        first_video_path = None  # Track first video for cover extraction
        
        for idx, video_item in enumerate(videos):
            video_url = video_item["url"]
            
            # Create videos folder
            videos_dir = os.path.join(os.getcwd(), "data", "downloaded_videos")
            os.makedirs(videos_dir, exist_ok=True)
            
            # Use note title as filename (sanitized)
            safe_title = "".join(c for c in item.get("title", "video")[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
            video_filename = f"{safe_title}_{page_id[-8:]}.mp4"
            video_path = os.path.join(videos_dir, video_filename)
            
            # Download and upload video
            if download_video(video_url, video_path):
                logger.verbose(f"  💾 Video saved to: {video_path}")
                
                # Save first video path for cover extraction
                if idx == 0:
                    first_video_path = video_path
                
                try:
                    upload_video_to_notion_api(page_id, video_path)
                    print(f"  ✅ Video uploaded (will appear at top)")
                except Exception as e:
                    logger.debug(f"  ⚠️ Video upload failed: {e}")
            else:
                logger.debug(f"  ⚠️ Video download failed: {video_url}")
        

        # STEP 2: Now add images and text blocks (they'll appear AFTER videos)
        blocks = []
        
        for content_item in images + texts:
            if content_item["type"] == "text":
                # Add paragraph
                text_content = content_item["content"]
                if text_content.strip():
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": text_content[:2000]  # Notion limit
                                    }
                                }
                            ]
                        }
                    })
            
            elif content_item["type"] == "image":
                # Add image block
                image_url = content_item["url"]
                blocks.append({
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {
                            "url": image_url
                        }
                    }
                })
        
        # Append blocks to page (max 100 blocks per request)
        if blocks:
            try:
                # Split into chunks of 100 blocks
                for i in range(0, len(blocks), 100):
                    chunk = blocks[i:i+100]
                    _append_blocks(page_id, chunk)
                logger.verbose(f"  ✓ Added {len(blocks)} content blocks")

            except Exception as e:
                logger.debug(f"  ✗ Failed to add content blocks: {e}")
                raise
        
        # STEP 3: For video-only notes, extract first frame and add at bottom
        # Only do this if there are NO images in the content
        has_images = any(c["type"] == "image" for c in item.get("content", []))
        
        logger.debug(f"  🔍 Video frame check: first_video_path={bool(first_video_path)}, exists={os.path.exists(first_video_path) if first_video_path else False}, has_images={has_images}")
        
        if first_video_path and os.path.exists(first_video_path) and not has_images:
            covers_dir = os.path.join(os.getcwd(), "data", "downloaded_covers")
            os.makedirs(covers_dir, exist_ok=True)
            safe_title = "".join(c for c in item.get("title", "cover")[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
            cover_filename = f"{safe_title}_{page_id[-8:]}.jpg"
            cover_path = os.path.join(covers_dir, cover_filename)
            
            if extract_video_frame(first_video_path, cover_path):
                try:
                    logger.verbose("  📸 Uploading video frame...")
                    
                    api_key = Config.NOTION_API_KEY
                    filename = os.path.basename(cover_path)
                    
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    }
                    
                    # Step 1: Create file upload object
                    create_payload = {
                        "mode": "single_part",
                        "filename": filename,
                        "content_type": "image/jpeg"
                    }
                    
                    response = requests.post(
                        "https://api.notion.com/v1/file_uploads",
                        headers=headers,
                        json=create_payload,
                        timeout=30
                    )
                    response.raise_for_status()
                    upload_data = response.json()
                    upload_id = upload_data["id"]
                    upload_url = upload_data["upload_url"]
                    logger.debug(f"  ℹ️ Upload URL: {upload_url}")
                    
                    # Step 2: Upload binary content to upload_url using POST (since it's a /send endpoint)
                    with open(cover_path, 'rb') as f:
                        files = {'file': (filename, f, 'image/jpeg')}
                        
                        upload_response = requests.post(
                            upload_url,
                            files=files,
                            headers={"Notion-Version": "2022-06-28", "Authorization": f"Bearer {api_key}"},
                            timeout=60
                        )
                        if upload_response.status_code != 200:
                            logger.debug(f"  ❌ File content upload failed: {upload_response.status_code}")
                            logger.debug(f"  Response: {upload_response.text}")
                        upload_response.raise_for_status()
                        logger.verbose("  ✓ Video frame content uploaded")
                    
                    # Step 3: Add as image block using file_upload type
                    _append_blocks(
                        page_id,
                        [{
                            'object': 'block',
                            'type': 'image',
                            'image': {
                                'type': 'file_upload',
                                'file_upload': {'id': upload_id}
                            }
                        }],
                    )
                    logger.debug("  ✅ Video frame added at bottom!")
                except Exception as e:
                    logger.debug(f"  ⚠️ Video frame upload failed: {e}")
    
    return page_id

def push_to_notion(favorites: List[Dict], incremental: bool = True, log_callback: Optional[Callable] = None):
    """
    Pushes a list of favorite items to the configured Notion database.
    Creates full pages with rich content.
    
    Returns:
        tuple: (success_count, skip_count, fail_count)
    """
    api_key = Config.NOTION_API_KEY
    database_id = Config.NOTION_DATABASE_ID

    def _log(msg, level="info"):
        # Still support log_callback for web UI
        if log_callback:
            log_callback(msg, level)

    if not api_key or not database_id:
        raise ValueError("Please set NOTION_API_KEY and NOTION_DATABASE_ID in .env file")

    # Load synced IDs
    synced_ids_path = Config.SYNCED_IDS_FILE
    # Use a set for fast lookup and to remove accidental duplicates in the json file
    synced_ids_list = load_synced_ids(synced_ids_path)
    synced_ids = set(normalize_xhs_url(u) for u in (synced_ids_list or []) if u)

    logger.verbose(f"Starting sync to Notion database: {database_id}...")
    logger.verbose(f"Will process {len(favorites)} pages")
    database_properties = _get_database_properties(database_id)
    url_property = _find_property(database_properties, ["URL", "Url", "Link", "链接", "原文链接"], "url")

    success_count = 0
    fail_count = 0
    skip_count = 0

    for idx, item in enumerate(favorites, 1):
        try:
            note_url = normalize_xhs_url(item.get('url', '') or '')

            # Always prevent duplicates by checking Notion first (works even in --full mode)
            existing_page_id = None
            if note_url and url_property:
                existing_page_id = find_existing_page_id_by_url(database_id, note_url, url_property)

            # Incremental mode: skip if we've already synced (local cache) OR Notion already has it
            if incremental and note_url and (note_url in synced_ids or existing_page_id):
                if existing_page_id:
                    update_existing_page_properties(existing_page_id, item, database_properties)
                skip_count += 1
                logger.verbose(f"⏭️ Skipping: {item.get('title', 'Untitled')}")
                logger.verbose(f"   ↳ reason: {'exists in Notion' if existing_page_id else 'exists in synced_ids.json'}")
                continue

            # Full/backfill mode: do NOT create duplicates; skip if Notion already has this URL
            if not incremental and existing_page_id:
                update_existing_page_properties(existing_page_id, item, database_properties)
                skip_count += 1
                logger.verbose(f"⏭️ Skipping (full): {item.get('title', 'Untitled')}")
                logger.verbose("   ↳ reason: exists in Notion")
                continue

            title = item.get("title", "Untitled")
            logger.debug(f"  ✓ 创建: \"{title}\"")
            logger.verbose(f"[{idx}/{len(favorites)}] Syncing: {title}")
            _log(f"[{idx}/{len(favorites)}] Syncing: {title}")
            page_id = create_notion_page_with_content(database_id, item, database_properties)
            
            # Mark as synced
            if note_url:
                synced_ids.add(note_url)
                # Persist de-duplicated list (sorted for stable diffs)
                save_synced_ids(sorted(synced_ids), synced_ids_path)

            success_count += 1

        except Exception as e:
            fail_count += 1
            logger.debug(f"  ✗ 失败: {item.get('title', 'Untitled')} - {str(e)[:50]}")
            logger.verbose(f"  ✗ Failed to sync: {e}")
            _log(f"  ✗ Failed to sync: {e}", "error")
            continue

    # Verbose-level detailed results
    logger.verbose("="*60)
    logger.verbose(f"Sync Results: {success_count} added, {skip_count} skipped, {fail_count} failed")
    logger.verbose("="*60)

    # Final save to ensure any in-memory changes are persisted
    try:
        save_synced_ids(sorted(synced_ids), synced_ids_path)
    except Exception:
        pass
    
    # Return stats tuple for main.py to use in summary
    return (success_count, skip_count, fail_count)
