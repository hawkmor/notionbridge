"""
Xiaohongshu Web Selectors Mapping
Centralized place to manage CSS selectors as XHS updates frequently.
"""

SELECTORS = {
    # Board/Feed Page
    "note_item": "section.note-item, div.note-item, [class*='note-item']",
    "feed_container": "main, [class*='content'], #app",
    
    # Modal / Detail Popup
    "modal_container": [
        ".note-detail-mask",
        ".modal-container",
        "[class*='modal']",
        "[role='dialog']",
        ".note-detail-container"
    ],
    "close_button": ".close-circle, .close-btn, [class*='close']",
    
    # Content Inside Modal
    "title": [
        "h1.title",
        "[class*='title']",
        ".note-content .title",
        "#detail-title"
    ],
    "author": [
        ".author-name",
        ".nickname",
        "[class*='author-name']",
        "a[href*='/user/profile/']",
        ".username"
    ],
    "desc": [
        ".desc",
        ".note-text",
        "[class*='note-text']",
        "#detail-desc"
    ],
    "tags": ".tag, a[href*='/search']",
    "date": "span.date, .publish-date, [class*='publish-date'], time",
    
    # Media
    "image": "img[src*='sns-img'], img[src*='xhscdn'], img[src*='ci.xiaohongshu']",
    "video_tag": "video",
    "video_container": ".video-card, .player-container, [class*='video']"
}
