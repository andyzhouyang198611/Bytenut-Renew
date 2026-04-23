import os
import json
import time
import requests
from seleniumbase import SB

# ================= Configuration & Environment Parsing =================

# Account list, expected format: [{"username": "...", "password": "...", "panel_url": "..."}]
BYTENUT_ACCOUNTS = os.environ.get('BYTENUT_ACCOUNTS', '[]')
try:
    ACCOUNTS = json.loads(BYTENUT_ACCOUNTS)
except json.JSONDecodeError:
    print("❌ Failed to parse BYTENUT_ACCOUNTS JSON!")
    ACCOUNTS = []

# Telegram Bot info, format: "bot_token,chat_id"
TG_BOT = os.environ.get('TG_BOT', '')

# GOST Proxy (the workflow should have started the proxy on port 8080)
USE_PROXY = os.environ.get('GOST_PROXY') != ''
PROXY_STR = "http://127.0.0.1:8080" if USE_PROXY else None

# ================= Helper Functions =================

def send_telegram_message(message):
    """Send a Telegram notification."""
    print(message)
    if not TG_BOT or ',' not in TG_BOT:
        return
    
    try:
        token, chat_id = TG_BOT.split(',', 1)
        url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
        payload = {
            "chat_id": chat_id.strip(),
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram message failed to send: {e}")

# ================= Core Automation Logic =================

def login_and_renew(sb, account_info):
    username = account_info.get('username')
    password = account_info.get('password')
    panel_url = account_info.get('panel_url')
    
    send_telegram_message(f"🔄 Starting account: <b>{username}</b>")

    try:
        # 1. Login with Username/Password
        print("🔑 Logging in with password...")
        sb.open("https://bytenut.com/auth/login")
        sb.sleep(3)
        sb.type('input[placeholder="Username"]', username)
        sb.type('input[placeholder="Password"]', password)
        sb.click('button:contains("Sign In")')
        sb.sleep(8)  # Give ample time for login and CF challenges

        # Verify we aren't still on the login page
        if "/auth/login" in sb.get_current_url():
            send_telegram_message(f"❌ Account {username} login failed.")
            sb.save_screenshot(f"login_failed_{username}.png")
            return

        # 2. Go to the specified Panel URL
        if not panel_url:
            send_telegram_message(f"⚠️ Account {username} is missing panel_url. Skipped.")
            return

        print(f"🎯 Navigating to panel: {panel_url}")
        sb.open(panel_url)
        sb.sleep(8) # Wait for page and CF widget to load

        # 3. 🛡️ Handle Cloudflare Turnstile Challenge
        print("🛡️ Cloudflare Turnstile detected. Waiting for verification...")
        
        # Turnstile is in an iframe from challenges.cloudflare.com
        turnstile_iframe = 'iframe[src*="challenges.cloudflare.com"]'
        
        # Monitor the Turnstile state (wait up to 30s)
        verification_confirmed = False
        start_time = time.time()
        timeout = 30 # Seconds to wait for verification to complete
        
        while time.time() - start_time < timeout:
            try:
                # Turnstile applies a unique state to the container div in the iframe.
                # When successful, the internal #success element becomes visible.
                
                # We need to check inside the iframe
                sb.switch_to_frame(turnstile_iframe)
                
                # Check for an element that only appears on success (e.g., the checkmark container)
                # This selector is a common Turnstile success indicator.
                if sb.is_element_visible('#success-icon') or sb.is_element_visible('div.cf-success'):
                    verification_confirmed = True
                    break
                
                # Cloudflare can detect Selenium, so we need a slow check
                sb.sleep(3)
                print("⏳ still waiting...")

            except Exception as e:
                # If we lose connection to the iframe, it might be refreshing
                # print(f"DEBUG: Frame check failed: {e}")
                pass
            finally:
                # Always switch back to the main content
                sb.switch_to_default_content()

        if verification_confirmed:
            print("✅ Cloudflare verification successful!")
            send_telegram_message(f"🛡️ {username} | Cloudflare verification <b>passed</b>.")
        else:
            send_telegram_message(f"❌ {username} | Cloudflare verification <b>failed (timed out)</b>.")
            sb.save_screenshot(f"cf_failed_{username}.png")
            # If the check failed, don't even bother clicking the button; it won't work.
            return

        # 4. Find and Click the "Extend Time" Button
        extend_button_selector = 'button:contains("Extend Time")'
        
        if sb.is_element_visible(extend_button_selector):
            print("🖱️ Clicking 'Extend Time' button...")
            sb.js_click(extend_button_selector) # Use JS click for robustness
            sb.sleep(5)
            send_telegram_message(f"✅ {username} | Clicked 'Extend Time' button. Waiting for server response.")
            sb.save_screenshot(f"success_extend_click_{username}.png")
        else:
            send_telegram_message(f"ℹ️ {username} | 'Extend Time' button not found.")
            sb.save_screenshot(f"no_button_{username}.png")
                
    except Exception as e:
        # Save a screenshot on any unhandled error
        error_screenshot = f"error_{username}_{int(time.time())}.png"
        sb.save_screenshot(error_screenshot)
        send_telegram_message(f"❌ Account {username} encountered an error: {str(e)[:100]}")

def main():
    if not ACCOUNTS:
        print("停止运行：没有找到账户配置。")
        return

    # Use SeleniumBase's Undetected ChromeDriver (UC) mode
    # Workflow uses xvfb-run, so we can run as headless=False inside the virtual display
    with SB(uc=True, headless=False, proxy=PROXY_STR) as sb:
        for account in ACCOUNTS:
            login_and_renew(sb, account)
            # Short pause between accounts
            sb.sleep(3)

if __name__ == "__main__":
    main()
