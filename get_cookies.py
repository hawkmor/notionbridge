#!/usr/bin/env python3
"""
Standalone script to get Xiaohongshu cookies interactively.
No dependencies on app modules.
"""
import os
import sys
import json
import time

print(f"DEBUG: Python executable: {sys.executable}")
print(f"DEBUG: Python version: {sys.version}")
print(f"DEBUG: sys.path: {sys.path}")

try:
    from playwright.sync_api import sync_playwright
except ImportError as e:
    print(f"❌ ImportError: {e}")
    # Try to find where playwright is if it's installed but not in path
    import subprocess
    try:
        pip_show = subprocess.check_output([sys.executable, "-m", "pip", "show", "playwright"]).decode()
        print(f"DEBUG: pip show playwright output:\n{pip_show}")
    except Exception as e2:
        print(f"DEBUG: Failed to run pip show: {e2}")
    
    # Re-raise to keep original behavior after debugging
    raise

# User-Agent to ensure consistency
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'

# Cookie storage file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "cookies.json")
AUTH_STATE_FILE = os.path.join(BASE_DIR, "auth_state.json")


def save_auth_state(context, cookie_file: str = COOKIE_FILE, auth_state_file: str = AUTH_STATE_FILE) -> bool:
    """Save full browser state (cookies + localStorage)."""
    try:
        # Save cookies separately for backward compatibility
        cookies = context.cookies()
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
            
        # Save full storage state (Playwright standard)
        context.storage_state(path=auth_state_file)
        
        print(f"✅ Auth state saved to {auth_state_file}")
        print(f"✅ Cookies saved to {cookie_file}")
        return True
    except Exception as e:
        print(f"❌ Failed to save auth state: {e}")
        return False


def interactive_login(timeout: int = 300):
    """
    Launches a headed browser for the user to log in manually.
    Polls for login success and saves cookies.
    """
    print("\n" + "="*50)
    print("🔐 STARTING INTERACTIVE LOGIN")
    print("="*50)
    
    try:
        with sync_playwright() as p:
            # Launch headed browser
            print("🌐 Opening browser...")
            browser = p.chromium.launch(headless=False)
            
            # Use unified context options
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent=USER_AGENT
            )
            page = context.new_page()
            
            # Load existing state if any
            if os.path.exists(AUTH_STATE_FILE):
                print(f"ℹ️ Loading existing state from {AUTH_STATE_FILE}...")
                # Re-create context with storage state
                context.close()
                context = browser.new_context(
                    storage_state=AUTH_STATE_FILE,
                    viewport={'width': 1280, 'height': 800},
                    user_agent=USER_AGENT
                )
                page = context.new_page()
            
            print("🚀 Navigating to Xiaohongshu...")
            page.goto("https://www.xiaohongshu.com")
            
            print(f"⏳ Please log in to Xiaohongshu (timeout: {timeout}s)...")
            print("   - Use QR code scan OR")
            print("   - Use phone number login OR")
            print("   - Use email/password login")
            print("")
            print("⚠️  After successful login, please wait for a few seconds.")
            print("   The script will automatically detect your login and save cookies.")
            print("")
            
            start_time = time.time()
            is_logged_in = False
            
            # Track initial state to avoid false positives from old cookies
            initial_check_done = False
            initial_logged_val = None
            
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
                    
                    # Store initial state on first check
                    if not initial_check_done:
                        initial_logged_val = logged_val
                        initial_check_done = True
                        print(f"   Initial state: data-logged={logged_val}, avatar={'Yes' if user_icon else 'No'}")
                        print(f"   Waiting for you to login manually...")
                    
                    # Only detect login if state CHANGED from initial
                    # This prevents false positives from old cookies
                    state_changed = (logged_val == "1" and initial_logged_val != "1")
                    
                    # Also check if we have user info in page (more reliable)
                    has_user_info = page.evaluate('''() => {
                        try {
                            return window.__INITIAL_STATE__?.user?.userInfo?.userId ? true : false;
                        } catch(e) {
                            return false;
                        }
                    }''')
                    
                    if state_changed or has_user_info:
                        print("\n✅ Login detected!")
                        # Wait a moment for fully settled state
                        page.wait_for_timeout(2000)
                        
                        # Save full auth state
                        save_auth_state(context, COOKIE_FILE, AUTH_STATE_FILE)
                        
                        is_logged_in = True
                        break
                        
                    # Check if user closed the browser
                    if page.is_closed():
                        print("⚠️ Browser closed by user")
                        break
                        
                except Exception:
                    # Page might be closed or navigating
                    if page.is_closed():
                        break
                    pass
                
                time.sleep(1)
            
            if not is_logged_in and not page.is_closed():
                print("⏰ Login timed out")
            
            try:
                browser.close()
            except:
                pass
                
            return is_logged_in
            
    except Exception as e:
        print(f"❌ Error during interactive login: {e}")
        return False


if __name__ == "__main__":
    print("🔐 Xiaohongshu Cookie Retrieval Tool")
    print("=" * 50)
    print("cwd =", os.getcwd())
    print("script dir =", BASE_DIR)
    print("cookie file =", COOKIE_FILE)
    print("")
    
    success = interactive_login()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ SUCCESS! Cookies saved successfully!")
        print(f"📁 Location: {os.path.abspath(COOKIE_FILE)}")
        print("")
        print("💡 Next steps:")
        print("   1. The cookies.json file is ready to use")
        print("   2. You can now run your sync script")
        print("   3. Cookies typically last 1-2 months")
    else:
        print("❌ FAILED to retrieve cookies")
        print("")
        print("💡 Troubleshooting:")
        print("   1. Make sure Playwright is installed:")
        print("      pip install playwright")
        print("      playwright install chromium")
        print("   2. Try running the script again")
        print("   3. Make sure you complete the login process")
    print("=" * 50)
    print("cwd =", os.getcwd())
