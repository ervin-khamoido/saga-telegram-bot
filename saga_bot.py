import os
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.error import TelegramError

# --- Налаштування логування ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Завантаження змінних середовища з .env ---
load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))
SAGA_URL = os.getenv('SAGA_URL')

# --- Шлях до файлу зі збереженими ID оголошень ---
BASE_DIR = Path(__file__).parent
KNOWN_OFFERS_PATH = BASE_DIR / 'known_offers.txt'

# --- Ініціалізація Telegram-бота ---
bot = Bot(token=BOT_TOKEN)

# --- Зчитує раніше оброблені ID оголошень з файлу ---
def load_known_offers():
    if not KNOWN_OFFERS_PATH.exists():
        return set()
    with open(KNOWN_OFFERS_PATH, 'r') as f:
        return set(line.strip() for line in f if line.strip())


# --- Зберігає оновлений список ID оголошень у файл ---
def save_known_offers(offers):
    with open(KNOWN_OFFERS_PATH, 'w') as f:
        for offer_id in sorted(offers):
            f.write(f"{offer_id}\n")


# --- Отримує список поточних оголошень із сайту SAGA ---
def fetch_offers():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    response = requests.get(SAGA_URL, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    offers = {}
    # Знаходимо всі посилання на деталі оголошень
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/immobiliensuche/immo-detail/' in href:
            # Витягуємо ID оголошення
            parts = href.strip('/').split('/')
            # передостанній елемент містить ID, наприклад '4981'
            offer_id = parts[-2]
            full_url = f"https://www.saga.hamburg{href}"
            # Текст заголовку оголошення (можна налаштувати CSS селектор для точнішого парсингу)
            title = a.get_text(strip=True)
            offers[offer_id] = {
                'url': full_url,
                'title': title or 'Нове оголошення'
            }
    return offers


# --- Відправляє повідомлення в Telegram для кожного нового оголошення ---
def notify_new_offers(new_offers):
    for offer_id, data in new_offers.items():
        text = f"🏠 *{data['title']}*\n{data['url']}"
        try:
            bot.send_message(
                chat_id=CHAT_ID,
                text=text,
                parse_mode='Markdown'
            )
            logger.info(f"Sent: {offer_id} | {data['url']}")
        except TelegramError as e:
            logger.error(f"Failed to send {offer_id}: {e}")


# --- Основна функція для запуску моніторування ---
def main():
    logger.info('Starting SAGA Hamburg monitor...')
    seen = load_known_offers()
    logger.info(f'Loaded {len(seen)} known offers.')

    while True:
        try:
            offers = fetch_offers()
            # Фільтруємо нові оголошення
            new_offers = {oid: info for oid, info in offers.items() if oid not in seen}
            if new_offers:
                notify_new_offers(new_offers)
                seen.update(new_offers)
                save_known_offers(seen)
            else:
                logger.info('No new offers found.')
        except Exception as e:
            logger.exception(f"Error during monitoring: {e}")
        # Очікуємо перед наступною перевіркою
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()