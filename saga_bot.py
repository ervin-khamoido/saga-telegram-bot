import os
import re
import time
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load environment variables ---
load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
SAGA_URL = os.getenv('SAGA_URL')
INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))

# --- File paths ---
BASE_DIR = Path(__file__).parent
KNOWN_OFFERS_PATH = BASE_DIR / 'known_offers.txt'
SUBSCRIBERS_PATH = BASE_DIR / 'subscribers.txt'

# --- Telegram Bot ---
bot = Bot(token=BOT_TOKEN)

# --- Cache Management ---
def load_known_offers():
    if not KNOWN_OFFERS_PATH.exists():
        return set()
    with open(KNOWN_OFFERS_PATH, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def save_known_offers(offers):
    with open(KNOWN_OFFERS_PATH, 'w') as f:
        for offer_id in sorted(offers):
            f.write(f"{offer_id}\n")

# --- Subscription ---
def load_subscribers():
    if not SUBSCRIBERS_PATH.exists():
        return set()
    with open(SUBSCRIBERS_PATH, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def save_subscribers(subscribers):
    with open(SUBSCRIBERS_PATH, 'w') as f:
        for chat_id in sorted(subscribers):
            f.write(f"{chat_id}\n")

# --- Parsing ---
def fetch_offers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(SAGA_URL, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    offers = {}
    for listing in soup.select('a[href*="/immobiliensuche/immo-detail/"]'):
        href = listing['href']
        parts = href.strip('/').split('/')
        offer_id = parts[-2]
        full_url = f"https://www.saga.hamburg{href}"
        title = listing.get_text(strip=True) or 'Neue Anzeige'
        offers[offer_id] = {
            'url': full_url,
            'title': title,
        }
    return offers

def parse_offer_details(offer):
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(offer['url'], headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    data = {}

    for dl in soup.find_all('dl'):
        for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
            k = dt.get_text(strip=True)
            v = dd.get_text(strip=True)
            if v:
                data[k] = v

    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cols = row.find_all(['th', 'td'])
            if len(cols) == 2:
                k = cols[0].get_text(strip=True)
                v = cols[1].get_text(strip=True)
                if v:
                    data[k] = v

    desc = soup.select_one('#text-description, .description')
    if desc:
        text = desc.get_text(separator=' ', strip=True)
        if text:
            data['Beschreibung'] = text

    return data

# --- Format message ---
def build_message(data, details):
    title = data.get('title', 'Neue Anzeige')
    url = data.get('url')
    offer_id = url.split('/')[-2]
    immomio_link = f"https://tenant.immomio.com/de/apply/{offer_id}"

    def line(emoji, label, value, suffix=''):
        value = value.replace("€", "").replace("m²", "").strip()
        return f"{emoji} *{label}:* {value}{suffix}".strip()

    # Energy class colors
    energy_emoji = {
        "A+": "🟢", "A": "🟢", "B": "🟢",
        "C": "🟡", "D": "🟡",
        "E": "🟠", "F": "🔴", "G": "🔴"
    }
    energy_class = details.get("Energieeffizienzklasse", "").strip()
    energy_icon = energy_emoji.get(energy_class.upper(), "⚡️")

    lines = [f"🏠 *{title}*"]

    if details.get("Objektnummer"):
        lines.append(line("🆔", "Objektnummer", details["Objektnummer"]))
    if details.get("Netto-Kaltmiete"):
        lines.append(line("💵", "Kaltmiete", details["Netto-Kaltmiete"], " €"))
    if details.get("Betriebskosten"):
        lines.append(line("💡", "Betriebskosten", details["Betriebskosten"], " €"))
    if details.get("Heizkosten"):
        lines.append(line("🔥", "Heizkosten", details["Heizkosten"], " €"))
    if details.get("Gesamtmiete"):
        lines.append(line("💰", "Gesamtmiete", details["Gesamtmiete"], " €"))
    if details.get("Wohnfläche ca."):
        lines.append(line("📐", "Wohnfläche", details["Wohnfläche ca."], " m²"))
    if details.get("Zimmer"):
        lines.append(line("🛏️", "Zimmer", details["Zimmer"]))
    if details.get("Etage"):
        lines.append(line("🏢", "Etage", details["Etage"]))
    if details.get("Verfügbar ab"):
        lines.append(line("📅", "Verfügbar ab", details["Verfügbar ab"]))
    if energy_class:
        lines.append(f"{energy_icon} *Energieklasse:* {energy_class}")

    lines.append("")
    lines.append(f"🔗 [Anzeigen-Link]({url})")
    lines.append(f"📬 [Jetzt bewerben]({immomio_link})")

    return '\n'.join(lines)

# --- Notifier ---
async def notify_new_offers(new_offers):
    subscribers = load_subscribers()
    if not subscribers:
        logger.info("No subscribers to notify.")
        return

    for offer_id, offer in new_offers.items():
        try:
            details = parse_offer_details(offer)
            msg = build_message(offer, details)
            for chat_id in subscribers:
                try:
                    await bot.send_message(
                        chat_id=int(chat_id),
                        text=msg,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.error(f"Failed to send to {chat_id}: {e}")
            logger.info(f"Sent offer {offer_id}")
        except Exception as e:
            logger.error(f"Error parsing {offer_id}: {e}")

# --- Background task ---
async def check_and_notify_loop():
    if KNOWN_OFFERS_PATH.exists():
        age = time.time() - KNOWN_OFFERS_PATH.stat().st_mtime
        if age > 7 * 86400:
            KNOWN_OFFERS_PATH.unlink()
            logger.info("Cache too old — cleared known_offers.txt")

    seen = load_known_offers()
    logger.info(f"Loaded {len(seen)} known offers.")

    while True:
        try:
            offers = fetch_offers()
            logger.info(f"Found {len(offers)} offers on search page.")
            new = {oid: offer for oid, offer in offers.items() if oid not in seen}
            if new:
                logger.info(f"New offers: {list(new.keys())}")
                await notify_new_offers(new)
                seen.update(new)
                save_known_offers(seen)
            else:
                logger.info("No new offers.")
        except Exception as e:
            logger.exception(f"Error during monitoring: {e}")
        await asyncio.sleep(INTERVAL)

# --- Command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    subscribers = load_subscribers()

    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        logger.info(f"New subscriber added: {chat_id}")
        await update.message.reply_text("✅ You are now subscribed to apartment updates.")
    else:
        await update.message.reply_text("ℹ️ You are already subscribed.")

    # Send current offers
    offers = fetch_offers()
    logger.info(f"Sending {len(offers)} current offers to chat {chat_id}")

    if not offers:
        await update.message.reply_text("🔍 No current listings found.")
        return

    for offer_id, offer_data in offers.items():
        details = parse_offer_details(offer_data)
        message = build_message(offer_data, details)
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

# --- Entry point ---
def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    async def startup(app: Application):
        asyncio.create_task(check_and_notify_loop())

    application.post_init = startup
    application.run_polling()

if __name__ == '__main__':
    run_bot()
