import os
import json
import time
import requests
from seleniumbase import SB

# ================= 配置与环境变量解析 =================

BYTENUT_ACCOUNTS = os.environ.get('BYTENUT_ACCOUNTS', '[]')
try:
    ACCOUNTS = json.loads(BYTENUT_ACCOUNTS)
except json.JSONDecodeError:
    print("❌ BYTENUT_ACCOUNTS 解析失败！")
    ACCOUNTS = []

TG_BOT = os.environ.get('TG_BOT', '')
USE_PROXY = os.environ.get('GOST_PROXY') != ''
PROXY_STR = "http://127.0.0.1:8080" if USE_PROXY else None

def send_telegram_message(message):
    print(message)
    if not TG_BOT or ',' not in TG_BOT:
        return
    try:
        token, chat_id = TG_BOT.split(',', 1)
        url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
        payload = {"chat_id": chat_id.strip(), "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram 消息发送失败: {e}")

# ================= 核心自动化逻辑 =================

def login_and_renew(sb, account_info):
    username = account_info.get('username')
    password = account_info.get('password')
    panel_url = account_info.get('panel_url')
    
    send_telegram_message(f"🔄 开始处理账号: <b>{username}</b>")

    try:
        # 1. 账号密码登录
        print("🔑 使用账号密码登录...")
        sb.open("https://bytenut.com/auth/login")
        sb.sleep(3)
        sb.type('input[placeholder="Username"]', username)
        sb.type('input[placeholder="Password"]', password)
        sb.click('button:contains("Sign In")')
        sb.sleep(8) # 等待登录完成，防 CF 拦截
        
        sb.open("https://bytenut.com/free-server")
        sb.sleep(5)
        
        if "/auth/login" in sb.get_current_url():
            send_telegram_message(f"❌ 账号 {username} 密码登录失败。")
            sb.save_screenshot(f"login_failed_{username}.png")
            return

        # 2. 跳转到指定的面板 URL
        if not panel_url:
            send_telegram_message(f"⚠️ 账号 {username} 缺少 panel_url 配置，请在 Secrets 中添加。")
            return

        print(f"🎯 跳转至目标面板: {panel_url}")
        sb.open(panel_url)
        sb.sleep(8) # 留足时间让 CF 验证码 iframe 加载出来

        # 3. 🛡️ 强力破解 Cloudflare 验证码
        # Turnstile 验证码通常嵌套在特定的 iframe 中
        cf_iframe_selector = 'iframe[src*="challenges.cloudflare.com"]'
        
        if sb.is_element_visible(cf_iframe_selector):
            print("🛡️ 捕捉到 Cloudflare 验证码！准备模拟人类鼠标点击...")
            # 使用 sb.uc_click() 进行底层的、带轨迹的真实点击，专破 CF
            sb.uc_click(cf_iframe_selector)
            
            # 点击后必须等待它转圈验证通过，通常需要几秒钟
            print("⏳ 正在等待 CF 验证通过 (10秒)...")
            sb.sleep(10)
        else:
            print("ℹ️ 未捕捉到需要手动点击的 CF 验证码，可能已自动绿灯放行。")

        # 4. 点击续期按钮
        extend_button_selector = 'button:contains("Extend Time")'
        if sb.is_element_visible(extend_button_selector):
            print("🖱️ 正在点击续期按钮...")
            # 使用 js_click 强制点击，防止被隐形元素遮挡
            sb.js_click(extend_button_selector)
            sb.sleep(5)
            
            # 截图留证，确认点击后的页面状态
            sb.save_screenshot(f"success_verify_{username}.png")
            send_telegram_message(f"✅ 账号 {username} | 成功绕过 CF 并发送续期请求！")
        else:
            send_telegram_message(f"ℹ️ 账号 {username} | 续期按钮未找到。")
            sb.save_screenshot(f"no_button_{username}.png")
                
    except Exception as e:
        error_screenshot = f"error_{username}_{int(time.time())}.png"
        sb.save_screenshot(error_screenshot)
        send_telegram_message(f"❌ 账号 {username} 发生异常: {str(e)[:100]}")

def main():
    if not ACCOUNTS:
        print("停止运行：没有配置账号。")
        return

    # 保持 uc=True 开启反检测模式
    with SB(uc=True, headless=False, proxy=PROXY_STR) as sb:
        for account in ACCOUNTS:
            login_and_renew(sb, account)
            sb.sleep(3)

if __name__ == "__main__":
    main()
