import os
import asyncio
import logging
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from aiogram import Bot

# --- الإعدادات الفنية ---
API_TOKEN = '8753647023:AAGHqY5MMtpC9VyvdteBdvrfSb2lusUDy0Q'
CHANNEL_ID = '-1003763158509'
post_counter = 1

# إعداد السجلات لمراقبة أداء البوت
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
bot = Bot(token=API_TOKEN)

def generate_professional_chart():
    """توليد رسم بياني فائق الدقة بهوية TON"""
    try:
        # جلب بيانات 24 ساعة بفاصل 5 دقائق
        data = yf.download('TON1-USD', period='1d', interval='5m', progress=False)
        if data.empty or len(data) < 5:
            return None

        plt.clf()
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # رسم المنحنى بلون TON الرسمي
        ax.plot(data.index, data['Close'], color='#0088cc', linewidth=2, antialiased=True)
        ax.fill_between(data.index, data['Close'], color='#0088cc', alpha=0.15)
        
        # تنسيقات جمالية واحترافية
        ax.set_title('TON / USD - Live High Precision Chart', color='#55bcff', fontsize=12, pad=15)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.grid(True, linestyle='--', alpha=0.1)
        
        # إزالة الحواف (Minimalist Look)
        for spine in ax.spines.values():
            spine.set_visible(False)
            
        chart_filename = f"ton_price_{int(datetime.now().timestamp())}.png"
        plt.savefig(chart_filename, bbox_inches='tight', dpi=120)
        plt.close(fig) # مسح الرسم من الذاكرة تماماً
        return chart_filename
    except Exception as e:
        logging.error(f"Error drawing chart: {e}")
        return None

async def main_loop():
    global post_counter
    logging.info("TON Price Bot is now LIVE.")

    while True:
        loop_start = asyncio.get_event_loop().time()
        
        try:
            # 1. جلب بيانات السعر بدقة عالية
            ticker = yf.Ticker("TON1-USD")
            hist = ticker.history(period="1d")
            if hist.empty:
                raise Exception("Data source unavailable")
            
            current_price = hist['Close'].iloc[-1]
            opening_price = hist['Open'].iloc[0]
            price_change = ((current_price - opening_price) / opening_price) * 100
            trend_icon = "📈" if price_change >= 0 else "📉"

            # 2. إعداد التوقيت
            now = datetime.now()
            full_date = now.strftime("%A, %B %d, %Y")
            exact_time = now.strftime("%H:%M:%S UTC")

            # 3. إنشاء المخطط
            chart_file = generate_professional_chart()

            # 4. صياغة الرسالة الاحترافية (English Only)
            caption = (
                f"💎 **TON COIN REAL-TIME UPDATE**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 **Date:** {full_date}\n"
                f"⏰ **Time:** {exact_time}\n"
                f"💰 **Price:** `${current_price:.4f} USD`\n"
                f"{trend_icon} **24h Change:** {price_change:+.2f}%\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 **Channel Description:**\n"
                f"This channel provides high-precision, automated updates on TON (The Open Network) prices and market trends. Data is synchronized every 3 minutes for maximum accuracy.\n\n"
                f"🔗 **Follow Us:** @TON_Price_Live_B\n"
                f"🔢 **Post Number:** #{post_counter}\n\n"
                f"#TON #Toncoin #Telegram #Crypto #Blockchain #PriceAction #MarketUpdate #Web3 #Fintech #GlobalMarkets"
            )

            # 5. الإرسال للقناة
            if chart_file and os.path.exists(chart_file):
                with open(chart_file, 'rb') as photo:
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption, parse_mode="Markdown")
                os.remove(chart_file) # حذف الصورة لعدم ملء مساحة الهاردسك
            else:
                await bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="Markdown")

            logging.info(f"Post #{post_counter} sent successfully.")
            post_counter += 1

        except Exception as e:
            logging.error(f"Post Loop Error: {e}")

        # ضمان الإرسال كل 3 دقائق (180 ثانية) بدقة
        execution_time = asyncio.get_event_loop().time() - loop_start
        wait_time = max(180 - execution_time, 10)
        await asyncio.sleep(wait_time)

if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot execution stopped.")