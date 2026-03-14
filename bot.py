import re
import asyncio
import aiohttp
import aiosqlite
import time
import redis
import os
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from dotenv import load_dotenv

# ================= CONFIG =================
# إنشاء ملف config.env إذا لم يكن موجوداً
if not os.path.exists("config.env"):
    with open("config.env", "w") as f:
        f.write("""BOT_TOKEN=8280439521:AAGIcJv0iIFY5gpjZUIkjx4K_Hccb0TSY34
ADMIN_ID=8639822125
REDIS_HOST=localhost
REDIS_PORT=6379
""")

load_dotenv("config.env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

RESULTS_PER_PAGE = 25
SEARCH_PAGES = 6
CACHE_TTL = 600
MAX_QUERY_LENGTH = 200

# ================= INITIALIZATION =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
session = None
redis_client = None
user_results = {}

# ================= DATABASE =================
async def init_db():
    """تهيئة قاعدة البيانات"""
    async with aiosqlite.connect("bot.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        date TEXT
        )
        """)
        await db.commit()

async def add_user(uid):
    """إضافة مستخدم جديد إلى قاعدة البيانات"""
    async with aiosqlite.connect("bot.db") as db:
        await db.execute(
            "INSERT OR IGNORE INTO users VALUES (?,?)",
            (uid, str(datetime.utcnow().date()))
        )
        await db.commit()

async def get_stats():
    """الحصول على إحصائيات المستخدمين"""
    async with aiosqlite.connect("bot.db") as db:
        total = await db.execute_fetchone("SELECT COUNT(*) FROM users")
        today = await db.execute_fetchone(
            "SELECT COUNT(*) FROM users WHERE date=?",
            (str(datetime.utcnow().date()),)
        )
    return total[0] if total else 0, today[0] if today else 0

# ================= CACHE =================
def init_redis():
    """تهيئة اتصال Redis"""
    global redis_client
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST, 
            port=REDIS_PORT, 
            decode_responses=True,
            socket_connect_timeout=2
        )
        redis_client.ping()
        print("✅ Redis connected successfully")
    except redis.ConnectionError:
        print("⚠️ Redis not available, caching disabled")
        redis_client = None

CACHE_PREFIX = "tg_search:"

async def cache_get(query):
    """الحصول على نتائج مخزنة من Redis"""
    if not redis_client:
        return None
    try:
        cached = redis_client.get(CACHE_PREFIX + query)
        if cached:
            return cached.split("|")
    except:
        pass
    return None

async def cache_set(query, results):
    """تخزين النتائج في Redis"""
    if not redis_client or not results:
        return
    try:
        redis_client.setex(CACHE_PREFIX + query, CACHE_TTL, "|".join(results))
    except:
        pass

# ================= SEARCH ENGINE =================
async def fetch_page(session, url):
    """جلب صفحة ويب مع إعادة المحاولة"""
    for attempt in range(3):
        try:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < 2:
                await asyncio.sleep(2)
    return ""

async def search_links(query):
    """البحث عن روابط Telegram"""
    # التحقق من الذاكرة المؤقتة
    cached = await cache_get(query)
    if cached:
        print(f"✅ Cache hit for: {query}")
        return cached

    print(f"🔍 Searching for: {query}")
    encoded = quote_plus(query)
    results = set()
    
    # عناوين URL للبحث في محركات مختلفة
    search_urls = []
    for page in range(SEARCH_PAGES):
        # DuckDuckGo
        search_urls.append(f"https://duckduckgo.com/html/?q=site:t.me+{encoded}&s={page*30}")
        # Google (بديل)
        search_urls.append(f"https://www.google.com/search?q=site:t.me+{encoded}&start={page*10}")
        # Bing
        search_urls.append(f"https://www.bing.com/search?q=site:t.me+{encoded}&first={page*10+1}")

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_page(session, url) for url in search_urls[:SEARCH_PAGES*2]]  # نأخذ أول عدد معقول من الصفحات
        html_pages = await asyncio.gather(*tasks)

    for html in html_pages:
        if html:
            soup = BeautifulSoup(html, "html.parser")
            # البحث عن روابط Telegram
            for a in soup.find_all("a", href=True):
                # أنماط مختلفة للروابط
                patterns = [
                    r"https://t\.me/[A-Za-z0-9_]+",
                    r"https://telegram\.me/[A-Za-z0-9_]+",
                    r"https://t\.me/[A-Za-z0-9_]+/\d+",
                    r"https://t\.me/joinchat/[A-Za-z0-9_-]+"
                ]
                for pattern in patterns:
                    m = re.search(pattern, a["href"])
                    if m:
                        link = m.group(0)
                        # تجاهل الروابط المكررة وبعض الأنواع
                        if "share" not in link and "contact" not in link:
                            results.add(link)

    results = list(results)[:200]  # حد أقصى 200 نتيجة
    await cache_set(query, results)
    print(f"✅ Found {len(results)} results for: {query}")
    return results

# ================= PAGINATION =================
def build_page(query, page):
    """بناء صفحة النتائج مع أزرار التنقل"""
    results = user_results.get(query, [])
    if not results:
        return "No results found.", None
    
    start = page * RESULTS_PER_PAGE
    end = min(start + RESULTS_PER_PAGE, len(results))
    chunk = results[start:end]

    text = f"🔍 <b>نتائج البحث عن:</b> {query}\n"
    text += f"📊 <b>إجمالي النتائج:</b> {len(results)}\n"
    text += f"📄 <b>الصفحة:</b> {page + 1}/{(len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE}\n\n"
    
    for i, r in enumerate(chunk, start=1):
        text += f"{i}. <a href='{r}'>{r}</a>\n"

    # أزرار التنقل
    buttons = []
    nav_row = []
    
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="◀️ السابق", 
            callback_data=f"nav|{query}|{page-1}"
        ))
    
    if end < len(results):
        nav_row.append(InlineKeyboardButton(
            text="التالي ▶️", 
            callback_data=f"nav|{query}|{page+1}"
        ))
    
    if nav_row:
        buttons.append(nav_row)
    
    # زر حذف النتائج المؤقتة
    buttons.append([
        InlineKeyboardButton(
            text="🗑️ مسح النتائج", 
            callback_data=f"clear|{query}"
        )
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return text, keyboard

# ================= HANDLERS =================
@dp.message(Command("start"))
async def start_command(msg: types.Message):
    """معالج أمر /start"""
    await add_user(msg.from_user.id)
    welcome_text = """
🚀 <b>Telegram Search Engine</b>

🔍 <b>محرك بحث متخصص في روابط تيليجرام</b>

📝 <b>كيفية الاستخدام:</b>
• أرسل أي كلمة أو جملة للبحث
• البحث يشمل القنوات والمجموعات العامة
• النتائج مرتبة ومقسمة لصفحات

🎯 <b>الأوامر المتاحة:</b>
/start - عرض هذه الرسالة
/stats - إحصائيات البوت (للمسؤول فقط)

✨ <b>مميزات البوت:</b>
• بحث في عدة محركات
• نتائج فورية
• تصفح سهل للنتائج
• تحديث يومي للبيانات

<i>@Ahmed7Yahia</i>
    """
    await msg.answer(welcome_text, parse_mode="HTML")

@dp.message(Command("stats"))
async def stats_command(msg: types.Message):
    """معالج أمر /stats (للمسؤول فقط)"""
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("⛔ هذا الأمر متاح فقط للمسؤول!")
        return
    
    total, today = await get_stats()
    
    # معلومات Redis
    redis_status = "✅ متصل" if redis_client and redis_client.ping() else "❌ غير متصل"
    
    stats_text = f"""
📊 <b>إحصائيات البوت</b>

👥 <b>المستخدمين:</b>
• الإجمالي: {total}
• اليوم: {today}

⚙️ <b>الحالة:</b>
• Redis: {redis_status}
• الذاكرة المؤقتة: {CACHE_TTL} ثانية
• النتائج لكل صفحة: {RESULTS_PER_PAGE}

🤖 <b>معلومات البوت:</b>
• وقت التشغيل: جاري العمل
• آخر تحديث: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
    """
    
    await msg.answer(stats_text, parse_mode="HTML")

@dp.message(F.text)
async def search_handler(msg: types.Message):
    """معالج رسائل البحث"""
    query = msg.text.strip()
    
    # التحقق من طول النص
    if len(query) > MAX_QUERY_LENGTH:
        await msg.answer(f"❌ النص طويل جداً! الحد الأقصى {MAX_QUERY_LENGTH} حرف.")
        return
    
    # التحقق من النص الفارغ
    if not query:
        await msg.answer("❌ الرجاء إدخال نص للبحث!")
        return
    
    await add_user(msg.from_user.id)
    
    # إرسال رسالة الانتظار
    wait_msg = await msg.answer("🔍 جاري البحث...")
    
    try:
        # البحث
        results = await search_links(query)
        
        if not results:
            await wait_msg.edit_text("❌ لم يتم العثور على نتائج. جرب كلمات بحث مختلفة.")
            return
        
        # تخزين النتائج للمستخدم
        user_results[query] = results
        
        # عرض الصفحة الأولى
        text, kb = build_page(query, 0)
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ حدث خطأ: {str(e)}")

@dp.callback_query()
async def callback_handler(call: types.CallbackQuery):
    """معالج أزرار التنقل"""
    data = call.data.split("|")
    
    if data[0] == "nav":
        # التنقل بين الصفحات
        query = data[1]
        page = int(data[2])
        
        if query in user_results:
            text, kb = build_page(query, page)
            await call.message.edit_text(
                text, 
                parse_mode="HTML", 
                reply_markup=kb, 
                disable_web_page_preview=True
            )
        else:
            await call.answer("❌ انتهت صلاحية النتائج، ابحث مجدداً!")
            
    elif data[0] == "clear":
        # مسح النتائج المؤقتة
        query = data[1]
        if query in user_results:
            del user_results[query]
            await call.message.edit_text("✅ تم مسح النتائج. ابحث مجدداً!")
        else:
            await call.answer("❌ لا توجد نتائج لمسحها!")
    
    await call.answer()

# ================= MAIN =================
async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    global session
    
    print("🚀 Starting Telegram Search Bot...")
    
    # تهيئة قاعدة البيانات
    await init_db()
    print("✅ Database initialized")
    
    # تهيئة Redis
    init_redis()
    
    # بدء البوت
    print(f"🤖 Bot started! Admin ID: {ADMIN_ID}")
    print("✅ Bot is ready to work!")
    
    try:
        await dp.start_polling(bot)
    finally:
        if session:
            await session.close()

# ================= ENTRY POINT =================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")