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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get tokens from environment
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CUTTLY_API_KEY = os.getenv('CUTTLY_API_KEY')

if not TOKEN:
    raise ValueError("Please set TELEGRAM_BOT_TOKEN environment variable")
if not CUTTLY_API_KEY:
    raise ValueError("Please set CUTTLY_API_KEY environment variable")

# Store user sessions for analytics (optional)
user_stats: Dict[int, Dict] = {}

# Cuttly API base URL
CUTTLY_API_URL = "https://cutt.ly/api/api.php"

def is_valid_url(url: str) -> bool:
    """Validate URL format"""
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
    """
    Shorten URL using Cuttly API
    Returns: {'success': bool, 'short_url': str, 'error': str, 'short_id': str}
    """
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
        
        if status == 7:  # Success
            short_link = url_data.get('shortLink')
            if not short_link:
                return {'success': False, 'error': 'No short link in response'}
            
            return {
                'success': True,
                'short_url': short_link,
                'short_id': short_link.split('/')[-1] if '/' in short_link else short_link,
                'full_data': url_data
            }
        elif status == 1:  # Already exists
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
            # Handle Cuttly error codes
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
    """
    Get statistics for a shortened URL
    API: https://cutt.ly/api/api.php?key=API_KEY&stats=SHORT_ID
    """
    if not short_url:
        return {'success': False, 'error': 'No URL provided'}
    
    # Extract short ID from URL
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
        
        if status == 1:  # Stats retrieved successfully
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
            # Handle stats errors
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
    """
    Generate QR code locally - NO EXTERNAL API NEEDED
    Returns: QR code image bytes
    """
    if not url:
        return None
    
    try:
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # Add URL to QR code
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create image with black foreground and white background
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        img_byte_arr = BytesIO()
        img.save(img_byte_arr)
        img_byte_arr.seek(0)
        
        return img_byte_arr.getvalue()
        
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        
        # Fallback to external API if local generation fails
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
    """Format stats data into a readable message"""
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
    """Update user statistics"""
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
    """Send welcome message when /start is issued"""
    user = update.effective_user
    
    welcome_message = (
        f"👋 Hello {user.first_name}!\n\n"
        "🔗 URL Shortener Bot\n\n"
        "I can shorten your long URLs using Cuttly service.\n\n"
        "📝 How to use:\n"
        "1. Send me any long URL\n"
        "2. I'll shorten it instantly\n"
        "3. Get your short link with analytics\n\n"
        "✨ New Features:\n"
        "• View stats directly in bot\n"
        "• See QR code images in chat\n"
        "• Platform-wise click analytics\n\n"
        "⚙️ Commands:\n"
        "/start - Show this message\n"
        "/help - Detailed help\n"
        "/mystats - Your statistics\n"
        "/stats - View URL stats\n"
        "/bulk - Shorten multiple URLs\n"
        "/custom - Set custom alias\n"
        "/qr - Generate QR code\n\n"
        "📎 Just send me a URL to get started!"
    )
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    help_text = (
        "📚 Help Guide\n\n"
        "Basic Usage:\n"
        "Just send any URL starting with http:// or https://\n\n"
        "Advanced Features:\n"
        "1. Custom Alias: /custom alias https://mylink.com\n"
        "2. QR Code: /qr https://mylink.com (shows image!)\n"
        "3. Bulk URLs: /bulk then send URLs\n"
        "4. User Stats: /mystats to see your usage\n"
        "5. URL Stats: /stats short-url for analytics\n\n"
        "Examples:\n"
        "• https://www.example.com/very-long-url-path\n"
        "• /custom mysite https://example.com\n"
        "• /qr https://example.com\n"
        "• /stats https://cutt.ly/abc123\n\n"
        "Limitations:\n"
        "• Max URL length: 2048 characters\n"
        "• Must start with http:// or https://\n"
        "• Rate limit: 10 URLs/minute"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    user_id = update.effective_user.id
    
    if user_id in user_stats:
        stats = user_stats[user_id]
        urls_count = stats.get('urls_shortened', 0)
        first_used = stats.get('first_used')
        last_used = stats.get('last_used')
        
        first_str = first_used.strftime('%Y-%m-%d %H:%M') if first_used else 'Never'
        last_str = last_used.strftime('%Y-%m-%d %H:%M') if last_used else 'Never'
        
        mystats_message = (
            f"📊 Your Statistics\n\n"
            f"👤 User: {update.effective_user.first_name}\n"
            f"🔗 URLs Shortened: {urls_count}\n"
            f"📅 First Used: {first_str}\n"
            f"⏰ Last Used: {last_str}\n\n"
            f"🎯 Rank: {'Beginner' if urls_count < 5 else 'Pro' if urls_count > 50 else 'Regular'}\n"
        )
    else:
        mystats_message = (
            f"📊 Your Statistics\n\n"
            f"👤 User: {update.effective_user.first_name}\n"
            f"🔗 URLs Shortened: 0\n"
            f"📅 First Used: Never\n"
            f"⏰ Last Used: Never\n\n"
            f"🎯 Start by shortening your first URL!"
        )
    
    await update.message.reply_text(mystats_message, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get statistics for a shortened URL"""
    if not context.args:
        await update.message.reply_text(
            "📊 URL Statistics\n\n"
            "Usage: /stats https://cutt.ly/your-short-url\n\n"
            "Example:\n"
            "/stats https://cutt.ly/abc123\n\n"
            "What you'll see:\n"
            "• Total clicks\n"
            "• Platform breakdown\n"
            "• Creation date\n"
            "• Original URL\n\n"
            "Send /help for more information."
        )
        return
    
    short_url = ' '.join(context.args)
    
    # Validate it's a Cuttly URL
    if not short_url.startswith('https://cutt.ly/'):
        await update.message.reply_text(
            "❌ Invalid Cuttly URL!\n\n"
            "Please provide a valid Cuttly short URL.\n"
            "Example: https://cutt.ly/abc123"
        )
        return
    
    processing_msg = await update.message.reply_text("📊 Fetching statistics...")
    
    # Get statistics
    result = get_url_stats(short_url)
    
    if result.get('success'):
        stats = result.get('stats', {})
        stats_message = format_stats_message(stats)
        
        # Create keyboard with actions
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Stats", callback_data=f"refresh_stats_{short_url}")],
            [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(stats_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_text(f"❌ Failed to fetch statistics:\n{error_msg}")

async def custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom alias command"""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /custom your-alias https://example.com\n\n"
            "Example:\n"
            "/custom mysite https://www.mylink.com\n\n"
            "Rules for alias:\n"
            "• 3-30 characters\n"
            "• Letters, numbers, hyphens only\n"
            "• Must be unique"
        )
        return
    
    # Check if enough arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Please provide both alias and URL.\n"
            "Example: /custom mysite https://example.com"
        )
        return
    
    custom_alias = context.args[0]
    url = context.args[1]
    
    # Validate alias
    if not re.match(r'^[a-zA-Z0-9-]{3,30}$', custom_alias):
        await update.message.reply_text(
            "❌ Invalid alias!\n\n"
            "Valid alias must:\n"
            "• Be 3-30 characters\n"
            "• Contain only letters, numbers, hyphens\n"
            "• Start with letter or number\n"
            "• No spaces or special characters"
        )
        return
    
    # Validate URL
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ Invalid URL!\n\n"
            "Please send a valid URL starting with:\n"
            "• http:// or https://\n"
            "• Example: https://example.com"
        )
        return
    
    # Process URL shortening
    processing_msg = await update.message.reply_text(f"⏳ Shortening with alias {custom_alias}...")
    
    result = shorten_url_with_cuttly(url, custom_alias)
    
    if result.get('success'):
        short_url = result.get('short_url', '')
        short_id = result.get('short_id', '')
        update_user_stats(update.effective_user.id)
        
        response_message = (
            f"✅ URL Shortened Successfully!\n\n"
            f"🌐 Original URL:\n{url[:100]}...\n\n"
            f"🔗 Short URL:\n{short_url}\n\n"
            f"🏷️ Custom Alias: {custom_alias}\n\n"
            f"📊 Use /stats {short_url} to track clicks\n\n"
            f"📋 Copy: {short_url}"
        )
        
        # Create keyboard with actions
        keyboard = [
            [InlineKeyboardButton("📋 Copy URL", callback_data=f"copy_{short_url}")],
            [InlineKeyboardButton("📊 View Stats", callback_data=f"stats_{short_url}")],
            [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(response_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_text(f"❌ Failed to shorten URL:\n{error_msg}")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate QR code for URL and send as image"""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /qr https://example.com\n\n"
            "Example:\n"
            "/qr https://www.mylink.com\n\n"
            "I'll generate and send a QR code image for your URL!"
        )
        return
    
    url = ' '.join(context.args)
    
    # Validate URL
    if not url.startswith('https://cutt.ly/') and not is_valid_url(url):
        await update.message.reply_text(
            "❌ Invalid URL!\n\n"
            "Please send a valid URL starting with:\n"
            "• http:// or https://\n"
            "• Example: https://example.com\n"
            "• Or a Cuttly short URL: https://cutt.ly/abc123"
        )
        return
    
    processing_msg = await update.message.reply_text("📱 Generating QR code...")
    
    # Generate QR code LOCALLY
    qr_image = generate_qr_code(url)
    
    if qr_image:
        try:
            # Send QR code as photo
            await processing_msg.delete()
            
            # Truncate URL for caption
            display_url = url[:60] + "..." if len(url) > 60 else url
            
            caption = (
                f"📱 QR Code Generated\n\n"
                f"🔗 URL: {display_url}\n\n"
                f"To use:\n"
                f"1. Scan with phone camera\n"
                f"2. Save the image\n"
                f"3. Share with others\n\n"
                f"✅ Generated locally - No external API used"
            )
            
            # Send the image
            await update.message.reply_photo(
                photo=qr_image,
                caption=caption,
                parse_mode='Markdown'
            )
            logger.info(f"✅ QR code sent successfully for URL: {url[:50]}")
            
        except Exception as e:
            logger.error(f"Failed to send QR photo: {e}")
            await processing_msg.edit_text(
                f"❌ Failed to send QR code image:\n{str(e)[:100]}"
            )
    else:
        await processing_msg.edit_text(
            "❌ Failed to generate QR code!\n\n"
            "Please try again with a different URL."
        )

async def bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk URL shortening"""
    await update.message.reply_text(
        "📦 Bulk URL Shortener\n\n"
        "Send me multiple URLs (one per line):\n\n"
        "Example:\n"
        "\n"
        "https://example.com/page1\n"
        "https://example.com/page2\n"
        "https://example.com/page3\n"
        "\n\n"
        "I'll shorten all of them and send back the results!\n\n"
        "Note: Maximum 10 URLs at once."
    )
    
    # Store that we're expecting bulk URLs
    context.user_data['expecting_bulk'] = True

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle URL messages from users"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Check if we're expecting bulk URLs
    if context.user_data.get('expecting_bulk'):
        context.user_data['expecting_bulk'] = False
        await handle_bulk_urls(update, text)
        return
    
    # Validate URL
    if not is_valid_url(text):
        await update.message.reply_text(
            "❌ Invalid URL!\n\n"
            "Please send a valid URL starting with:\n"
            "• http:// or https://\n"
            "• Example: https://example.com\n\n"
            "Or use commands:\n"
            "• /custom alias url - Custom alias\n"
            "• /qr url - Generate QR code\n"
            "• /bulk - Multiple URLs\n"
            "• /stats url - View statistics"
        )
        return
    
    # Show processing message
    processing_msg = await update.message.reply_text("⏳ Shortening your URL...")
    
    # Shorten URL
    result = shorten_url_with_cuttly(text)
    
    if result.get('success'):
        short_url = result.get('short_url', '')
        update_user_stats(user_id)
        
        response_message = (
            f"✅ URL Shortened Successfully!\n\n"
            f"🌐 Original URL:\n{text[:100]}...\n\n"
            f"🔗 Short URL:\n{short_url}\n\n"
            f"💡 Tip: Use /custom for custom alias"
        )
        
        # Create keyboard with actions
        keyboard = [
            [InlineKeyboardButton("📊 View Stats", callback_data=f"stats_{short_url}")],
            [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(response_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_text(f"❌ Failed to shorten URL:\n{error_msg}")

async def handle_bulk_urls(update: Update, text: str):
    """Handle bulk URL shortening"""
    urls = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Limit to 10 URLs
    if len(urls) > 10:
        await update.message.reply_text("❌ Maximum 10 URLs allowed. Please send fewer URLs.")
        return
    
    # Validate URLs
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
    
    # Process bulk shortening
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
    
    # Prepare response
    response_parts = []
    
    if successful > 0:
        response_parts.append(f"✅ Successfully shortened {successful} URLs:\n")
        for original, short_url in results:
            if not short_url.startswith('❌'):
                response_parts.append(f"• {short_url}")
    
    if failed > 0:
        response_parts.append(f"\n❌ Failed to shorten {failed} URLs:")
        for original, error in results:
            if error.startswith('❌'):
                response_parts.append(f"• {original[:50]}... → {error}")
    
    if invalid_urls:
        response_parts.append(f"\n⚠️ Invalid URLs ({len(invalid_urls)}):")
        for url in invalid_urls[:5]:  # Show first 5
            response_parts.append(f"• {url[:50]}...")
        if len(invalid_urls) > 5:
            response_parts.append(f"• ... and {len(invalid_urls) - 5} more")
    
    # Update user stats
    update_user_stats(update.effective_user.id, successful)
    
    response_message = "\n".join(response_parts)
    
    # Split if message is too long
    if len(response_message) > 4000:
        chunks = [response_message[i:i+4000] for i in range(0, len(response_message), 4000)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                await processing_msg.edit_text(chunk, parse_mode='Markdown')
            else:
                await update.message.reply_text(chunk, parse_mode='Markdown')
    else:
        await processing_msg.edit_text(response_message, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        if data.startswith('stats_'):
            # Show statistics for URL
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
                
                await query.edit_message_text(stats_message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                error_msg = result.get('error', 'Unknown error')
                await query.edit_message_text(f"❌ Failed to fetch stats:\n{error_msg}")
        
        elif data.startswith('qr_'):
            # Generate and send QR code
            url = data[3:]
            await query.edit_message_text("📱 Generating QR code...")
            
            qr_image = generate_qr_code(url)
            
            if qr_image:
                # Truncate URL for caption
                display_url = url[:60] + "..." if len(url) > 60 else url
                
                caption = (
                    f"📱 QR Code\n\n"
                    f"🔗 URL: {display_url}\n\n"
                    f"Scan to open URL"
                )
                
                # Send QR code as photo
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=qr_image,
                    caption=caption,
                    parse_mode='Markdown'
                )
                
                # Edit original message to show success
                await query.edit_message_text(
                    f"✅ QR code generated successfully!"
                )
                logger.info(f"✅ QR code sent via button for: {url[:50]}")
            else:
                await query.edit_message_text(
                    "❌ Failed to generate QR code!\n\n"
                    "Please try again later."
                )
        
        elif data.startswith('refresh_stats_'):
            # Refresh statistics
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
                
                await query.edit_message_text(stats_message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                error_msg = result.get('error', 'Unknown error')
                await query.edit_message_text(f"❌ Failed to refresh stats:\n{error_msg}")
    
    except Exception as e:
        logger.error(f"Button callback error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)[:100]}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    # Send user-friendly error message
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again or contact support."
            )
    except:
        pass

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mystats", mystats_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("custom", custom_command))
    application.add_handler(CommandHandler("qr", qr_command))
    application.add_handler(CommandHandler("bulk", bulk_command))
    
    # Add message handler for URLs
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("🤖 URL Shortener Bot starting...")
    
    class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is alive!')
    
    def log_message(self, format, *args):
        pass  # Silence logs

    def run_health_server():
        port = int(os.environ.get("PORT", 8080))
        httpd = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✅ Health server on port {port}")
        httpd.serve_forever()
    
    # Start health server
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
       )

if __name__ == '__main__':
    main()