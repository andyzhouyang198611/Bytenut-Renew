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

        # 🛑 铁腕处理隐私横幅 (防止报错崩溃)
        print("🛑 尝试清理底部隐私横幅...")
        try:
            # 设置极短的超时时间，找不到直接略过，绝不报错
            if sb.is_element_visible("button:contains('Consent')", timeout=2):
                sb.click("button:contains('Consent')", timeout=2)
                sb.sleep(1)
        except Exception:
            print("ℹ️ 未发现隐私横幅或点击超时，忽略并继续。")

        # 3. 🎯 严格等待续期按钮
        print("⏳ 正在严格等待核心组件 (续期按钮) 加载...")
        try:
            sb.wait_for_element_present(extend_button_xpath, timeout=20)
            print("✅ 续期按钮已加载。")
        except Exception:
            send_telegram_message(f"❌ 账号 {username} | 等待 20 秒后仍未发现续期按钮。")
            sb.save_screenshot(f"timeout_no_btn_{username}.png")
            return

        # 📜 将按钮滚动到屏幕中央
        print("📜 正在将按钮滚动到屏幕中央...")
        scroll_js = f"""
        var ele = document.evaluate("{extend_button_xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        if(ele) {{ ele.scrollIntoView({{block: 'center'}}); }}
        """
        sb.execute_script(scroll_js)
        sb.sleep(3) 

        # 4. 🛡️ 物理级模拟鼠标点击 CF 验证码 (落实大神逻辑)
        print("🔍 启动主动扫描雷达：查找 Cloudflare 验证码 (轮询 15 秒)...")
        cf_exists = False
        cf_selector = "iframe[src*='cloudflare'], iframe[src*='turnstile'], .cf-turnstile iframe"

        for i in range(15):
            if sb.is_element_present(cf_selector):
                cf_exists = True
                print(f"🎯 报告！在第 {i+1} 秒成功捕捉到验证码框！")
                break
            sb.sleep(1)

        if cf_exists:
            print("🖱️ 正在执行物理级鼠标轨迹模拟点击...")
            sb.sleep(1)
            try:
                # 方案 A：使用底层的 GUI 鼠标滑动+点击算法破解
                sb.uc_gui_click_captcha()
            except:
                try:
                    # 方案 B：直接将虚拟鼠标移动到该元素的坐标上执行原生左键单击
                    sb.uc_click(cf_selector)
                except Exception as e:
                    print(f"⚠️ 物理点击抛出警告 (可能依然成功): {e}")
            
            print("⏳ 正在死守人机验证 Token 生成 (最多30秒)...")
            cf_passed = False
            for i in range(15): 
                sb.sleep(2)
                response_field = 'input[name="cf-turnstile-response"]'
                if sb.is_element_present(response_field):
                    token = sb.get_attribute(response_field, "value")
                    if token and len(token) > 10:
                        cf_passed = True
                        print(f"✅ 第 {i*2 + 2} 秒时，Token 获取成功！人机验证通关！")
                        break
            
            if not cf_passed:
                print("⚠️ Token 获取超时！极有可能是 CF 隐形验证放行，准备强攻续期按钮...")
        else:
            print("ℹ️ 15秒雷达扫描未发现验证码，确认为免检状态，直接放行。")

        # 5. 🖱️ 最终点击
        print("🖱️ 正在对续期按钮执行终极点击...")
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
