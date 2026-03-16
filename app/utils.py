"""
NotionBridge Utilities Module

Shared utility functions used across the application.
"""
import os
import json
from typing import Dict, List, Any


def load_synced_ids(filepath: str = "synced_ids.json") -> List[str]:
    """Load synced IDs from file.

    Supports both formats:
      1) {"synced_ids": ["..."]}
      2) ["..."]

    Always returns a de-duplicated list (stable order).
    """
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data: Any = json.load(f)

        # Format A: dict wrapper
        if isinstance(data, dict):
            raw = data.get('synced_ids', [])
        # Format B: plain list
        elif isinstance(data, list):
            raw = data
        else:
            return []

        if not isinstance(raw, list):
            return []

        # De-duplicate while preserving order
        seen = set()
        out: List[str] = []
        for x in raw:
            if not x:
                continue
            s = str(x)
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    except Exception:
        return []


def save_synced_ids(synced_ids: List[str], filepath: str = "synced_ids.json"):
    """Save synced IDs to file.

    - Always saves in dict-wrapper format: {"synced_ids": [...]}.
    - De-duplicates before saving.
    - Uses atomic write to avoid corrupting the file.
    """
    try:
        # De-duplicate while preserving order
        seen = set()
        out: List[str] = []
        for x in synced_ids or []:
            if not x:
                continue
            s = str(x)
            if s in seen:
                continue
            seen.add(s)
            out.append(s)

        tmp = filepath + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'synced_ids': out}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, filepath)
    except Exception:
        pass  # Silent fail for utility function


def is_already_synced(item_id: str, synced_ids: List[str]) -> bool:
    """
    Check if an item has already been synced.
    
    Args:
        item_id: Item ID to check
        synced_ids: List of already synced IDs
        
    Returns:
        True if already synced, False otherwise
    """
    if not item_id:
        return False
    if not synced_ids:
        return False
    return str(item_id) in set(str(x) for x in synced_ids if x)
