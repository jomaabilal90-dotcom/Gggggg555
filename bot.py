import subprocess
import sys

# -----------------------------
# تثبيت المكتبات تلقائياً إذا لم تكن موجودة
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import requests
except ImportError:
    install("requests")
    import requests

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
except ImportError:
    install("python-telegram-bot==20.3")
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
# -----------------------------

# -----------------------------
# إعدادات البوت
BOT_TOKEN = "8619373733:AAGZ6gqSzoQYIBazJk_dVhdUI9V9w9iXhuE"
ADMIN_ID = 8639822125
GEMINI_KEY = "AIzaSyD9jm4Za2BIyvJYwhEiJcjN_rGI4saKc24"
# -----------------------------

# حفظ سياق المستخدم
user_contexts = {}

# ----- الأوامر -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Help", callback_data='help')],
        [InlineKeyboardButton("Privacy & Terms", callback_data='policy')],
        [InlineKeyboardButton("Clear Context", callback_data='clear')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        "Hello! 👋 Welcome to your multilingual AI chat bot. "
        "I can answer your questions concisely in your language. "
        "Use the commands below to explore features and manage your chat effectively."
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛠 Help Guide:\n"
        "1. Type any question and I will reply in your language.\n"
        "2. /start - Welcome message and commands.\n"
        "3. /clear - Reset chat context.\n"
        "4. /policy - Read Privacy & Terms.\n"
    )
    await update.message.reply_text(text)

async def policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 Privacy & Terms:\n"
        "1. All chats are private and not shared.\n"
        "2. No personal info will be stored permanently.\n"
        "3. Use responsibly. Misuse may lead to bans.\n"
    )
    await update.message.reply_text(text)

async def clear_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_contexts[update.message.from_user.id] = []
    await update.message.reply_text("🗑 Chat context cleared successfully!")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_ID:
        total_users = len(user_contexts)
        await update.message.reply_text(f"Total users: {total_users}")
    else:
        await update.message.reply_text("❌ You are not authorized.")

# ----- دالة Gemini AI -----
def query_gemini(prompt, user_lang="en"):
    url = f"https://gemini.googleapis.com/v1beta2/models/text-bison-001:generateText?key={GEMINI_KEY}"
    full_prompt = f"Respond concisely in {user_lang}: {prompt}"
    try:
        response = requests.post(url, json={"prompt": full_prompt, "temperature": 0.5, "maxOutputTokens": 200}, timeout=15)
        response.raise_for_status()
        return response.json()['candidates'][0]['output']
    except Exception as e:
        return f"⚠️ AI service error. Please try again later. ({e})"

# ----- الردود الذكية -----
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    msg = update.message.text
    user_lang = update.effective_user.language_code or "en"

    # حفظ السياق
    if user_id not in user_contexts:
        user_contexts[user_id] = []
    user_contexts[user_id].append(msg)

    # الرد
    reply = query_gemini(msg, user_lang)
    await update.message.reply_text(reply)

# -----------------------------
# تشغيل البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("policy", policy))
app.add_handler(CommandHandler("clear", clear_context))
app.add_handler(CommandHandler("admin", admin_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

print("✅ Bot is running...")
app.run_polling()