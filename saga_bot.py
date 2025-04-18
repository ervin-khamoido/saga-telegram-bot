import os
import asyncio
import logging
import time
from pathlib import Path
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.error import TelegramError

# --- Логування ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Змінено на DEBUG для виводу деталей
)
logger = logging.getLogger(__name__)

# --- Змінні середовища ---
load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))
SAGA_URL = os.getenv('SAGA_URL')

# --- Шляхи ---
BASE_DIR = Path(__file__).parent
KNOWN_OFFERS_PATH = BASE_DIR / 'known_offers.txt'

# --- Ініціалізація асинхронного бота ---
bot = Bot(token=BOT_TOKEN)


def load_known_offers():
    if not KNOWN_OFFERS_PATH.exists():
        return set()
    with open(KNOWN_OFFERS_PATH, 'r') as f:
        return set(line.strip() for line in f if line.strip())


def save_known_offers(offers):
    with open(KNOWN_OFFERS_PATH, 'w') as f:
        for offer_id in sorted(offers):
            f.write(f"{offer_id}\n")


def fetch_offers():
    """Отримує короткий список оголошень (IDs + URLs) зі сторінки пошуку."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(SAGA_URL, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    offers = {}
    for a in soup.select('a[href*="/immobiliensuche/immo-detail/"]'):
        href = a['href']
        offer_id = href.strip('/').split('/')[-2]
        url = f"https://www.saga.hamburg{href}"
        offers[offer_id] = url
    return offers


def parse_offer_details(url):
    """Повертає словник з усіма деталями оголошення зі сторінки детального перегляду."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    data = {}

    # Заголовок
    h1 = soup.select_one('h1')
    data['Title'] = h1.get_text(strip=True) if h1 else 'N/A'

    # 1) DT/DD пари у списках опису
    for dl in soup.select('dl'):
        dts = dl.select('dt')
        dds = dl.select('dd')
        for dt, dd in zip(dts, dds):
            key = dt.get_text(strip=True).rstrip(':')
            val = dd.get_text(strip=True)
            data[key] = val

    # 2) Табличні дані у таблицях
    for tr in soup.select('table tr'):
        # випадок <th> / <td>
        th = tr.select_one('th')
        td = tr.select_one('td')
        if th and td:
            key = th.get_text(strip=True).rstrip(':')
            val = td.get_text(strip=True)
            data[key] = val
            continue
        # випадок дві <td>
        tds = tr.select('td')
        if len(tds) == 2:
            key = tds[0].get_text(strip=True).rstrip(':')
            val = tds[1].get_text(strip=True)
            data[key] = val
            continue

    # 3) Keyfacts list
    for item in soup.select('.keyfacts-list li'):
        text = item.get_text(strip=True)
        if ':' in text:
            k, v = text.split(':', 1)
            data[k.strip()] = v.strip()

    # 4) Опис оголошення
    desc = soup.select_one('#text-description') or soup.select_one('.description')
    if desc:
        data['Description'] = desc.get_text(strip=True)

    # 5) Додаткові секції (заголовки h2)
    for h2 in soup.select('h2'):
        section = h2.get_text(strip=True)
        content = []
        for sib in h2.find_next_siblings():
            if sib.name == 'h2':
                break
            if sib.name in ['p', 'li']:
                text = sib.get_text(strip=True)
                if text:
                    content.append(text)
        if content:
            data[section] = ' '.join(content)

    # 6) Усі параграфи у головному блоці
    main_block = soup.select_one('article') or soup.select_one('div.body-text') or soup.select_one('main')
    if main_block:
        for idx, p in enumerate(main_block.select('p'), 1):
            text = p.get_text(strip=True)
            if text:
                data[f'Paragraph {idx}'] = text

    return data


async def notify_new_offers(new_offers):
    emoji_map = {
        'Objektnummer': '🆔',
        'Netto-Kaltmiete': '💵',
        'Betriebskosten': '💡',
        'Heizkosten': '🔥',
        'Gesamtmiete': '💰',
        'Wohnfläche ca.': '📐',
        'Zimmer': '🛏️',
        'Etage': '🏢',
        'Verfügbar ab': '📅',
    }
    for offer_id, url in new_offers.items():
        try:
            details = parse_offer_details(url)
            lines = []

            title = details.get('Title', 'N/A')
            lines.append(f"🏠 *{title}*\n")

            for key in ['Objektnummer', 'Netto-Kaltmiete', 'Betriebskosten', 'Heizkosten', 'Gesamtmiete', 'Wohnfläche ca.', 'Zimmer', 'Etage', 'Verfügbar ab']:
                value = details.get(key)
                if value:
                    value = ' '.join(value.split())
                    emoji = emoji_map.get(key, '')
                    lines.append(f"{emoji} *{key}:* {value}")

            desc = details.get('Description')
            if desc:
                desc = ' '.join(desc.split())
                lines.append(f"📝 {desc}")

            lines.append(f"🔗 {url}")
            message = "\n".join(lines)

            await bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            logger.info(f"Sent offer {offer_id}")
        except Exception as e:
            logger.error(f"Error notifying {offer_id}: {e}")


async def main():
    logger.info('Starting SAGA Hamburg monitor...')
    seen = load_known_offers()
    logger.info(f'Loaded {len(seen)} known offers.')

    if KNOWN_OFFERS_PATH.exists():
        max_age_days = 7
        age = time.time() - KNOWN_OFFERS_PATH.stat().st_mtime
        if age > max_age_days * 86400:
            logger.info("Cache too old, clearing known_offers.txt")
            KNOWN_OFFERS_PATH.unlink()

    while True:
        try:
            offers = fetch_offers()
            logger.info(f"Found {len(offers)} offers on search page.")
            new = {oid: url for oid, url in offers.items() if oid not in seen}
            if new:
                logger.info(f"New offers: {list(new.keys())}")
                await notify_new_offers(new)
                seen.update(new)
                save_known_offers(seen)
            else:
                logger.info('No new offers.')
        except Exception as e:
            logger.exception(f"Monitoring error: {e}")
        await asyncio.sleep(INTERVAL)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot stopped manually.')