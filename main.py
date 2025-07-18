import os
import re
import requests
from bs4 import BeautifulSoup
import tweepy
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes
from notion_client import Client as NotionClient
from github import Github
import json
import time

# API Keys
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TWITTER_BEARER = os.getenv("TWITTER_BEARER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Initialize clients
twitter_client = tweepy.Client(bearer_token=TWITTER_BEARER) if TWITTER_BEARER else None
github_client = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None
notion_client = NotionClient(auth=NOTION_API_KEY) if NOTION_API_KEY else None

def get_website_info(url: str) -> str:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        r = requests.get(url, timeout=15, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Получаем title
        title = "Неизвестный сайт"
        if soup.title:
            title = soup.title.string.strip()
        elif soup.find('h1'):
            title = soup.find('h1').get_text().strip()
        
        # Ищем социальные ссылки более агрессивно
        social_links = []
        
        # Поиск в различных элементах
        selectors = [
            'a[href*="twitter.com"]', 'a[href*="x.com"]',
            'a[href*="github.com"]', 'a[href*="discord.gg"]',
            'a[href*="discord.com/invite"]', 'a[href*="t.me"]',
            'a[href*="medium.com"]', 'a[href*="telegram"]'
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href and href.startswith('http'):
                    if 'twitter.com' in href or 'x.com' in href:
                        social_links.append(f"🐦 Twitter: {href}")
                    elif 'github.com' in href:
                        social_links.append(f"🐙 GitHub: {href}")
                    elif 'discord' in href:
                        social_links.append(f"🔔 Discord: {href}")
                    elif 't.me' in href or 'telegram' in href:
                        social_links.append(f"📱 Telegram: {href}")
                    elif 'medium.com' in href:
                        social_links.append(f"📝 Medium: {href}")
        
        # Также ищем в тексте страницы
        text_content = soup.get_text()
        
        # Поиск Twitter handles в тексте
        twitter_handles = re.findall(r'@[A-Za-z0-9_]{1,15}', text_content)
        for handle in twitter_handles[:3]:  # Берем первые 3
            social_links.append(f"🐦 Twitter: https://twitter.com/{handle[1:]}")
        
        # Поиск GitHub репозиториев
        github_repos = re.findall(r'github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', text_content)
        for repo in github_repos[:2]:  # Берем первые 2
            social_links.append(f"🐙 GitHub: https://{repo}")
        
        # Убираем дубликаты
        unique_social = list(dict.fromkeys(social_links))
        
        result = f"🌐 Сайт: {title[:100]}"
        if unique_social:
            result += "\n" + "\n".join(unique_social[:8])  # Максимум 8 ссылок
        else:
            result += "\n❌ Социальные ссылки не найдены"
        
        return result
        
    except Exception as e:
        return f"🌐 Сайт: Ошибка загрузки - {str(e)[:100]}"

def get_tokenomics(symbol: str) -> str:
    if not symbol:
        return "🔢 Токеномика: символ не найден"
    
    result = []
    
    # CoinGecko API - пробуем разные способы поиска
    try:
        # Сначала пытаемся найти по символу
        search_url = f"https://api.coingecko.com/api/v3/search?query={symbol}"
        search_resp = requests.get(search_url, timeout=10)
        
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            coins = search_data.get('coins', [])
            
            if coins:
                coin_id = coins[0]['id']
                
                # Получаем данные о токене
                price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true"
                price_resp = requests.get(price_url, timeout=10)
                
                if price_resp.status_code == 200:
                    price_data = price_resp.json()
                    
                    if coin_id in price_data:
                        data = price_data[coin_id]
                        price = data.get('usd', 0)
                        mcap = data.get('usd_market_cap', 0)
                        vol = data.get('usd_24h_vol', 0)
                        change = data.get('usd_24h_change', 0)
                        
                        result.append(f"💰 Токен: {coins[0]['name']} (${coins[0]['symbol'].upper()})")
                        result.append(f"💲 Цена: ${price:.6f}")
                        result.append(f"📊 Market Cap: ${mcap:,.0f}")
                        result.append(f"📈 Volume 24h: ${vol:,.0f}")
                        result.append(f"📉 Change 24h: {change:.2f}%")
    except Exception as e:
        result.append(f"💰 CoinGecko: ошибка - {str(e)[:50]}")
    
    return "\n".join(result) if result else "🔢 Токеномика: данные не найдены"

def get_twitter_stats(handle: str) -> str:
    if not twitter_client:
        return "🐦 Twitter: API не настроен (нужен TWITTER_BEARER_TOKEN)"
    
    try:
        handle = handle.replace('@', '').replace('https://twitter.com/', '').replace('https://x.com/', '')
        user = twitter_client.get_user(username=handle, user_fields=['public_metrics', 'created_at'])
        
        if user.data:
            metrics = user.data.public_metrics
            followers = metrics['followers_count']
            following = metrics['following_count']
            tweets = metrics['tweet_count']
            likes = metrics['like_count']
            
            # Получаем последние твиты
            tweets_data = twitter_client.get_users_tweets(user.data.id, max_results=5)
            recent_activity = "Нет недавних твитов"
            
            if tweets_data.data:
                recent_tweets = len(tweets_data.data)
                recent_activity = f"Последние {recent_tweets} твитов найдены"
            
            return f"🐦 @{handle}:\n👥 {followers:,} подписчиков\n📝 {tweets:,} твитов\n❤️ {likes:,} лайков\n🔄 {recent_activity}"
        
        return f"🐦 @{handle}: пользователь не найден"
    except Exception as e:
        return f"🐦 Twitter: ошибка - {str(e)[:100]}"

def get_github_info(repo_url: str) -> str:
    if not github_client:
        return "🐙 GitHub: API не настроен (нужен GITHUB_TOKEN)"
    
    try:
        # Извлекаем owner/repo из URL
        match = re.search(r'github\.com/([^/]+/[^/\s]+)', repo_url)
        if not match:
            return "🐙 GitHub: неверный URL"
        
        repo_path = match.group(1).rstrip('/')
        repo = github_client.get_repo(repo_path)
        
        # Получаем статистику
        stars = repo.stargazers_count
        forks = repo.forks_count
        issues = repo.open_issues_count
        
        # Получаем последние коммиты
        commits = list(repo.get_commits()[:3])
        commit_info = []
        
        for commit in commits:
            msg = commit.commit.message.split('\n')[0][:60]
            date = commit.commit.author.date.strftime('%d.%m')
            commit_info.append(f"• {date}: {msg}")
        
        # Получаем языки программирования
        languages = repo.get_languages()
        top_lang = max(languages.keys(), key=lambda x: languages[x]) if languages else "Unknown"
        
        return f"🐙 {repo.name}:\n⭐ {stars:,} звезд, 🍴 {forks:,} форков\n🐛 {issues} открытых issues\n💻 Язык: {top_lang}\n📝 Последние коммиты:\n" + "\n".join(commit_info)
        
    except Exception as e:
        return f"🐙 GitHub: ошибка - {str(e)[:100]}"

def analyze_discord(invite_url: str) -> str:
    try:
        # Извлекаем код приглашения
        invite_code = invite_url.split('/')[-1].split('?')[0]
        
        # Используем публичный API Discord
        api_url = f"https://discord.com/api/v10/invites/{invite_code}?with_counts=true"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            guild = data.get('guild', {})
            guild_name = guild.get('name', 'Unknown Server')
            members = data.get('approximate_member_count', 0)
            online = data.get('approximate_presence_count', 0)
            
            # Дополнительная информация
            description = guild.get('description', 'Нет описания')
            features = guild.get('features', [])
            
            result = f"🔔 {guild_name}:\n👥 ~{members:,} участников\n🟢 ~{online:,} онлайн"
            
            if description and description != 'Нет описания':
                result += f"\n📝 {description[:100]}"
            
            if features:
                result += f"\n✨ Особенности: {', '.join(features[:3])}"
            
            return result
        else:
            return f"🔔 Discord: сервер недоступен (код: {response.status_code})"
    except Exception as e:
        return f"🔔 Discord: ошибка - {str(e)[:100]}"

def get_manual_analysis(data: str) -> str:
    """Улучшенный анализ без AI"""
    analysis = []
    score = 0
    
    data_lower = data.lower()
    
    # Анализ социальных сетей
    if "twitter" in data_lower:
        if "подписчиков" in data_lower:
            follower_match = re.search(r'(\d+[,\d]*)\s+подписчиков', data_lower)
            if follower_match:
                followers = int(follower_match.group(1).replace(',', ''))
                if followers > 100000:
                    analysis.append("✅ Сильное сообщество в Twitter")
                    score += 2
                elif followers > 10000:
                    analysis.append("🟡 Среднее сообщество в Twitter")
                    score += 1
                else:
                    analysis.append("🔴 Малое сообщество в Twitter")
        else:
            analysis.append("🔍 Twitter найден, но данные недоступны")
    
    # Анализ GitHub
    if "github" in data_lower:
        if "звезд" in data_lower or "⭐" in data:
            star_match = re.search(r'⭐\s*(\d+[,\d]*)', data)
            if star_match:
                stars = int(star_match.group(1).replace(',', ''))
                if stars > 1000:
                    analysis.append("✅ Популярный GitHub проект")
                    score += 2
                elif stars > 100:
                    analysis.append("🟡 Средняя популярность GitHub")
                    score += 1
                else:
                    analysis.append("🔴 Малая популярность GitHub")
        else:
            analysis.append("🔍 GitHub найден, но статистика недоступна")
    
    # Анализ Discord
    if "discord" in data_lower:
        if "участников" in data_lower:
            member_match = re.search(r'(\d+[,\d]*)\s+участников', data_lower)
            if member_match:
                members = int(member_match.group(1).replace(',', ''))
                if members > 50000:
                    analysis.append("✅ Большое Discord сообщество")
                    score += 2
                elif members > 10000:
                    analysis.append("🟡 Среднее Discord сообщество")
                    score += 1
                else:
                    analysis.append("🔴 Малое Discord сообщество")
        else:
            analysis.append("🔍 Discord найден, но данные недоступны")
    
    # Анализ токеномики
    if "market cap" in data_lower or "цена" in data_lower:
        analysis.append("✅ Токен торгуется на рынке")
        score += 1
    elif "данные не найдены" in data_lower:
        analysis.append("🎯 Возможный airdrop (токен не найден)")
    
    # Анализ активности разработки
    if "последние коммиты" in data_lower:
        analysis.append("✅ Активная разработка")
        score += 1
    
    # Финальная оценка
    if score >= 5:
        verdict = "🚀 Очень высокий потенциал"
    elif score >= 3:
        verdict = "🟢 Высокий потенциал"
    elif score >= 2:
        verdict = "🟡 Средний потенциал"
    elif score >= 1:
        verdict = "🔴 Низкий потенциал"
    else:
        verdict = "❌ Недостаточно данных"
    
    if len(analysis) == 0:
        return "🤖 Анализ: Социальные ссылки не найдены. Возможно, это новый проект или сайт блокирует парсинг."
    
    return f"🤖 Анализ: {verdict}\n📊 Факторы:\n" + "\n".join(f"   {factor}" for factor in analysis)

def research_project(url: str) -> str:
    results = []
    
    # Базовый анализ сайта
    website_info = get_website_info(url)
    results.append(website_info)
    
    # Если нашли социальные ссылки, анализируем их
    if "🐦 Twitter:" in website_info:
        twitter_links = re.findall(r'🐦 Twitter: (https?://[^\s]+)', website_info)
        for twitter_link in twitter_links[:1]:  # Берем первую ссылку
            handle = twitter_link.split('/')[-1]
            results.append(get_twitter_stats(handle))
            # Пытаемся найти токен по handle
            results.append(get_tokenomics(handle))
    
    # Анализ GitHub
    if "🐙 GitHub:" in website_info:
        github_links = re.findall(r'🐙 GitHub: (https?://[^\s]+)', website_info)
        for github_link in github_links[:1]:  # Берем первую ссылку
            results.append(get_github_info(github_link))
    
    # Анализ Discord
    if "🔔 Discord:" in website_info:
        discord_links = re.findall(r'🔔 Discord: (https?://[^\s]+)', website_info)
        for discord_link in discord_links[:1]:  # Берем первую ссылку
            results.append(analyze_discord(discord_link))
    
    # Собираем все данные
    summary = "\n\n".join(filter(None, results))
    
    # Добавляем анализ
    analysis = get_manual_analysis(summary)
    summary += f"\n\n{analysis}"
    
    return summary

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Crypto Research Bot v2.0 активен!\n\n"
        "Отправьте ссылку на проект и получите анализ:\n"
        "• 🌐 Сайт и социальные ссылки\n"
        "• 🐦 Twitter статистика\n"
        "• 🔢 Токеномика (CoinGecko)\n"
        "• 🐙 GitHub активность\n"
        "• 🔔 Discord сообщество\n"
        "• 🤖 Анализ потенциала\n\n"
        "⚙️ Для полного функционала настройте API ключи:\n"
        "• TWITTER_BEARER_TOKEN\n"
        "• GITHUB_TOKEN"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    urls = re.findall(r'https?://[^\s]+', text)
    
    if not urls:
        await update.message.reply_text("🔍 Отправьте ссылку на проект для анализа")
        return
    
    await update.message.reply_text("🔄 Анализирую проект... Это может занять до 30 секунд.")
    
    for url in urls[:1]:  # Анализируем только первую ссылку
        try:
            result = research_project(url)
            
            # Разбиваем длинные сообщения
            if len(result) > 4000:
                parts = [result[i:i+3800] for i in range(0, len(result), 3800)]
                for i, part in enumerate(parts):
                    if i > 0:
                        await update.message.reply_text(f"Часть {i+1}:")
                    await update.message.reply_text(part)
            else:
                await update.message.reply_text(result)
                
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка анализа: {str(e)[:200]}")

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не найден в переменных окружения")
        return
    
    # Проверяем наличие API ключей
    if not TWITTER_BEARER:
        print("⚠️ TWITTER_BEARER_TOKEN не найден - Twitter анализ недоступен")
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN не найден - GitHub анализ недоступен")
    
    # Telegram бот
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Crypto Research Bot запущен...")
    print("📡 Парсинг сайтов работает без API ключей")
    print("🔧 Для полного функционала добавьте TWITTER_BEARER_TOKEN и GITHUB_TOKEN")
    
    app.run_polling()

if __name__ == '__main__':
    main()
