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

# API Keys
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TWITTER_BEARER = os.getenv("TWITTER_BEARER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Initialize clients
openai.api_key = OPENAI_API_KEY
twitter_client = tweepy.Client(bearer_token=TWITTER_BEARER) if TWITTER_BEARER else None
github_client = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None
notion_client = NotionClient(auth=NOTION_API_KEY) if NOTION_API_KEY else None

def get_website_info(url: str) -> str:
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string.strip() if soup.title else url
        
        # Extract social links
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        social = []
        for link in set(links):
            if not link:
                continue
            if 'twitter.com' in link or 'x.com' in link:
                social.append(f"🐦 {link}")
            elif 'github.com' in link:
                social.append(f"🐙 {link}")
            elif 'discord.gg' in link or 'discord.com/invite' in link:
                social.append(f"🔗 {link}")
        
        return f"🌐 Сайт: {title}\n" + "\n".join(social[:5])
    except Exception as e:
        return f"🌐 Сайт: Ошибка загрузки - {str(e)[:50]}"

def get_tokenomics(symbol: str) -> str:
    if not symbol:
        return "🔢 Токеномика: символ не найден"
    
    result = []
    
    # CoinGecko API (free)
    try:
        cg_url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
        cg_resp = requests.get(cg_url, timeout=10).json()
        if cg_resp:
            data = list(cg_resp.values())[0]
            price = data.get('usd', 0)
            mcap = data.get('usd_market_cap', 0)
            vol = data.get('usd_24h_vol', 0)
            result.append(f"💰 Цена: ${price:.6f}")
            result.append(f"📊 Market Cap: ${mcap:,.0f}")
            result.append(f"📈 Volume 24h: ${vol:,.0f}")
    except:
        result.append("💰 CoinGecko: данные недоступны")
    
    # DeFiLlama
    try:
        llama_url = "https://api.llama.fi/protocols"
        llama_resp = requests.get(llama_url, timeout=10).json()
        matches = [p for p in llama_resp if p.get('symbol', '').lower() == symbol.lower()]
        if matches:
            tvl = matches[0].get('tvl', 0)
            result.append(f"🔐 TVL: ${tvl:,.0f}")
    except:
        result.append("🔐 DeFiLlama: недоступно")
    
    return "\n".join(result) if result else "🔢 Токеномика: данные не найдены"

def get_twitter_stats(handle: str) -> str:
    if not twitter_client:
        return "🐦 Twitter: API не настроен"
    
    try:
        handle = handle.replace('@', '')
        user = twitter_client.get_user(username=handle, user_fields=['public_metrics'])
        if user.data:
            metrics = user.data.public_metrics
            followers = metrics['followers_count']
            following = metrics['following_count']
            tweets = metrics['tweet_count']
            return f"🐦 @{handle}: {followers:,} подписчиков, {tweets:,} твитов"
        return f"🐦 @{handle}: пользователь не найден"
    except Exception as e:
        return f"🐦 Twitter: ошибка - {str(e)[:50]}"

def get_github_info(repo_url: str) -> str:
    if not github_client:
        return "🐙 GitHub: API не настроен"
    
    try:
        match = re.search(r'github\.com/([^/]+/[^/]+)', repo_url)
        if not match:
            return "🐙 GitHub: неверный URL"
        
        repo = github_client.get_repo(match.group(1))
        commits = list(repo.get_commits()[:3])
        stars = repo.stargazers_count
        forks = repo.forks_count
        
        commit_msgs = [c.commit.message.split('\n')[0][:50] for c in commits]
        
        return f"🐙 {repo.name}: ⭐{stars} 🍴{forks}\n📝 Коммиты: {'; '.join(commit_msgs)}"
    except Exception as e:
        return f"🐙 GitHub: ошибка - {str(e)[:50]}"

def analyze_discord(invite_url: str) -> str:
    try:
        # Простой парсинг через веб-запрос
        invite_code = invite_url.split('/')[-1]
        api_url = f"https://discord.com/api/v9/invites/{invite_code}?with_counts=true"
        
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            guild_name = data.get('guild', {}).get('name', 'Unknown')
            members = data.get('approximate_member_count', 0)
            online = data.get('approximate_presence_count', 0)
            
            return f"🔔 {guild_name}: ~{members:,} участников, ~{online:,} онлайн"
        else:
            return "🔔 Discord: сервер недоступен"
    except Exception as e:
        return f"🔔 Discord: ошибка - {str(e)[:50]}"

def get_manual_analysis(data: str) -> str:
    """Простой анализ без AI"""
    analysis = []
    
    # Анализ по ключевым словам
    data_lower = data.lower()
    
    # Социальные сигналы
    if "подписчиков" in data_lower:
        follower_match = re.search(r'(\d+[,\d]*)\s+подписчиков', data_lower)
        if follower_match:
            followers = int(follower_match.group(1).replace(',', ''))
            if followers > 100000:
                analysis.append("✅ Сильное сообщество")
            elif followers > 10000:
                analysis.append("🟡 Среднее сообщество")
            else:
                analysis.append("🔴 Малое сообщество")
    
    # Токеномика
    if "market cap" in data_lower:
        analysis.append("✅ Токен в обороте")
    elif "данные не найдены" in data_lower:
        analysis.append("🎯 Возможный airdrop (нет токена)")
    
    # GitHub активность
    if "github" in data_lower and "⭐" in data:
        star_match = re.search(r'⭐(\d+)', data)
        if star_match:
            stars = int(star_match.group(1))
            if stars > 1000:
                analysis.append("✅ Активная разработка")
            elif stars > 100:
                analysis.append("🟡 Умеренная разработка")
    
    # Discord активность
    if "участников" in data_lower:
        member_match = re.search(r'(\d+[,\d]*)\s+участников', data_lower)
        if member_match:
            members = int(member_match.group(1).replace(',', ''))
            if members > 50000:
                analysis.append("✅ Большое сообщество")
            elif members > 10000:
                analysis.append("🟡 Среднее сообщество")
    
    # Общий вывод
    if len(analysis) == 0:
        return "🤖 Анализ: Недостаточно данных для оценки"
    
    score = len([a for a in analysis if a.startswith("✅")])
    
    if score >= 3:
        verdict = "🚀 Высокий потенциал"
    elif score >= 2:
        verdict = "🟡 Средний потенциал"
    else:
        verdict = "⚠️ Низкий потенциал"
    
    return f"🤖 Анализ: {verdict}\n📊 Факторы: {' | '.join(analysis)}"

def research_project(url: str) -> str:
    results = []
    
    # Базовый анализ сайта
    results.append(get_website_info(url))
    
    # Извлечение Twitter handle
    twitter_handle = None
    twitter_match = re.search(r'(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)', url)
    if twitter_match:
        twitter_handle = twitter_match.group(1)
        results.append(get_twitter_stats(twitter_handle))
    
    # Токеномика (используем Twitter handle как символ)
    if twitter_handle:
        results.append(get_tokenomics(twitter_handle))
    
    # GitHub анализ
    github_match = re.search(r'github\.com/[^\s]+', url)
    if github_match:
        results.append(get_github_info(github_match.group(0)))
    
    # Discord анализ
    discord_match = re.search(r'discord\.gg/[A-Za-z0-9]+', url)
    if discord_match:
        discord_result = analyze_discord(discord_match.group(0))
        results.append(discord_result)
    
    # Собираем все данные
    summary = "\n\n".join(filter(None, results))
    
    # Добавляем собственный анализ
    analysis = get_manual_analysis(summary)
    summary += f"\n\n{analysis}"
    
    return summary

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Crypto Research Bot активен!\n\n"
        "Отправьте ссылку на проект и получите полный анализ:\n"
        "• Сайт и соцсети\n"
        "• Twitter статистика\n"
        "• Токеномика\n"
        "• GitHub активность\n"
        "• Discord сообщество\n"
        "• AI анализ потенциала"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    urls = re.findall(r'https?://[^\s]+', text)
    
    if not urls:
        await update.message.reply_text("🔍 Отправьте ссылку на проект для анализа")
        return
    
    await update.message.reply_text("🔄 Анализирую проект...")
    
    for url in urls[:2]:  # Максимум 2 ссылки
        try:
            result = research_project(url)
            # Разбиваем длинные сообщения
            if len(result) > 4000:
                parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
                for part in parts:
                    await update.message.reply_text(part)
            else:
                await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка анализа: {str(e)[:100]}")

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не найден")
        return
    
    # Telegram бот
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
