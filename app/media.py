import os
import requests
import subprocess
from logger import logger

def extract_video_frame(video_path: str, output_path: str) -> bool:
    """
    Extract first frame from video as cover image using ffmpeg.
    Returns True if successful, False otherwise.
    """
    try:
        logger.verbose("  📸 Extracting first frame from video...")
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vframes', '1',
            '-f', 'image2',
            '-y',  # Overwrite output file
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0 and os.path.exists(output_path):
            logger.verbose(f"  ✓ Extracted frame: {os.path.getsize(output_path) / 1024:.1f} KB")
            return True
        else:
            logger.debug(f"  ⚠️ Frame extraction failed")
            return False
            
    except Exception as e:
        logger.debug(f"  ⚠️ Frame extraction error: {e}")
        return False

def download_video(video_url: str, output_path: str) -> bool:
    """
    Download video from URL to local file.
    Returns True if successful, False otherwise.
    """
    try:
        logger.verbose(f"  📥 Downloading video...")
        response = requests.get(video_url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(output_path)
        print(f"  ✓ Downloaded {file_size / 1024 / 1024:.2f} MB")
        return True
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return False
        
def download_cover_image(url: str, save_path: str) -> bool:
    """Download cover image from URL."""
    try:
        logger.verbose("  📥 Downloading cover image...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        size_mb = len(response.content) / (1024 * 1024)
        logger.verbose(f"  ✓ Downloaded cover: {size_mb:.2f} MB")
        return True
    except Exception as e:
        logger.debug(f"  ⚠️ Cover download failed: {e}")
        return False
