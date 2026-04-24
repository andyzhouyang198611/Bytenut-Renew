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
        
        extend_button_xpath = "//button[contains(., 'Extend Time')]"
        cf_iframe_xpath = "//iframe[contains(@src, 'cloudflare')]"
        privacy_btn_xpath = "//button[contains(., 'Consent')]"

        # 🛑 关键修复 1：关掉底部那个巨大的白色隐私横幅 (防止遮挡)
        sb.sleep(3)
        if sb.is_element_visible(privacy_btn_xpath):
            print("🛑 发现底部隐私横幅，正在点击关闭...")
            sb.click(privacy_btn_xpath)
            sb.sleep(1)

        # 3. 🎯 严格等待续期按钮
        print("⏳ 正在严格等待核心组件 (续期按钮) 加载...")
        try:
            sb.wait_for_element_present(extend_button_xpath, timeout=20)
            print("✅ 续期按钮已加载。")
        except Exception:
            send_telegram_message(f"❌ 账号 {username} | 等待 20 秒后仍未发现续期按钮。")
            sb.save_screenshot(f"timeout_no_btn_{username}.png")
            return

        # 📜 关键修复 2：彻底抛弃 arguments，使用纯净的 JS 字符串执行居中滚动
        print("📜 正在将按钮滚动到屏幕中央...")
        scroll_js = f"""
        var ele = document.evaluate("{extend_button_xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        if(ele) {{ ele.scrollIntoView({{block: 'center'}}); }}
        """
        sb.execute_script(scroll_js)
        sb.sleep(2) 

        # 4. 🛡️ 强制盯防 CF 验证码 
        print("🔍 检查是否存在 Cloudflare 验证码 (主动死守最多 10 秒)...")
        cf_exists = False
        try:
            sb.wait_for_element_present(cf_iframe_xpath, timeout=10)
            cf_exists = True
        except Exception:
            pass

        if cf_exists:
            print("🛡️ 成功捕捉到延迟加载的验证码框，准备模拟点击...")
            try:
                sb.uc_gui_click_captcha()
            except:
                try:
                    sb.uc_click(cf_iframe_xpath)
                except:
                    sb.js_click(cf_iframe_xpath)
            
            print("⏳ 正在等待人机验证 Token 生成...")
            cf_passed = False
            for _ in range(15): 
                sb.sleep(2)
                response_field = 'input[name="cf-turnstile-response"]'
                if sb.is_element_present(response_field):
                    token = sb.get_attribute(response_field, "value")
                    if token and len(token) > 10:
                        cf_passed = True
                        break
            
            if cf_passed:
                print("✅ 人机验证已成功通过！")
            else:
                print("⚠️ 人机验证 Token 获取超时，将强行尝试点击续期...")
        else:
            print("ℹ️ 10秒内未刷出 CF 验证码，假定本次直接免检通过。")

        # 5. 🖱️ 最终点击
        print("🖱️ 正在点击续期按钮...")
        sb.js_click(extend_button_xpath)
        sb.sleep(6)
        
        send_telegram_message(f"✅ 账号 {username} | 续期指令执行完毕！")
        sb.save_screenshot(f"success_final_{username}.png")

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
