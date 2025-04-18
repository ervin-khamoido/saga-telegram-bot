Ось англійська версія `README.md` для твого Telegram-бота:

---

### 📄 `README.md`

```markdown
# 🏠 SAGA Hamburg Telegram Bot

A Telegram bot that automatically monitors new apartment rental listings on [saga.hamburg](https://www.saga.hamburg/immobiliensuche?Kategorie=APARTMENT) and sends them instantly to all subscribed Telegram users.

---

## 🚀 Features

- 📡 Real-time monitoring of [saga.hamburg](https://www.saga.hamburg)
- 📬 Instant Telegram notifications for new listings
- 👥 Multi-user support with `/start` subscription
- 🧹 Automatic cache cleanup
- ☁️ Easy deployment to [Railway](https://railway.app)
- ⚙️ CI/CD with GitHub Actions

---

## 🧩 Project Structure

```
saga-telegram-bot/
├── saga_bot.py                 # main bot logic
├── known_offers.txt            # cache of known listing IDs
├── subscribers.txt             # list of subscriber chat IDs
├── .env                        # local environment variables
├── requirements.txt            # Python dependencies
├── Dockerfile                  # container config for Railway
├── .github/workflows/deploy.yml  # CI/CD via GitHub Actions
└── README.md
```

---

## ⚙️ Local Setup

1. Clone the repo:
```bash
git clone https://github.com/yourusername/saga-telegram-bot.git
cd saga-telegram-bot
```

2. Create a `.env` file:
```
TELEGRAM_TOKEN=your_bot_token
SAGA_URL=https://www.saga.hamburg/immobiliensuche?Kategorie=APARTMENT
CHECK_INTERVAL=300
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the bot:
```bash
python saga_bot.py
```

---

## ☁️ Deploy to Railway

1. Sign in at [https://railway.app](https://railway.app)
2. Create a new project and link your GitHub repo or upload manually
3. Set the following environment variables:
   - `TELEGRAM_TOKEN=your_bot_token`
   - `SAGA_URL=https://www.saga.hamburg/immobiliensuche?Kategorie=APARTMENT`
   - `CHECK_INTERVAL=300`

4. Set the start command:
```bash
python saga_bot.py
```

---

## 🔄 GitHub Actions (CI/CD)

`.github/workflows/deploy.yml`:

```yaml
name: Deploy Bot

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: 3.11

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run bot
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          SAGA_URL: ${{ secrets.SAGA_URL }}
          CHECK_INTERVAL: 300
        run: python saga_bot.py
```

> Make sure to add your secrets in **Settings → Secrets → Actions** on GitHub.

---

## 🧹 Cache Handling (`known_offers.txt`)

This file stores listing IDs already sent to users.

- ✅ Safe to keep it — prevents duplicates
- 🔁 Automatically updated by the bot
- 🗑 Delete it manually if you want to re-send all listings

---

## 💬 Commands

- `/start` → Subscribes user to updates
- (optional) `/stop` → Unsubscribe support can be added easily

---

## 📌 Notes

- One bot instance only — do **not** run locally and on Railway at the same time
- To reset listing cache, just delete `known_offers.txt`
- You can add logging, filters, or admin control for advanced use

---

Made with ❤️ in Python
```