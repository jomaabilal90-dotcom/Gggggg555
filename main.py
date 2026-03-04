import telebot
import requests
from bs4 import BeautifulSoup
import schedule
import time
import re
import sqlite3
import os
from dotenv import load_dotenv

# ==========================
# 🔥 الإعداد
# ==========================
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = "@Bil_storeapps"

if not TOKEN:
    raise Exception("BOT_TOKEN غير موجود")

bot = telebot.TeleBot(TOKEN)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ==========================
# 🔥 قاعدة بيانات + Cache
# ==========================
conn = sqlite3.connect("apps.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS apps (
    link TEXT PRIMARY KEY
)
""")
conn.commit()

CACHE = {}

def exists(link):
    return link in CACHE or cursor.execute(
        "SELECT 1 FROM apps WHERE link=?", (link,)
    ).fetchone() is not None

def save(link):
    cursor.execute("INSERT OR IGNORE INTO apps VALUES (?)", (link,))
    conn.commit()
    CACHE[link] = True


# ==========================
# 🔥 جلب أحدث التطبيقات
# ==========================
def get_latest():
    url = "https://apkpure.com/new-apps"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        apps = []

        for a in soup.find_all("a", href=True):
            name = a.text.strip()
            link = "https://apkpure.com" + a["href"]

            if name and "apk" in link:
                if not re.search(r'game|pubg|free fire|hack|mod', name.lower()):
                    apps.append((name, link))

        return apps[:20]

    except Exception as e:
        print("Fetch error:", e)
        return []


# ==========================
# 🔥 جلب التفاصيل
# ==========================
def get_details(url):

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        desc = soup.find("div", class_="description")
        description = desc.text.strip() if desc else "No description"

        img = soup.find("img")
        image = img["src"] if img and "http" in img["src"] else None

        version = "Unknown"
        size = "Unknown"
        rating = "No Rating"

        for li in soup.find_all("div"):
            text = li.text

            if "Version" in text:
                version = text.strip()

            if "Size" in text:
                size = text.strip()

            if "Rating" in text:
                rating = text.strip()

        return description, image, version, size, rating

    except Exception as e:
        print("Detail error:", e)
        return "No description", None, "Unknown", "Unknown", "No Rating"


# ==========================
# 🔥 النشر الذكي
# ==========================
def post_apps():

    print("🔄 Checking new apps...")

    apps = get_latest()

    for name, link in apps:

        if exists(link):
            continue

        desc, image, version, size, rating = get_details(link)

        text = f"""
📦 {name}

📌 Version: {version}
📏 Size: {size}
⭐ Rating: {rating}

📝 Description:
{desc}

🔗 Source:
{link}
"""

        try:
            keyboard = telebot.types.InlineKeyboardMarkup()
            btn = telebot.types.InlineKeyboardButton("⬇ Download", url=link)
            keyboard.add(btn)

            if image:
                bot.send_photo(CHANNEL, image, caption=text, reply_markup=keyboard)
            else:
                bot.send_message(CHANNEL, text, reply_markup=keyboard)

            save(link)
            time.sleep(1)

        except Exception as e:
            print("Send error:", e)

    print("✅ Cycle Done")


# ==========================
# 🔥 تشغيل مستمر
# ==========================
schedule.every(1).minutes.do(post_apps)

print("🚀 Bot Running Without API...")

while True:
    try:
        schedule.run_pending()
        time.sleep(1)
    except Exception as e:
        print("Loop Error:", e)
        time.sleep(5)