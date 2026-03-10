import telebot
import google.generativeai as genai
from telebot.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
from datetime import datetime, timedelta
import threading
import time
from functools import wraps
import hashlib
import queue
from concurrent.futures import ThreadPoolExecutor
import logging
from cachetools import TTLCache

# ==================== التهيئة ====================
TOKEN = "8678280549:AAEgCJgOncWH6rWWsNZqQYfllMcAf33qVN4"
GEMINI_KEY = "AIzaSyD9jm4Za2BIyvJYwhEiJcjN_rGI4saKc24"
ADMIN_ID = 8639822125

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تهيئة البوت والذكاء الاصطناعي
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=5)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

# نظام التخزين المؤقت
context_cache = TTLCache(maxsize=1000, ttl=1800)  # 30 دقيقة
response_cache = TTLCache(maxsize=500, ttl=300)   # 5 دقائق

# تجمع الخيوط
executor = ThreadPoolExecutor(max_workers=10)

# ==================== قاعدة البيانات المحسنة ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot_data.db', check_same_thread=False)
        self.lock = threading.Lock()
        self.create_tables()
        
    def create_tables(self):
        with self.lock:
            c = self.conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS users
                        (user_id INTEGER PRIMARY KEY, 
                         first_seen TIMESTAMP,
                         last_active TIMESTAMP,
                         username TEXT,
                         first_name TEXT,
                         language TEXT,
                         total_messages INTEGER DEFAULT 0)''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS daily_stats
                        (date TEXT PRIMARY KEY,
                         new_users INTEGER DEFAULT 0,
                         total_users INTEGER DEFAULT 0,
                         messages INTEGER DEFAULT 0)''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS blocked_users
                        (user_id INTEGER PRIMARY KEY,
                         reason TEXT,
                         blocked_at TIMESTAMP)''')
            self.conn.commit()
    
    def update_user(self, user):
        with self.lock:
            user_id = user.id
            username = user.username or ""
            first_name = user.first_name or ""
            language = user.language_code or "en"
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            
            c = self.conn.cursor()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            if not c.fetchone():
                c.execute("""INSERT INTO users 
                            (user_id, first_seen, last_active, username, first_name, language, total_messages) 
                            VALUES (?, ?, ?, ?, ?, ?, 0)""",
                          (user_id, now, now, username, first_name, language))
                
                c.execute("INSERT OR IGNORE INTO daily_stats (date, new_users, total_users, messages) VALUES (?, 0, 0, 0)", (today,))
                c.execute("UPDATE daily_stats SET new_users = new_users + 1 WHERE date = ?", (today,))
            else:
                c.execute("""UPDATE users SET 
                            last_active = ?, 
                            username = ?, 
                            first_name = ?, 
                            language = ?,
                            total_messages = total_messages + 1 
                            WHERE user_id = ?""",
                          (now, username, first_name, language, user_id))
                
                c.execute("UPDATE daily_stats SET messages = messages + 1 WHERE date = ?", (today,))
            
            # تحديث إجمالي المستخدمين
            total = self.get_total_users()
            c.execute("UPDATE daily_stats SET total_users = ? WHERE date = ?", (total, today))
            
            self.conn.commit()
    
    def get_total_users(self):
        with self.lock:
            c = self.conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            return c.fetchone()[0]
    
    def get_daily_stats(self):
        today = datetime.now().strftime("%Y-%m-%d")
        with self.lock:
            c = self.conn.cursor()
            c.execute("SELECT new_users, total_users, messages FROM daily_stats WHERE date = ?", (today,))
            result = c.fetchone()
            if result:
                return {"new": result[0], "total": result[1], "messages": result[2]}
            return {"new": 0, "total": self.get_total_users(), "messages": 0}
    
    def get_active_today(self):
        with self.lock:
            c = self.conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE DATE(last_active) = DATE('now')")
            return c.fetchone()[0]
    
    def is_blocked(self, user_id):
        with self.lock:
            c = self.conn.cursor()
            c.execute("SELECT * FROM blocked_users WHERE user_id = ?", (user_id,))
            return c.fetchone() is not None

db = Database()

# ==================== الدوال المساعدة المحسنة ====================
def admin_only(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if message.from_user.id == ADMIN_ID:
            return func(message, *args, **kwargs)
        else:
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
    return wrapper

def rate_limit(max_per_minute=30):
    def decorator(func):
        calls = {}
        @wraps(func)
        def wrapper(message, *args, **kwargs):
            user_id = message.from_user.id
            now = time.time()
            
            if user_id in calls:
                if now - calls[user_id] < 60.0 / max_per_minute:
                    bot.reply_to(message, "⏳ من فضلك انتظر قليلاً قبل إرسال رسالة أخرى.")
                    return
            
            calls[user_id] = now
            return func(message, *args, **kwargs)
        return wrapper
    return decorator

def get_context_key(user_id):
    return f"context_{user_id}"

# ==================== الأوامر المحسنة ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        db.update_user(message.from_user)
        
        welcome_text = """
🤖 Welcome to AI Assistant Bot!

I'm your intelligent AI companion powered by Google Gemini. I can help you with any question or task in any language. Just send me a message and I'll respond concisely and accurately!

✨ Features:
• Smart AI responses in any language
• Completely FREE
• Context memory (use /clear to reset)
• Private & secure

📋 Available Commands:
/start - Welcome message
/help - How to use & troubleshooting
/privacy - Privacy policy & rules
/clear - Clear conversation context
/stats - Bot statistics (admin only)

Simply type your question and I'll answer! 🚀
        """
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("📝 Start Chatting", callback_data="chat"),
            InlineKeyboardButton("❓ Help", callback_data="help")
        )
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in start: {e}")
        bot.reply_to(message, "عذراً، حدث خطأ. الرجاء المحاولة مرة أخرى.")

@bot.message_handler(commands=['help'])
def send_help(message):
    try:
        db.update_user(message.from_user)
        
        help_text = """
❓ How to Use This Bot

📝 Basic Usage:
1. Simply type any question in any language
2. The AI will respond concisely and accurately
3. Use /clear to reset conversation context

🔄 Common Issues:

• No response? - The AI might be processing, wait a few seconds
• Wrong answer? - Try rephrasing your question
• Context issues? - Use /clear to reset
• Language? - The bot supports ALL languages automatically

💡 Tips:
- Be specific in your questions
- Use /clear for a fresh start
- The bot remembers conversation context

⚡ Need more help?
Just describe your issue and I'll assist you!
        """
        
        bot.send_message(message.chat.id, help_text)
    except Exception as e:
        logger.error(f"Error in help: {e}")
        bot.reply_to(message, "عذراً، حدث خطأ. الرجاء المحاولة مرة أخرى.")

@bot.message_handler(commands=['privacy'])
def send_privacy(message):
    try:
        db.update_user(message.from_user)
        
        privacy_text = """
🔒 Privacy Policy & Terms of Use

📊 Data Collection:
• User ID (anonymous)
• Username (optional)
• First name
• Chat messages (for AI responses)
• Last activity time

🛡️ How We Use Data:
• Improve bot performance
• Track usage statistics
• Provide AI responses
• Maintain conversation context

✅ Your Rights:
• Request data deletion
• Clear context anytime (/clear)
• Stop using bot anytime

⚠️ Rules:
• No illegal content
• No harassment
• No spam
• No sharing sensitive info
• Use responsibly

📧 Contact admin for issues

By using this bot, you agree to these terms.
        """
        
        bot.send_message(message.chat.id, privacy_text)
    except Exception as e:
        logger.error(f"Error in privacy: {e}")
        bot.reply_to(message, "عذراً، حدث خطأ. الرجاء المحاولة مرة أخرى.")

@bot.message_handler(commands=['clear'])
def clear_context(message):
    try:
        db.update_user(message.from_user)
        user_id = message.from_user.id
        context_key = get_context_key(user_id)
        
        if context_key in context_cache:
            del context_cache[context_key]
        
        bot.reply_to(message, "🧹 Conversation context cleared!\n\nStart fresh with your new question.")
    except Exception as e:
        logger.error(f"Error in clear: {e}")
        bot.reply_to(message, "عذراً، حدث خطأ. الرجاء المحاولة مرة أخرى.")

@bot.message_handler(commands=['stats'])
@admin_only
def send_stats(message):
    try:
        stats = db.get_daily_stats()
        active_today = db.get_active_today()
        
        # إحصائيات إضافية
        total_messages = stats["messages"]
        
        stats_text = f"""
📊 Bot Statistics

👥 Total Users: {stats['total']:,}
🆕 New Today: {stats['new']:,}
✨ Active Today: {active_today:,}
💬 Messages Today: {total_messages:,}
📅 Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}

✅ System Status: Online
🤖 AI Model: Gemini Pro
⚡ Response Time: Fast
        """
        
        bot.send_message(message.chat.id, stats_text)
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        bot.reply_to(message, "عذراً، حدث خطأ في جلب الإحصائيات.")

# ==================== معالجة الرسائل المحسنة ====================
@bot.message_handler(func=lambda message: True)
@rate_limit(max_per_minute=20)
def handle_message(message):
    try:
        # تجاهل الأوامر
        if message.text.startswith('/'):
            return
        
        # التحقق من الحظر
        if db.is_blocked(message.from_user.id):
            return
        
        db.update_user(message.from_user)
        user_id = message.from_user.id
        
        # التحقق من التكرار
        cache_key = f"{user_id}_{hashlib.md5(message.text.encode()).hexdigest()}"
        if cache_key in response_cache:
            bot.reply_to(message, response_cache[cache_key])
            return
        
        # إظهار مؤشر الكتابة
        bot.send_chat_action(message.chat.id, 'typing')
        
        # الحصول على الرد من الذكاء الاصطناعي
        def get_ai_response():
            try:
                context_key = get_context_key(user_id)
                chat = context_cache.get(context_key)
                
                if not chat:
                    chat = model.start_chat()
                    context_cache[context_key] = chat
                
                response = chat.send_message(message.text, stream=False)
                return response.text
            except Exception as e:
                logger.error(f"AI Error: {e}")
                return None
        
        # تنفيذ في خيط منفصل
        future = executor.submit(get_ai_response)
        
        try:
            response_text = future.result(timeout=15)
            
            if response_text:
                # تقصير الرد إذا كان طويلاً
                if len(response_text) > 4000:
                    response_text = response_text[:4000] + "..."
                
                bot.reply_to(message, response_text)
                response_cache[cache_key] = response_text
            else:
                bot.reply_to(message, "عذراً، حدث خطأ في الذكاء الاصطناعي. الرجاء المحاولة مرة أخرى.")
                
        except TimeoutError:
            bot.reply_to(message, "⏱️ استغرق الرد وقتاً طويلاً. الرجاء المحاولة مرة أخرى.")
            
    except Exception as e:
        logger.error(f"Error in message handler: {e}")
        bot.reply_to(message, "حدث خطأ. الرجاء المحاولة مرة أخرى.")

# ==================== معالجة الكول باك ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        if call.data == "chat":
            bot.answer_callback_query(call.id, "Start typing your question!")
            bot.send_message(call.message.chat.id, "💭 Go ahead, type your question...")
        elif call.data == "help":
            bot.answer_callback_query(call.id)
            send_help(call.message)
    except Exception as e:
        logger.error(f"Error in callback: {e}")

# ==================== تحديث الإحصائيات اليومية ====================
def daily_stats_updater():
    while True:
        try:
            now = datetime.now()
            next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            time_to_wait = (next_day - now).total_seconds()
            time.sleep(time_to_wait)
            
            # تنظيف الذاكرة المؤقتة
            context_cache.clear()
            response_cache.clear()
            
            logger.info("Daily stats updated and cache cleared")
            
        except Exception as e:
            logger.error(f"Error in daily updater: {e}")
            time.sleep(3600)  # انتظر ساعة إذا حدث خطأ

# بدء تحديث الإحصائيات
stats_thread = threading.Thread(target=daily_stats_updater, daemon=True)
stats_thread.start()

# ==================== إعداد الأوامر ====================
def setup_bot_commands():
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("help", "How to use & help"),
        BotCommand("privacy", "Privacy policy & rules"),
        BotCommand("clear", "Clear conversation context"),
        BotCommand("stats", "Bot statistics (admin only)")
    ]
    bot.set_my_commands(commands)

# ==================== تشغيل البوت ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 AI Assistant Bot is starting...")
    print("=" * 50)
    print(f"🤖 Admin ID: {ADMIN_ID}")
    print(f"📊 Database: SQLite")
    print(f"🤖 AI Model: Gemini Pro")
    print(f"⚡ Threads: 5")
    print(f"💾 Cache: Enabled")
    print("=" * 50)
    print("✅ Bot is running! Press Ctrl+C to stop")
    print("=" * 50)
    
    setup_bot_commands()
    
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(5)