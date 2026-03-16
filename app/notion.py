import os
import requests
import math
import json
from urllib.parse import urlparse, urlunparse

from typing import List, Dict, Optional, Callable
from notion_client import Client
from logger import logger

from app.config import Config
from app.media import extract_video_frame, download_video, download_cover_image
from app.utils import load_synced_ids, save_synced_ids, is_already_synced


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


def find_existing_page_id_by_url(notion: Client, database_id: str, url: str) -> Optional[str]:
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
            resp = notion.databases.query(
                database_id=database_id,
                filter={
                    "property": "URL",
                    "url": {"equals": candidate},
                },
                page_size=1,
            )
            results = resp.get("results") or []
            if results:
                return results[0].get("id")
        except Exception:
            # If the DB doesn't have a URL property, or query fails, ignore and fallback to synced_ids.
            continue

    return None

def upload_video_to_notion_api(notion: Client, page_id: str, video_path: str) -> bool:
    """
    Upload video to Notion using official API multi-part upload via HTTP requests.
    Returns True if successful, False otherwise.
    """
    try:
        print(f"  📤 Uploading video via Notion API...")
        
        # Get file size and API key
        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)
        api_key = os.getenv("NOTION_API_KEY")
        
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
            json=create_payload
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
                    data=data
                )
                part_response.raise_for_status()
                
                logger.verbose(f"  ✓ Part {part_num}/{num_parts} uploaded")
        
        # Step 3: Complete the upload
        print(f"  3️⃣ Completing upload...")
        complete_response = requests.post(
            f"https://api.notion.com/v1/file_uploads/{upload_id}/complete",
            headers=headers
        )
        complete_response.raise_for_status()
        print(f"  ✓ Upload completed")
        
        # Step 4: Add video block to page using Notion SDK
        print(f"  4️⃣ Adding video block to page...")
        
        try:
            # Use Notion SDK directly (revert from requests.patch)
            notion.blocks.children.append(
                block_id=page_id,
                children=[
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
            )
            
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


def create_notion_page_with_content(notion: Client, database_id: str, item: Dict):
    """
    Create a Notion page with full content (text, images, videos).
    """
    # Prepare properties for the database row
    properties = {
        "Name": {
            "title": [
                {
                    "text": {
                        "content": item["title"][:2000]  # Notion title limit
                    }
                }
            ]
        }
    }
    
    # Only add URL if it's not empty
    if item.get("url"):
        properties["URL"] = {
            "url": item["url"]
        }
    
    # Add Author if available
    if item.get("author"):
        properties["Author"] = {
            "rich_text": [
                {
                    "text": {
                        "content": item["author"]
                    }
                }
            ]
        }
    
    # Add Created Date if available and in valid ISO format
    if item.get("created_date"):
        created_date = item["created_date"]
        # Only add if it looks like a valid ISO date (contains dash or T)
        if '-' in created_date or 'T' in created_date:
            try:
                properties["Created Date"] = {
                    "date": {
                        "start": created_date
                    }
                }
            except:
                pass  # Skip if invalid format
    
    # Extract and add Tags from content (only if Tags field exists in database)
    # Note: Tags field must be manually created in Notion database first
    # Look for hashtags in the content (e.g., #美食 #旅行)
    tags_set = set()
    
    # Extract from item's tags field if exists
    if item.get("tags"):
        for tag in item["tags"]:
            tags_set.add(tag)
    
    # Also extract hashtags from text content
    if item.get("content"):
        import re
        for content_item in item["content"]:
            if content_item.get("type") == "text":
                text = content_item.get("content", "")
                # Match Chinese/English hashtags: #tag or #标签
                hashtags = re.findall(r'#([^\s#]+)', text)
                for tag in hashtags:
                    tags_set.add(tag)
    
    # Try to add Tags property (will be skipped if field doesn't exist)
    # To use this feature, manually add a "Tags" multi-select field to your Notion database
    if tags_set:
        try:
            properties["Tags"] = {
                "multi_select": [
                    {"name": tag[:100]} for tag in sorted(tags_set)[:20]
                ]
            }
        except:
            # Tags field doesn't exist in database, skip it
            pass
    
    # Cover image
    cover_data = None
    if item.get("cover_image"):
        cover_data = {
            "type": "external",
            "external": {
                "url": item["cover_image"]
            }
        }
    
    # Create the page first
    page = notion.pages.create(
        parent={"database_id": database_id},
        properties=properties,
        cover=cover_data
    )
    
    
    page_id = page["id"]
    logger.verbose(f"  ✓ Created page: {item['title']}")
    
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
                    upload_video_to_notion_api(notion, page_id, video_path)
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
        
        # Add tags at the end if available
        if item.get("tags"):
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
            tags_text = " ".join([f"#{tag}" for tag in item["tags"]])
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": tags_text
                            }
                        }
                    ],
                    "color": "gray"
                }
            })
        
        # Append blocks to page (max 100 blocks per request)
        if blocks:
            try:
                # Split into chunks of 100 blocks
                for i in range(0, len(blocks), 100):
                    chunk = blocks[i:i+100]
                    notion.blocks.children.append(
                        block_id=page_id,
                        children=chunk
                    )
                logger.verbose(f"  ✓ Added {len(blocks)} content blocks")

            except Exception as e:
                logger.debug(f"  ⚠️ Failed to add content blocks: {e}")
        
        # STEP 3: For video-only notes, extract first frame and add at bottom
        # Only do this if there are NO images in the content
        has_images = any(item["type"] == "image" for item in item.get("content", []))
        
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
                    
                    api_key = os.getenv("NOTION_API_KEY")
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
                        json=create_payload
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
                            headers={"Notion-Version": "2022-06-28", "Authorization": f"Bearer {api_key}"}
                        )
                        if upload_response.status_code != 200:
                            logger.debug(f"  ❌ File content upload failed: {upload_response.status_code}")
                            logger.debug(f"  Response: {upload_response.text}")
                        upload_response.raise_for_status()
                        logger.verbose("  ✓ Video frame content uploaded")
                    
                    # Step 3: Add as image block using file_upload type
                    notion.blocks.children.append(
                        block_id=page_id,
                        children=[{
                            'object': 'block',
                            'type': 'image',
                            'image': {
                                'type': 'file_upload',
                                'file_upload': {'id': upload_id}
                            }
                        }]
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
    from logger import logger
    api_key = Config.NOTION_API_KEY
    database_id = Config.NOTION_DATABASE_ID

    def _log(msg, level="info"):
        # Still support log_callback for web UI
        if log_callback:
            log_callback(msg, level)

    if not api_key or not database_id:
        raise ValueError("Please set NOTION_API_KEY and NOTION_DATABASE_ID in .env file")

    notion = Client(auth=api_key)

    # Load synced IDs
    synced_ids_path = Config.SYNCED_IDS_FILE
    # Use a set for fast lookup and to remove accidental duplicates in the json file
    synced_ids_list = load_synced_ids(synced_ids_path)
    synced_ids = set(normalize_xhs_url(u) for u in (synced_ids_list or []) if u)

    logger.verbose(f"Starting sync to Notion database: {database_id}...")
    logger.verbose(f"Will process {len(favorites)} pages")

    success_count = 0
    fail_count = 0
    skip_count = 0

    for idx, item in enumerate(favorites, 1):
        try:
            note_url = normalize_xhs_url(item.get('url', '') or '')

            # Always prevent duplicates by checking Notion first (works even in --full mode)
            existing_page_id = None
            if note_url:
                existing_page_id = find_existing_page_id_by_url(notion, database_id, note_url)

            # Incremental mode: skip if we've already synced (local cache) OR Notion already has it
            if incremental and note_url and (note_url in synced_ids or existing_page_id):
                skip_count += 1
                logger.verbose(f"⏭️ Skipping: {item.get('title', 'Untitled')}")
                logger.verbose(f"   ↳ reason: {'exists in Notion' if existing_page_id else 'exists in synced_ids.json'}")
                continue

            # Full/backfill mode: do NOT create duplicates; skip if Notion already has this URL
            if not incremental and existing_page_id:
                skip_count += 1
                logger.verbose(f"⏭️ Skipping (full): {item.get('title', 'Untitled')}")
                logger.verbose("   ↳ reason: exists in Notion")
                continue

            logger.debug(f"  ✓ 创建: \"{item['title']}\"")
            logger.verbose(f"[{idx}/{len(favorites)}] Syncing: {item['title']}")
            _log(f"[{idx}/{len(favorites)}] Syncing: {item['title']}")
            page_id = create_notion_page_with_content(notion, database_id, item)
            
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
