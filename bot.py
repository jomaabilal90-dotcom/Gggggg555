import re, asyncio, aiohttp, aiosqlite, time, redis, os
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv("config.env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

RESULTS_PER_PAGE = 25
SEARCH_PAGES = 6
CACHE_TTL = 600
MAX_QUERY_LENGTH = 200

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
session = None
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect("bot.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        date TEXT
        )
        """)
        await db.commit()

async def add_user(uid):
    async with aiosqlite.connect("bot.db") as db:
        await db.execute(
            "INSERT OR IGNORE INTO users VALUES (?,?)",
            (uid, str(datetime.utcnow().date()))
        )
        await db.commit()

async def get_stats():
    async with aiosqlite.connect("bot.db") as db:
        total = await db.execute_fetchone("SELECT COUNT(*) FROM users")
        today = await db.execute_fetchone(
            "SELECT COUNT(*) FROM users WHERE date=?",
            (str(datetime.utcnow().date()),)
        )
    return total[0], today[0]

# ================= CACHE =================
CACHE_PREFIX = "tg_search:"
async def cache_get(query):
    cached = redis_client.get(CACHE_PREFIX + query)
    if cached:
        return cached.split("|")
    return None

async def cache_set(query, results):
    if results:
        redis_client.setex(CACHE_PREFIX + query, CACHE_TTL, "|".join(results))

# ================= SEARCH ENGINE =================
async def fetch_page(url):
    for _ in range(3):
        try:
            async with session.get(url, timeout=15) as r:
                return await r.text()
        except:
            await asyncio.sleep(1)
    return ""

async def search_links(query):
    cached = await cache_get(query)
    if cached:
        return cached

    encoded = quote_plus(query)
    results = set()

    for page in range(SEARCH_PAGES):
        url = f"https://duckduckgo.com/html/?q=site:t.me+{encoded}&s={page*30}"
        html = await fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            m = re.search(r"https://t\.me/[A-Za-z0-9_\/]+", a["href"])
            if m:
                link = m.group(0)
                if "joinchat" not in link:
                    results.add(link)

    results = list(results)
    await cache_set(query, results)
    return results

# ================= PAGINATION =================
user_results = {}

def build_page(query, page):
    results = user_results.get(query, [])
    start = page * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    chunk = results[start:end]

    text = f"Results for: {query}\n\n"
    for r in chunk:
        text += f"{r}\n"

    buttons = []
    if page > 0:
        buttons.append([InlineKeyboardButton(text="Previous", callback_data=f"prev|{query}|{page-1}")])
    if end < len(results):
        buttons.append([InlineKeyboardButton(text="Next", callback_data=f"next|{query}|{page+1}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return text, keyboard

# ================= START =================
@dp.message(Command("start"))
async def start(msg: types.Message):
    await add_user(msg.from_user.id)
    await msg.answer(
        "Telegram Public Search Engine\n\n"
        "Send any word, phrase, symbol, or language to search public Telegram links."
    )

# ================= ADMIN =================
@dp.message(Command("stats"))
async def stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    total, today = await get_stats()
    await msg.answer(f"Total users: {total}\nToday users: {today}")

# ================= SEARCH INPUT =================
@dp.message(F.text)
async def search(msg: types.Message):
    query = msg.text.strip()
    if len(query) > MAX_QUERY_LENGTH:
        await msg.answer("Query too long.")
        return
    await add_user(msg.from_user.id)
    wait = await msg.answer("Searching...")
    results = await search_links(query)
    if not results:
        await wait.edit_text("No results found.")
        return
    user_results[query] = results
    text, kb = build_page(query, 0)
    await wait.edit_text(text, reply_markup=kb)

# ================= PAGINATION HANDLER =================
@dp.callback_query()
async def paginate(call: types.CallbackQuery):
    data = call.data.split("|")
    if data[0] not in ("next","prev"):
        return
    query = data[1]
    page = int(data[2])
    text, kb = build_page(query, page)
    await call.message.edit_text(text, reply_markup=kb)

# ================= RUN =================
async def main():
    global session
    session = aiohttp.ClientSession()
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())