import os
import logging
import re
import io
import base64
from typing import Dict, Optional
from dotenv import load_dotenv
import requests
import qrcode
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CUTTLY_API_KEY = os.getenv('CUTTLY_API_KEY')
CUTTLY_API_URL = "https://cutt.ly/api/api.php"

if not TOKEN:
    raise ValueError("Please set TELEGRAM_BOT_TOKEN environment variable")
if not CUTTLY_API_KEY:
    raise ValueError("Please set CUTTLY_API_KEY environment variable")

user_stats: Dict[int, Dict] = {}

def is_valid_url(url: str) -> bool:
    if not url:
        return False
    url_pattern = re.compile(
        r'^(https?://)'  # http:// or https://
        r'(([A-Za-z0-9-]+\.)+[A-Za-z]{2,})'  # domain
        r'(:\d+)?'  # optional port
        r'(/[^\s]*)?$',  # path
        re.IGNORECASE
    )
    return bool(url_pattern.match(url))

def shorten_url_with_cuttly(long_url: str, custom_alias: str = None) -> Dict:
    if not long_url:
        return {'success': False, 'error': 'No URL provided'}
    params = {
        'key': CUTTLY_API_KEY,
        'short': long_url,
    }    
    if custom_alias:
        params['name'] = custom_alias
    try:
        response = requests.get(CUTTLY_API_URL, params=params, timeout=10)
        if response.status_code != 200:
            return {'success': False, 'error': f'API Error: {response.status_code}'}
        data = response.json()
        if not data or 'url' not in data:
            return {'success': False, 'error': 'Invalid API response'}
        url_data = data.get('url', {})
        if not url_data:
            return {'success': False, 'error': 'No URL data in response'}
        status = url_data.get('status')
        if status == 7:
            short_link = url_data.get('shortLink')
            if not short_link:
                return {'success': False, 'error': 'No short link in response'}
            return {
                'success': True,
                'short_url': short_link,
                'short_id': short_link.split('/')[-1] if '/' in short_link else short_link,
                'full_data': url_data
            }
        elif status == 1:
            short_link = url_data.get('shortLink')
            if short_link:
                return {
                    'success': True,
                    'short_url': short_link,
                    'short_id': short_link.split('/')[-1] if '/' in short_link else short_link,
                    'message': 'URL already shortened',
                    'full_data': url_data
                }
            else:
                return {'success': False, 'error': 'URL exists but no short link'}
        else:
            error_codes = {
                2: 'Invalid URL',
                3: 'Invalid custom alias',
                4: 'Custom alias already taken',
                5: 'Invalid API key',
                6: 'Too many requests',
                8: 'URL blocked by Cuttly'
            }
            error_msg = error_codes.get(status, f'Unknown error (code: {status})')
            return {
                'success': False,
                'error': f"Cuttly Error: {error_msg}",
                'code': status
            }
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Request timeout. Please try again.'}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': 'Connection error. Check your internet.'}
    except Exception as e:
        logger.error(f"Cuttly API error: {e}")
        return {'success': False, 'error': f'Internal error: {str(e)[:100]}'}

def get_url_stats(short_url: str) -> Dict:
    if not short_url:
        return {'success': False, 'error': 'No URL provided'}
    short_id = short_url.split('/')[-1] if '/' in short_url else short_url
    if not short_id:
        return {'success': False, 'error': 'Invalid short URL'}
    params = {
        'key': CUTTLY_API_KEY,
        'stats': short_id
    }
    try:
        response = requests.get(CUTTLY_API_URL, params=params, timeout=10)
        if response.status_code != 200:
            return {'success': False, 'error': f'API Error: {response.status_code}'}
        data = response.json()
        if not data or 'stats' not in data:
            return {'success': False, 'error': 'Invalid API response'}
        stats_data = data.get('stats', {})
        if not stats_data:
            return {'success': False, 'error': 'No stats data in response'}
        status = stats_data.get('status')
        if status == 1:
            return {
                'success': True,
                'stats': {
                    'title': stats_data.get('title', 'No title'),
                    'short_url': f"https://cutt.ly/{short_id}",
                    'original_url': stats_data.get('fullLink', 'Unknown'),
                    'clicks': stats_data.get('clicks', 0),
                    'date': stats_data.get('date', 'Unknown'),
                    'facebook': stats_data.get('facebook', 0),
                    'twitter': stats_data.get('twitter', 0),
                    'instagram': stats_data.get('instagram', 0),
                    'pinterest': stats_data.get('pinterest', 0),
                }
            }
        else:
            error_codes = {
                1: 'Short URL not found',
                2: 'Invalid short URL',
                3: 'Short URL not owned by user',
                4: 'API key missing or invalid',
                5: 'Too many requests'
            }
            error_msg = error_codes.get(status, f'Unknown error (code: {status})')
            return {'success': False, 'error': f"Stats Error: {error_msg}"}
    except Exception as e:
        logger.error(f"Stats API error: {e}")
        return {'success': False, 'error': f'Failed to fetch stats: {str(e)[:100]}'}

def generate_qr_code(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img_byte_arr = BytesIO()
        img.save(img_byte_arr)
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        try:
            import urllib.parse
            encoded_url = urllib.parse.quote(url, safe='')
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}"
            response = requests.get(qr_url, timeout=10)
            if response.status_code == 200:
                return response.content
        except:
            pass
        return None

def format_stats_message(stats: Dict) -> str:
    if not stats:
        return "❌ No statistics available"
    return (
        f"📊 URL Statistics\n\n"
        f"📝 Title: {stats.get('title', 'No title')}\n"
        f"🔗 Short URL: {stats.get('short_url', 'Unknown')}\n"
        f"🌐 Original URL:\n{stats.get('original_url', 'Unknown')[:80]}...\n\n"
        f"👆 Direct Clicks: {stats.get('clicks', 0)}\n"
        f"📅 Created: {stats.get('date', 'Unknown')}\n\n"
        f"📱 Platform Breakdown:\n"
        f"• Facebook: {stats.get('facebook', 0)} clicks\n"
        f"• Twitter: {stats.get('twitter', 0)} clicks\n"
        f"• Instagram: {stats.get('instagram', 0)} clicks\n"
        f"• Pinterest: {stats.get('pinterest', 0)} clicks\n\n"
    )

def update_user_stats(user_id: int, url_count: int = 1):
    if user_id not in user_stats:
        user_stats[user_id] = {
            'urls_shortened': 0,
            'first_used': None,
            'last_used': None
        }
    import datetime
    now = datetime.datetime.now()
    user_stats[user_id]['urls_shortened'] += url_count
    user_stats[user_id]['last_used'] = now
    if not user_stats[user_id]['first_used']:
        user_stats[user_id]['first_used'] = now
# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_message = (
        f"👋 Hello {user.first_name}!\n\n"
        "🔗 <b>URL shortener bot</b>\n\n"
        "I can shorten your long URLs using Cuttly service.\n\n"
        "📝 <b>How to use:</b>\n"
        "1. Send me any long URL\n"
        "2. I'll shorten it instantly\n"
        "3. Get your short link with analytics\n\n"
        "✨ <b>New Features:</b>\n"
        "• View stats directly in bot\n"
        "• See QR code images in chat\n"
        "• Platform-wise analytics\n\n"
        "⚙️ <b>Commands:</b>\n"
        "/start - Show this message\n"
        "/help - Detailed help\n"
        "/mystats - Your statistics\n"
        "/stats - View URL stats\n"
        "/bulk - Shorten multiple URLs\n"
        "/custom - Set custom alias\n"
        "/qr - Generate QR code\n\n"
        "📎 <b>Just send me a URL to get started!</b>"
    )
    await update.message.reply_html(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 <b>Help Guide</b>\n\n"
        "<b>Basic usage:</b>\n"
        "Just send any URL starting with http:// or https://\n\n"
        "<b>Advanced Features:</b>\n"
        "1. <b>Custom Alias</b>: /custom alias <code>https://url.com</code>\n"
        "2. <b>QR Code</b>: /qr <code>https://url.com</code> (shows image!)\n"
        "3. <b>Bulk URLs</b>: /bulk then send URLs\n"
        "4. <b>User Stats</b>: /mystats to see your usage\n"
        "5. <b>URL Stats</b>: /stats <code>short-url</code> for analytics\n\n"
        "<b>Examples:</b>\n"
        "• <code>https://www.example.com/very-long-url-path</code>\n"
        "• /custom mysite <code>https://example.com</code>\n"
        "• /qr <code>https://example.com</code>\n"
        "• /stats <code>https://cutt.ly/abc123</code>\n\n"
        "<b>Limitations:</b>\n"
        "• Max URL length: 2048 characters\n"
        "• Must start with http:// or https://\n"
        "• Rate limit: 10 URLs/minute"
    )
    await update.message.reply_html(help_text)

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_stats:
        stats = user_stats[user_id]
        urls_count = stats.get('urls_shortened', 0)
        first_used = stats.get('first_used')
        last_used = stats.get('last_used')
        first_str = first_used.strftime('%Y-%m-%d %H:%M') if first_used else 'Never'
        last_str = last_used.strftime('%Y-%m-%d %H:%M') if last_used else 'Never'
        mystats_message = (
            f"📊 <b>Your Statistics</b>\n\n"
            f"👤 <b>User:</b> {update.effective_user.first_name}\n"
            f"🔗 <b>URLs Shortened:</b> {urls_count}\n"
            f"📅 <b>First Used:</b> {first_str}\n"
            f"⏰ <b>Last Used:</b> {last_str}\n\n"
            f"🎯 <b>Rank:</b> {'Beginner' if urls_count < 5 else 'Pro' if urls_count > 50 else 'Regular'}\n"
        )
    else:
        mystats_message = (
            f"📊 <b>Your Statistics</b>\n\n"
            f"👤 <b>User:</b> {update.effective_user.first_name}\n"
            f"🔗 <b>URLs Shortened:</b> 0\n"
            f"📅 <b>First Used:</b> Never\n"
            f"⏰ <b>Last Used:</b> Never\n\n"
            f"🎯 <b>Start by shortening your first URL!</b>"
        )
    await update.message.reply_html(mystats_message)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "📊 <b>URL Statistics</b>\n\n"
            "<b>Usage:</b> /stats <code>https://cutt.ly/your-short-url</code>\n\n"
            "<b>Example:</b>\n"
            "/stats <code>https://cutt.ly/abc123</code>\n\n"
            "<b>What you'll see:</b>\n"
            "• Total clicks\n"
            "• Platform breakdown\n"
            "• Creation date\n"
            "• Original URL\n\n"
            "Send /help for more information."
        )
        return
    short_url = ' '.join(context.args)
    if not short_url.startswith('https://cutt.ly/'):
        await update.message.reply_html(
            "❌ <b>Invalid Cuttly URL!</b>\n\n"
            "Please provide a valid Cuttly short URL.\n"
            "Example: <code>https://cutt.ly/abc123</code>"
        )
        return
    processing_msg = await update.message.reply_text("📊 Fetching statistics...")
    result = get_url_stats(short_url)
    if result.get('success'):
        stats = result.get('stats', {})
        stats_message = format_stats_message(stats)
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Stats", callback_data=f"refresh_stats_{short_url}")],
            [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(stats_message, reply_markup=reply_markup)
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_html(f"❌ <b>Failed to fetch statistics:</b>\n{error_msg}")

async def custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Usage:</b> /custom your-alias <code>https://example.com</code>\n\n"
            "<b>Example:</b>\n"
            "/custom mysite <code>https://www.mywebsite.com</code>\n\n"
            "<b>Rules for alias:</b>\n"
            "• 3-30 characters\n"
            "• Letters, numbers, hyphens only\n"
            "• Must be unique"
        )
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Please provide both alias and URL.\n"
            "Example: /custom mysite https://example.com"
        )
        return
    custom_alias = context.args[0]
    url = context.args[1]
    if not re.match(r'^[a-zA-Z0-9-]{3,30}$', custom_alias):
        await update.message.reply_html(
            "❌ <b>Invalid alias!</b>\n\n"
            "<b>Valid alias must:</b>\n"
            "• Be 3-30 characters\n"
            "• Contain only letters, numbers, hyphens\n"
            "• Start with letter or number\n"
            "• No spaces or special characters"
        )
        return
    if not is_valid_url(url):
        await update.message.reply_html(
            "❌ <b>Invalid URL!</b>\n\n"
            "Please send a valid URL starting with:\n"
            "• <code>http://</code> or <code>https://</code>\n"
            "• Example: <code>https://example.com</code>"
        )
        return
    processing_msg = await update.message.reply_text(f"⏳ Shortening with alias {custom_alias}...")
    result = shorten_url_with_cuttly(url, custom_alias)
    if result.get('success'):
        short_url = result.get('short_url', '')
        short_id = result.get('short_id', '')
        update_user_stats(update.effective_user.id)
        response_message = (
            f"✅ <b>URL Shortened Successfully!</b>\n\n"
            f"🌐 <b>Original URL:</b>\n<code>{url[:100]}...</code>\n\n"
            f"🔗 <b>Short URL:</b>\n<code>{short_url}</code>\n\n"
            f"🏷️ <b>Custom Alias:</b> <code>{custom_alias}</code>\n\n"
            f"📊 <b>Use</b> <code>/stats {short_url}</code> <b>to track clicks</b>\n\n"
            f"📋 <b>Copy:</b> <code>{short_url}</code>"
        )
        keyboard = [
            [InlineKeyboardButton("📋 Copy URL", callback_data=f"copy_{short_url}")],
            [InlineKeyboardButton("📊 View Stats", callback_data=f"stats_{short_url}")],
            [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(response_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_html(f"❌ <b>Failed to shorten URL:</b>\n{error_msg}")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Usage:</b> /qr <code>https://example.com</code>\n\n"
            "<b>Example:</b>\n"
            "/qr <code>https://www.mywebsite.com</code>\n\n"
            "I'll generate and send a QR code image for your URL!"
        )
        return
    url = ' '.join(context.args)
    if not url.startswith('https://cutt.ly/') and not is_valid_url(url):
        await update.message.reply_html(
            "❌ <b>Invalid URL!</b>\n\n"
            "Please send a valid URL starting with:\n"
            "• <code>http://</code> or <code>https://</code>\n"
            "• Example: <code>https://example.com</code>\n"
            "• Or a Cuttly short URL: <code>https://cutt.ly/abc123</code>"
        )
        return
    processing_msg = await update.message.reply_text("📱 Generating QR code...")
    qr_image = generate_qr_code(url)
    if qr_image:
        try:
            await processing_msg.delete()
            display_url = url[:60] + "..." if len(url) > 60 else url
            caption = (
                f"📱 <b>QR Code Generated</b>\n\n"
                f"🔗 <b>URL:</b> <code>{display_url}</code>\n\n"
            )
            await update.message.reply_photo(
                photo=qr_image,
                caption=caption,
                parse_mode='HTML'
            )
            logger.info(f"✅ QR code sent successfully for URL: {url[:50]}")
        except Exception as e:
            logger.error(f"Failed to send QR photo: {e}")
            await processing_msg.edit_text(
                f"❌ Failed to send QR code image:\n{str(e)[:100]}"
            )
    else:
        await processing_msg.edit_html(
            "❌ <b>Failed to generate QR code!</b>\n\n"
            "Please try again or use a different URL."
        )

async def bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bulk_text = (
        "📦 <b>Bulk URL Shortener\n\n</b>"
        "Send me multiple URLs (one per line):\n\n"
        "<b>Example:</b>"
        "<pre><code>https://example.com/page1\n"
        "https://example.com/page2\n"
        "https://example.com/page3</code></pre>\n\n"
        "I'll shorten all of them and send back the results!\n\n"
        "<b>Note:</b> Maximum 10 URLs at once."
    )
    await update.message.reply_text(bulk_text, parse_mode="HTML")
    context.user_data['expecting_bulk'] = True

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    if context.user_data.get('expecting_bulk'):
        context.user_data['expecting_bulk'] = False
        await handle_bulk_urls(update, text)
        return
    if not is_valid_url(text):
        await update.message.reply_html(
            "❌ <b>Invalid URL!</b>\n\n"
            "Please send a valid URL starting with:\n"
            "• <code>http://</code> or <code>https://</code>\n"
            "• Example: <code>https://example.com</code>\n\n"
            "Or use commands:\n"
            "• /custom alias url - Custom alias\n"
            "• /qr url - Generate QR code\n"
            "• /bulk - Multiple URLs\n"
            "• /stats url - View statistics"
        )
        return
    processing_msg = await update.message.reply_text("⏳ Shortening your URL...")
    result = shorten_url_with_cuttly(text)
    if result.get('success'):
        short_url = result.get('short_url', '')
        update_user_stats(user_id)
        response_message = (
            f"✅ <b>URL Shortened Successfully!</b>\n\n"
            f"🌐 <b>Original URL:</b>\n<code>{text[:100]}...</code>\n\n"
            f"🔗 <b>Short URL:</b>\n<code>{short_url}</code>\n\n"
            f"📊 <b>Use</b> /stats <code>{short_url}</code> <b>to track clicks</b>\n\n"
            f"💡 <b>Tip:</b> Use /custom for custom alias"
        )
        keyboard = [
            [InlineKeyboardButton("📊 View Stats", callback_data=f"stats_{short_url}")],
            [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(response_message, reply_markup=reply_markup, parse_mode="HTML")
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_html(f"❌ <b>Failed to shorten URL:</b>\n{error_msg}")

async def handle_bulk_urls(update: Update, text: str):
    urls = [line.strip() for line in text.split('\n') if line.strip()]
    if len(urls) > 10:
        await update.message.reply_text("❌ Maximum 10 URLs allowed. Please send fewer URLs.")
        return
    valid_urls = []
    invalid_urls = []
    for url in urls:
        if is_valid_url(url):
            valid_urls.append(url)
        else:
            invalid_urls.append(url)    
    if not valid_urls:
        await update.message.reply_text("❌ No valid URLs found. Please check your URLs and try again.")
        return
    processing_msg = await update.message.reply_text(f"⏳ Processing {len(valid_urls)} URLs...")
    results = []
    successful = 0
    failed = 0
    for url in valid_urls:
        result = shorten_url_with_cuttly(url)
        if result.get('success'):
            short_url = result.get('short_url', 'Unknown')
            results.append((url, short_url))
            successful += 1
        else:
            error_msg = result.get('error', 'Unknown error')
            results.append((url, f"❌ Error: {error_msg}"))
            failed += 1
    response_parts = []
    if successful > 0:
        response_parts.append(f"✅ <b>Successfully shortened</b> {successful} URLs:\n")
        for original, short_url in results:
            if not short_url.startswith('❌'):
                response_parts.append(f"• {short_url}")
    if failed > 0:
        response_parts.append(f"\n❌ <b>Failed to shorten</b> {failed} URLs:")
        for original, error in results:
            if error.startswith('❌'):
                response_parts.append(f"• {original[:50]}... → {error}")
    if invalid_urls:
        response_parts.append(f"\n⚠️ <b>Invalid URLs ({len(invalid_urls)}):</b>")
        for url in invalid_urls[:5]:
            response_parts.append(f"• {url[:50]}...")
        if len(invalid_urls) > 5:
            response_parts.append(f"• ... and {len(invalid_urls) - 5} more")
    update_user_stats(update.effective_user.id, successful)    
    response_message = "\n".join(response_parts)
    if len(response_message) > 4000:
        chunks = [response_message[i:i+4000] for i in range(0, len(response_message), 4000)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                await processing_msg.edit_text(chunk, parse_mode="HTML")
            else:
                await update.message.reply_text(chunk, parse_mode="HTML")
    else:
        await processing_msg.edit_text(response_message, parse_mode="HTML")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    try:
        if data.startswith('stats_'):
            short_url = data[6:]
            await query.edit_message_text("📊 Fetching statistics...")
            result = get_url_stats(short_url)
            if result.get('success'):
                stats = result.get('stats', {})
                stats_message = format_stats_message(stats)
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"stats_{short_url}")],
                    [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
                    [InlineKeyboardButton("🔗 Open URL", url=short_url)],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(stats_message, reply_markup=reply_markup)
            else:
                error_msg = result.get('error', 'Unknown error')
                await query.edit_message_text(f"❌ <b>Failed to fetch stats:</b>\n{error_msg}", parse_mode="HTML")
        elif data.startswith('qr_'):
            url = data[3:]
            await query.edit_message_text("📱 Generating QR code...")
            qr_image = generate_qr_code(url)
            if qr_image:
                display_url = url[:60] + "..." if len(url) > 60 else url
                caption = (
                    f"📱 <b>QR Code</b>\n\n"
                    f"🔗 <b>URL:</b> <code>{url[:80]}...</code>\n\n"
                    f"<b>Scan to open URL</b>"
                )
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=qr_image,
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_text("✅ <b>QR code generated successfully!</b>", parse_mode="HTML")
                logger.info(f"✅ QR code sent via button for: {url[:50]}")
            else:
                await query.edit_message_text(
                    "❌ <b>Failed to generate QR code!</b>\n\n"
                    "Please try again later.",
                    parse_mode="HTML"
                )
        elif data.startswith('refresh_stats_'):
            short_url = data[14:]
            await query.edit_message_text("🔄 Refreshing statistics...")
            result = get_url_stats(short_url)
            if result.get('success'):
                stats = result.get('stats', {})
                stats_message = format_stats_message(stats)
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_stats_{short_url}")],
                    [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
                    [InlineKeyboardButton("🔗 Open URL", url=short_url)],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(stats_message, reply_markup=reply_markup, parse_mode="HTML")
            else:
                error_msg = result.get('error', 'Unknown error')
                await query.edit_message_text(f"❌ <b>Failed to refresh stats:</b>\n{error_msg}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Button callback error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)[:100]}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again or contact support."
            )
    except:
        pass

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mystats", mystats_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("custom", custom_command))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("bulk", bulk_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)
    logger.info("🤖 URL Shortener Bot starting...")
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is alive!')
        def log_message(self, format, *args):
            pass
    def run_health_server():
        httpd = HTTPServer(('0.0.0.0', 10000), HealthHandler)
        logger.info(f"✅ Health server on port 10000")
        httpd.serve_forever()
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
       )
if __name__ == '__main__':
    main()