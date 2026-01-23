# Cuttly URL Shortener Telegram Bot

A Telegram bot that shortens long URLs using Cuttly API.

## Features
- 🔗 Shorten any valid URL
- 🏷️ Custom alias support
- 📊 Click analytics
- 📱 QR code generation
- 📦 Bulk URL shortening
- 📊 User statistics
- 🆓 Free hosting on Render.com

## Setup

### 1. Get API Keys
1. **Telegram Bot Token**: From @BotFather
2. **Cuttly API Key**: From [cutt.ly](https://cutt.ly)

### 2. Local Development
```bash
git clone https://github.com/sinharzs2k26/Cuttly-telegram-bot.git
cd Cuttly-telegram-bot

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your tokens

# Run bot
python bot.py