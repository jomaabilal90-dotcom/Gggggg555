import requests
from bs4 import BeautifulSoup
import time
import logging
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import random

# إعدادات التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# معلومات البوت والقناة
BOT_TOKEN = "8774161772:AAGXbt4UDT0-NHcpFFFNd7lbIB6UBZm6mAo"
CHANNEL_ID = "@Bil_storeapps"
INTERVAL = 120  # ثانية (دقيقتان)

# قائمة التطبيقات الشهيرة (غير الألعاب)
APPS_LIST = [
    "telegram",
    "whatsapp",
    "instagram",
    "facebook",
    "tiktok",
    "youtube",
    "chrome",
    "firefox",
    "vlc",
    "spotify",
    "netflix",
    "messenger",
    "discord",
    "slack",
    "microsoft-word",
    "microsoft-excel",
    "adobe-photoshop",
    "adobe-reader",
    "winrar",
    "7zip",
    "notepad++",
    "visual-studio-code",
    "git",
    "nodejs",
    "python",
    "java",
    "eclipse",
    "gimp",
    "blender",
    "audacity",
    "obs-studio",
    "handbrake",
    "ffmpeg",
    "qbittorrent",
    "transmission",
    "putty",
    "mremoteng",
    "keepass",
    "bitwarden",
    "lastpass",
    "nordvpn",
    "expressvpn",
    "dropbox",
    "googledrive",
    "onedrive",
    "mega",
    "torproject",
    "teamviewer",
    "anydesk",
    "notion",
    "todoist",
]

class APKPureBot:
    def __init__(self, bot_token, channel_id):
        self.bot = Bot(token=bot_token)
        self.channel_id = channel_id
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.sent_apps = set()
        
    def get_app_info(self, app_name):
        """جلب معلومات التطبيق من APKpure مع رابط تحميل APK المباشر"""
        try:
            # البحث عن التطبيق
            search_url = f"https://apkpure.com/search?q={app_name}"
            response = self.session.get(search_url, timeout=10)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                logger.warning(f"لم يتم الحصول على معلومات {app_name}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            app_elem = soup.find('div', class_='app-item')
            
            if not app_elem:
                logger.warning(f"التطبيق {app_name} لم يتم العثور عليه")
                return None
            
            # استخراج البيانات الأساسية
            title_elem = app_elem.find('p', class_='app-name')
            title = title_elem.text.strip() if title_elem else app_name
            
            desc_elem = app_elem.find('p', class_='desc')
            description = desc_elem.text.strip() if desc_elem else "بدون وصف"
            
            link_elem = app_elem.find('a', class_='app-link')
            app_url = link_elem['href'] if link_elem else None
            
            version_elem = app_elem.find('span', class_='version')
            version = version_elem.text.strip() if version_elem else "N/A"
            
            rating_elem = app_elem.find('span', class_='rating')
            rating = rating_elem.text.strip() if rating_elem else "N/A"
            
            if not app_url:
                logger.warning(f"لم يتم الحصول على رابط {app_name}")
                return None
            
            # الحصول على رابط التحميل المباشر للـ APK
            apk_download_url = self.get_apk_download_link(app_url)
            
            if not apk_download_url:
                logger.warning(f"لم يتم الحصول على رابط APK المباشر لـ {app_name}")
                apk_download_url = app_url  # استخدم رابط الصفحة كبديل
            
            return {
                'title': title,
                'description': description[:200],  # أول 200 حرف
                'page_url': app_url,
                'apk_url': apk_download_url,
                'version': version,
                'rating': rating,
                'source': 'APKPure'
            }
            
        except requests.RequestException as e:
            logger.error(f"خطأ في الاتصال: {e}")
            return None
        except Exception as e:
            logger.error(f"خطأ في معالجة البيانات: {e}")
            return None
    
    def get_apk_download_link(self, app_page_url):
        """جلب رابط تحميل APK المباشر من صفحة التطبيق"""
        try:
            response = self.session.get(app_page_url, timeout=10)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # البحث عن زر التحميل
            download_btn = soup.find('a', {'class': 'download-btn'})
            if download_btn and download_btn.get('href'):
                return download_btn['href']
            
            # محاولة بديلة - البحث عن رابط بصيغة apk
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link['href']
                if 'apk' in href.lower() and 'download' in href.lower():
                    return href
            
            # إذا لم نجد رابط مباشر، نعيد رابط الصفحة
            return app_page_url
            
        except Exception as e:
            logger.warning(f"خطأ في جلب رابط التحميل المباشر: {e}")
            return app_page_url
    
    def format_message(self, app_info):
        """تنسيق الرسالة للإرسال مع رابط تحميل APK المباشر"""
        message = f"""
📱 <b>{app_info['title']}</b>

📝 <b>الوصف:</b>
{app_info['description']}

⭐ <b>التقييم:</b> {app_info['rating']}
📦 <b>الإصدار:</b> {app_info['version']}

🔗 <b>تحميل APK مباشر:</b>
<a href="{app_info['apk_url']}">⬇️ اضغط هنا للتحميل</a>

📄 <b>صفحة التطبيق:</b>
<a href="{app_info['page_url']}">عرض على APKpure</a>

📌 <b>المصدر:</b> APKPure
⏰ <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━
        """
        return message.strip()
    
    def send_to_channel(self, message):
        """إرسال الرسالة إلى القناة"""
        try:
            self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=False
            )
            logger.info(f"✅ تم الإرسال إلى القناة بنجاح")
            return True
        except TelegramError as e:
            logger.error(f"❌ خطأ في الإرسال: {e}")
            return False
    
    def run(self):
        """تشغيل البوت الرئيسي"""
        logger.info("🚀 بدء البوت...")
        
        try:
            # اختبار الاتصال
            bot_info = self.bot.get_me()
            logger.info(f"✅ تم الاتصال بنجاح: @{bot_info.username}")
        except TelegramError as e:
            logger.error(f"❌ فشل الاتصال بـ Telegram: {e}")
            return
        
        iteration = 0
        
        while True:
            try:
                iteration += 1
                logger.info(f"\n🔄 جولة #{iteration}")
                
                # اختيار تطبيق عشوائي لم يتم إرساله
                available_apps = [app for app in APPS_LIST if app not in self.sent_apps]
                
                if not available_apps:
                    logger.info("✨ تم إرسال جميع التطبيقات! إعادة تعيين القائمة...")
                    self.sent_apps.clear()
                    available_apps = APPS_LIST
                
                app_name = random.choice(available_apps)
                logger.info(f"📲 جلب معلومات: {app_name}")
                
                app_info = self.get_app_info(app_name)
                
                if app_info:
                    message = self.format_message(app_info)
                    if self.send_to_channel(message):
                        self.sent_apps.add(app_name)
                        logger.info(f"✅ تم إضافة {app_name} إلى قائمة المرسلة")
                else:
                    logger.warning(f"⚠️ فشل في جلب معلومات {app_name}")
                
                # الانتظار قبل الجولة التالية
                logger.info(f"⏳ الانتظار {INTERVAL} ثانية...")
                time.sleep(INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("\n🛑 تم إيقاف البوت بواسطة المستخدم")
                break
            except Exception as e:
                logger.error(f"❌ خطأ غير متوقع: {e}")
                logger.info(f"⏳ إعادة المحاولة بعد {INTERVAL} ثانية...")
                time.sleep(INTERVAL)

def main():
    """الدالة الرئيسية"""
    bot = APKPureBot(BOT_TOKEN, CHANNEL_ID)
    bot.run()

if __name__ == "__main__":
    main()
