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
        sb.sleep(4)

        # 🛑 尝试清理底部隐私横幅，扫清障碍
        print("🧹 尝试清理底部隐私横幅...")
        js_remove_banner = """
        var btns = document.querySelectorAll('button');
        for(var i=0; i<btns.length; i++) {
            if(btns[i].innerText.includes('Consent')) {
                btns[i].click();
                break;
            }
        }
        """
        sb.execute_script(js_remove_banner)
        sb.sleep(1)

        # =========================================================
        # 🛡️ 第一阶段：按照大神逻辑，优先处理 CF 验证码
        # =========================================================
        print("🔍 [步骤1] 等待页面加载 CF 验证码底层组件...")
        # 只要有 CF 验证，页面必定会注入这个名字的 input 用来存 token
        response_field = 'input[name="cf-turnstile-response"]'

        try:
            sb.wait_for_element_present(response_field, timeout=20)
        except Exception:
            print("⚠️ 20秒内未发现 CF 底层组件。可能页面加载失败，或完全免检。")

        cf_passed = False

        if sb.is_element_present(response_field):
            # 检查是否是 CF “隐形秒过” 模式
            initial_token = sb.get_attribute(response_field, "value")
            if initial_token and len(initial_token) > 10:
                print("✅ 欧皇附体！CF 隐形验证已自动秒过，无需点击。")
                cf_passed = True
            else:
                print("🛡️ 需要手动点击验证。正在将验证码滚动到屏幕正中央...")
                # 核心修复：精准滚动到验证码的父级容器，而不是滚动续期按钮
                sb.execute_script(f"""
                    var ele = document.querySelector('{response_field}');
                    if(ele && ele.parentElement) {{ ele.parentElement.scrollIntoView({{block: 'center'}}); }}
                """)
                sb.sleep(2) # 留出物理坐标稳定和 iframe 渲染的时间

                # 寻找 CF 的框 (采用最广义的选择器)
                cf_iframe = "iframe[src*='cloudflare'], iframe[title*='Cloudflare'], iframe[src*='turnstile'], iframe"
                if sb.is_element_present(cf_iframe):
                    print("🖱️ 正在对 CF 验证框执行物理级模拟鼠标点击...")
                    try:
                        sb.uc_gui_click_captcha()
                    except:
                        try:
                            sb.uc_click(cf_iframe)
                        except Exception as e:
                            print(f"⚠️ 点击指令执行遇阻，但可能已触发: {e}")

                print("⏳ 正在死守人机验证 Token (等待绿勾生成，最多 30 秒)...")
                for i in range(15):
                    sb.sleep(2)
                    token = sb.get_attribute(response_field, "value")
                    if token and len(token) > 10:
                        cf_passed = True
                        print(f"✅ 第 {i*2 + 2} 秒，成功截获 Token！CF 验证完美通关！")
                        break

        # 拦截：如果确实有验证码，但死活没通过，直接终止，绝不瞎点按钮
        if sb.is_element_present(response_field) and not cf_passed:
            send_telegram_message(f"❌ 账号 {username} | 人机验证超时未通过，为防封控已终止操作。")
            sb.save_screenshot(f"cf_fail_{username}.png")
            return

        # =========================================================
        # 🎯 第二阶段：验证通关后，再去找按钮点击
        # =========================================================
        extend_button_xpath = "//button[contains(., 'Extend Time')]"
        print("🔍 [步骤2] 验证已完成，正在寻找并点击续期按钮...")

        try:
            sb.wait_for_element_present(extend_button_xpath, timeout=10)
        except Exception:
            send_telegram_message(f"❌ 账号 {username} | 验证已过，但未找到续期按钮。")
            sb.save_screenshot(f"no_btn_{username}.png")
            return

        print("🖱️ 正在对续期按钮执行终极点击...")
        # 此时再把续期按钮滚动过来
        sb.execute_script(f"""
            var ele = document.evaluate("{extend_button_xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if(ele) {{ ele.scrollIntoView({{block: 'center'}}); }}
        """)
        sb.sleep(1)
        sb.js_click(extend_button_xpath)
        sb.sleep(6)
        
        send_telegram_message(f"✅ 账号 {username} | 完美！续期请求已发送！")
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
