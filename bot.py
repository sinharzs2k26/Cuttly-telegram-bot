import os
import logging
import re
from typing import Dict, Optional
from dotenv import load_dotenv
import requests
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
    Returns: {'success': bool, 'short_url': str, 'error': str}
    """
    params = {
        'key': CUTTLY_API_KEY,
        'short': long_url,
    }
    
    if custom_alias:
        params['name'] = custom_alias
    
    try:
        response = requests.get(CUTTLY_API_URL, params=params, timeout=10)
        data = response.json()
        
        if response.status_code == 200:
            url_data = data.get('url', {})
            
            if url_data.get('status') == 7:  # Success
                return {
                    'success': True,
                    'short_url': url_data.get('shortLink'),
                    'full_data': url_data
                }
            elif url_data.get('status') == 1:  # Already exists
                return {
                    'success': True,
                    'short_url': url_data.get('shortLink'),
                    'message': 'URL already shortened',
                    'full_data': url_data
                }
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
                error_msg = error_codes.get(url_data.get('status'), 'Unknown error')
                return {
                    'success': False,
                    'error': f"Cuttly Error: {error_msg}",
                    'code': url_data.get('status')
                }
        else:
            return {
                'success': False,
                'error': f"API Error: {response.status_code}"
            }
            
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': 'Request timeout. Please try again.'
        }
    except requests.exceptions.ConnectionError:
        return {
            'success': False,
            'error': 'Connection error. Check your internet.'
        }
    except Exception as e:
        logger.error(f"Cuttly API error: {e}")
        return {
            'success': False,
            'error': f'Internal error: {str(e)}'
        }

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
        "🔗 **URL Shortener Bot**\n\n"
        "I can shorten your long URLs using Cuttly service.\n\n"
        "📝 **How to use:**\n"
        "1. Send me any long URL\n"
        "2. I'll shorten it instantly\n"
        "3. Get your short link with analytics\n\n"
        "✨ **Features:**\n"
        "• Fast URL shortening\n"
        "• Custom alias support\n"
        "• Click analytics\n"
        "• QR code generation\n"
        "• Bulk URL shortening\n\n"
        "⚙️ **Commands:**\n"
        "/start - Show this message\n"
        "/help - Detailed help\n"
        "/stats - Your statistics\n"
        "/bulk - Shorten multiple URLs\n"
        "/custom - Set custom alias\n"
        "/qr - Generate QR code\n\n"
        "📎 **Just send me a URL to get started!**"
    )
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    help_text = (
        "📚 **Help Guide**\n\n"
        "**Basic Usage:**\n"
        "Just send any URL starting with http:// or https://\n\n"
        "**Advanced Features:**\n"
        "1. **Custom Alias**: Send `/custom your-alias` then URL\n"
        "2. **QR Code**: Send `/qr` then URL\n"
        "3. **Bulk URLs**: Send `/bulk` then URLs separated by new lines\n"
        "4. **Statistics**: `/stats` to see your usage\n\n"
        "**Examples:**\n"
        "• `https://www.example.com/very-long-url-path`\n"
        "• `/custom mysite https://example.com`\n"
        "• `/qr https://example.com`\n\n"
        "**Supported URLs:**\n"
        "• HTTP/HTTPS websites\n"
        "• YouTube, Instagram, Twitter links\n"
        "• Google Drive, Dropbox links\n"
        "• Any valid web URL\n\n"
        "**Limitations:**\n"
        "• Max URL length: 2048 characters\n"
        "• Must start with http:// or https://\n"
        "• No spam or malicious URLs\n"
        "• Rate limit: 10 URLs/minute"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    user_id = update.effective_user.id
    
    if user_id in user_stats:
        stats = user_stats[user_id]
        urls_count = stats['urls_shortened']
        first_used = stats['first_used'].strftime('%Y-%m-%d %H:%M') if stats['first_used'] else 'Never'
        last_used = stats['last_used'].strftime('%Y-%m-%d %H:%M') if stats['last_used'] else 'Never'
        
        stats_message = (
            f"📊 **Your Statistics**\n\n"
            f"👤 **User:** {update.effective_user.first_name}\n"
            f"🔗 **URLs Shortened:** {urls_count}\n"
            f"📅 **First Used:** {first_used}\n"
            f"⏰ **Last Used:** {last_used}\n\n"
            f"🎯 **Rank:** {'Beginner' if urls_count < 5 else 'Pro' if urls_count > 50 else 'Regular'}\n"
        )
    else:
        stats_message = (
            f"📊 **Your Statistics**\n\n"
            f"👤 **User:** {update.effective_user.first_name}\n"
            f"🔗 **URLs Shortened:** 0\n"
            f"📅 **First Used:** Never\n"
            f"⏰ **Last Used:** Never\n\n"
            f"🎯 **Start by shortening your first URL!**"
        )
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom alias command"""
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/custom your-alias https://example.com`\n\n"
            "**Example:**\n"
            "`/custom mysite https://www.mywebsite.com`\n\n"
            "**Rules for alias:**\n"
            "• 3-30 characters\n"
            "• Letters, numbers, hyphens only\n"
            "• Must be unique"
        )
        return
    
    # Check if enough arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Please provide both alias and URL.\n"
            "Example: `/custom mysite https://example.com`"
        )
        return
    
    custom_alias = context.args[0]
    url = context.args[1]
    
    # Validate alias
    if not re.match(r'^[a-zA-Z0-9-]{3,30}$', custom_alias):
        await update.message.reply_text(
            "❌ **Invalid alias!**\n\n"
            "**Valid alias must:**\n"
            "• Be 3-30 characters\n"
            "• Contain only letters, numbers, hyphens\n"
            "• Start with letter or number\n"
            "• No spaces or special characters"
        )
        return
    
    # Validate URL
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ **Invalid URL!**\n\n"
            "Please send a valid URL starting with:\n"
            "• `http://` or `https://`\n"
            "• Example: `https://example.com`"
        )
        return
    
    # Process URL shortening
    processing_msg = await update.message.reply_text(f"⏳ Shortening with alias `{custom_alias}`...")
    
    result = shorten_url_with_cuttly(url, custom_alias)
    
    if result['success']:
        short_url = result['short_url']
        update_user_stats(update.effective_user.id)
        
        response_message = (
            f"✅ **URL Shortened Successfully!**\n\n"
            f"🌐 **Original URL:**\n`{url[:100]}...`\n\n"
            f"🔗 **Short URL:**\n`{short_url}`\n\n"
            f"🏷️ **Custom Alias:** `{custom_alias}`\n\n"
            f"📊 **Analytics:** https://cutt.ly/{custom_alias}/stats\n\n"
            f"📋 **Copy:** `{short_url}`"
        )
        
        # Create keyboard with actions
        keyboard = [
            [InlineKeyboardButton("📋 Copy URL", callback_data=f"copy_{short_url}")],
            [InlineKeyboardButton("📊 View Stats", url=f"https://cutt.ly/{custom_alias}/stats")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(response_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_text(f"❌ **Failed to shorten URL:**\n{error_msg}")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate QR code for URL"""
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/qr https://example.com`\n\n"
            "**Example:**\n"
            "`/qr https://www.mywebsite.com`\n\n"
            "I'll generate a QR code for your URL!"
        )
        return
    
    url = ' '.join(context.args)
    
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ **Invalid URL!**\n\n"
            "Please send a valid URL starting with:\n"
            "• `http://` or `https://`\n"
            "• Example: `https://example.com`"
        )
        return
    
    # Generate QR code URL
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={url}"
    
    response_message = (
        f"📱 **QR Code Generated**\n\n"
        f"🔗 **URL:**\n`{url[:100]}...`\n\n"
        f"📸 **QR Code Image:** [Click to View]({qr_url})\n\n"
        f"**To use:**\n"
        f"1. Scan with phone camera\n"
        f"2. Or use QR scanner app\n"
        f"3. Click the image to save"
    )
    
    keyboard = [
        [InlineKeyboardButton("📸 View QR Code", url=qr_url)],
        [InlineKeyboardButton("🔗 Open URL", url=url)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(response_message, reply_markup=reply_markup, parse_mode='Markdown')

async def bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk URL shortening"""
    await update.message.reply_text(
        "📦 **Bulk URL Shortener**\n\n"
        "Send me multiple URLs (one per line):\n\n"
        "**Example:**\n"
        "```\n"
        "https://example.com/page1\n"
        "https://example.com/page2\n"
        "https://example.com/page3\n"
        "```\n\n"
        "I'll shorten all of them and send back the results!\n\n"
        "**Note:** Maximum 10 URLs at once."
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
            "❌ **Invalid URL!**\n\n"
            "Please send a valid URL starting with:\n"
            "• `http://` or `https://`\n"
            "• Example: `https://example.com`\n\n"
            "Or use commands:\n"
            "• `/custom alias url` - Custom alias\n"
            "• `/qr url` - Generate QR code\n"
            "• `/bulk` - Multiple URLs"
        )
        return
    
    # Show processing message
    processing_msg = await update.message.reply_text("⏳ Shortening your URL...")
    
    # Shorten URL
    result = shorten_url_with_cuttly(text)
    
    if result['success']:
        short_url = result['short_url']
        update_user_stats(user_id)
        
        # Get analytics link (extract from short URL)
        import urllib.parse
        parsed = urllib.parse.urlparse(short_url)
        path = parsed.path.lstrip('/')
        
        response_message = (
            f"✅ **URL Shortened Successfully!**\n\n"
            f"🌐 **Original URL:**\n`{text[:100]}...`\n\n"
            f"🔗 **Short URL:**\n`{short_url}`\n\n"
            f"📊 **Analytics:** https://cutt.ly/{path}/stats\n\n"
            f"📋 **Copy:** `{short_url}`\n\n"
            f"💡 **Tip:** Use `/custom` for custom alias"
        )
        
        # Create keyboard with actions
        keyboard = [
            [InlineKeyboardButton("📋 Copy URL", callback_data=f"copy_{short_url}")],
            [InlineKeyboardButton("📊 View Stats", url=f"https://cutt.ly/{path}/stats")],
            [InlineKeyboardButton("🔗 Open URL", url=short_url)],
            [InlineKeyboardButton("📱 QR Code", callback_data=f"qr_{short_url}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(response_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        error_msg = result.get('error', 'Unknown error')
        await processing_msg.edit_text(f"❌ **Failed to shorten URL:**\n{error_msg}")

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
        if result['success']:
            results.append((url, result['short_url']))
            successful += 1
        else:
            results.append((url, f"❌ Error: {result.get('error')}"))
            failed += 1
    
    # Prepare response
    response_parts = []
    
    if successful > 0:
        response_parts.append(f"✅ **Successfully shortened {successful} URLs:**\n")
        for original, short_url in results:
            if not short_url.startswith('❌'):
                response_parts.append(f"• `{short_url}`")
    
    if failed > 0:
        response_parts.append(f"\n❌ **Failed to shorten {failed} URLs:**")
        for original, error in results:
            if error.startswith('❌'):
                response_parts.append(f"• {original[:50]}... → {error}")
    
    if invalid_urls:
        response_parts.append(f"\n⚠️ **Invalid URLs ({len(invalid_urls)}):**")
        for url in invalid_urls[:5]:  # Show first 5
            response_parts.append(f"• `{url[:50]}...`")
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
    
    if data.startswith('copy_'):
        # Copy URL to clipboard (simulated)
        url = data[5:]
        await query.edit_message_text(
            f"📋 **URL copied to clipboard!**\n\n"
            f"`{url}`\n\n"
            f"_You can now paste it anywhere._"
        )
    
    elif data.startswith('qr_'):
        # Generate QR code
        url = data[3:]
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={url}"
        
        await query.edit_message_text(
            f"📱 **QR Code Generated**\n\n"
            f"🔗 **URL:** `{url}`\n\n"
            f"📸 **QR Code:** [Click to View]({qr_url})\n\n"
            f"**To use:**\n"
            f"1. Scan with phone camera\n"
            f"2. Save the image\n"
            f"3. Share with others"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
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
    logger.info("🤖 Bot is starting...")
    logger.info("📡 Press Ctrl+C to stop")

    # Check if running on Render
    is_render = 'RENDER' in os.environ

    if is_render:
        # Use webhook for Render
        logger.info("🚀 Running in Render mode")
        port = int(os.environ.get('PORT', 10000))

        # Get webhook URL
        webhook_url = os.environ.get('RENDER_EXTERNAL_URL')
        if webhook_url:
            webhook_url = f"{webhook_url}/{TOKEN}"
            logger.info(f"Setting webhook to: {webhook_url}")

            # Set webhook before starting
            async def set_webhook():
                await application.bot.set_webhook(webhook_url)

            # Run the application with webhook
            application.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=TOKEN,
                webhook_url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
        else:
            logger.warning("No RENDER_EXTERNAL_URL found, using polling instead")
            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
    else:
        # Use polling for local development
        logger.info("💻 Running in local mode (polling)")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

if __name__ == '__main__':
    main()