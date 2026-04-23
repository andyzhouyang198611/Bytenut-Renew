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
        # 1. 登录
        print("🔑 使用账号密码登录...")
        sb.open("https://bytenut.com/auth/login")
        sb.sleep(3)
        sb.type('input[placeholder="Username"]', username)
        sb.type('input[placeholder="Password"]', password)
        sb.click('button:contains("Sign In")')
        sb.sleep(8) 

        if "/auth/login" in sb.get_current_url():
            send_telegram_message(f"❌ 账号 {username} 密码登录失败。")
            sb.save_screenshot(f"login_failed_{username}.png")
            return

        if not panel_url:
            print("⚠️ 缺少 panel_url 配置。")
            return

        # 2. 打开面板页面
        print(f"🎯 跳转至目标面板: {panel_url}")
        sb.open(panel_url)
        sb.sleep(6)

        # 3. 🛡️ 强制寻找并破解 CF 验证码
        cf_iframe_selector = 'iframe[src*="challenges.cloudflare.com"]'
        extend_button_selector = 'button:contains("Extend Time")'

        print("🔍 正在等待 Cloudflare 验证码组件加载...")
        
        # 关键修复 1：使用 wait_for_element_present，只要存在于源码中就抓取，无视遮挡
        if not sb.is_element_present(cf_iframe_selector, timeout=15):
            send_telegram_message(f"❌ 账号 {username} | 彻底找不到 CF 验证码，请检查页面结构。")
            sb.save_screenshot(f"no_cf_iframe_{username}.png")
            return

        # 关键修复 2：用 JS 强制把验证码框拉到屏幕绝对居中的位置！
        cf_element = sb.find_element(cf_iframe_selector)
        sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", cf_element)
        sb.sleep(2)
        
        print("🛡️ 捕捉到验证码框 (已居中防遮挡)，正在执行拟人点击...")
        
        try:
            sb.uc_gui_click_captcha()
        except:
            sb.uc_click(cf_iframe_selector)
        
        # 严格轮询等待验证结果
        print("⏳ 正在等待人机验证通过打勾...")
        cf_passed = False
        for _ in range(15): # 最长等待 30 秒
            sb.sleep(2)
            
            # 检查隐藏的 token 是否生成
            response_field = 'input[name="cf-turnstile-response"]'
            if sb.is_element_present(response_field):
                token = sb.get_attribute(response_field, "value")
                if token and len(token) > 10:
                    cf_passed = True
                    break
            
            # 备选检查方案
            try:
                sb.switch_to_frame(cf_iframe_selector)
                if sb.is_element_visible('.cf-success') or sb.is_element_visible('#success-icon'):
                    cf_passed = True
                sb.switch_to_default_content()
                if cf_passed: break
            except:
                sb.switch_to_default_content()

        # 关键修复 3：没通过验证，绝对不允许点续期！
        if not cf_passed:
            send_telegram_message(f"❌ 账号 {username} | 人机验证超时未通过，终止操作。")
            sb.save_screenshot(f"cf_timeout_{username}.png")
            return 

        print("✅ 人机验证已成功打勾！")
        sb.sleep(2) 

        # 4. 点击续期
        if sb.is_element_present(extend_button_selector):
            print("🖱️ 正在点击续期按钮...")
            # 同样把按钮居中
            btn_element = sb.find_element(extend_button_selector)
            sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_element)
            sb.sleep(1)
            
            sb.js_click(extend_button_selector)
            sb.sleep(6)
            
            send_telegram_message(f"✅ {username} | 完美通关！续期请求发送完毕！")
            sb.save_screenshot(f"success_final_{username}.png")
        else:
            send_telegram_message(f"❌ 账号 {username} | 验证通过了，但找不到续期按钮。")
            sb.save_screenshot(f"no_btn_after_cf_{username}.png")

    except Exception as e:
        error_screenshot = f"error_{username}_{int(time.time())}.png"
        sb.save_screenshot(error_screenshot)
        send_telegram_message(f"❌ 账号 {username} 发生异常: {str(e)[:100]}")

def main():
    if not ACCOUNTS:
        return

    with SB(uc=True, headless=False, proxy=PROXY_STR) as sb:
        for account in ACCOUNTS:
            login_and_renew(sb, account)
            sb.sleep(3)

if __name__ == "__main__":
    main()
