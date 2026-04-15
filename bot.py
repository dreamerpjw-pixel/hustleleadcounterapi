import os
import csv
import re
import asyncio
from io import StringIO
from collections import defaultdict

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set")


# =========================
# APP
# =========================
app = ApplicationBuilder().token(TOKEN).build()

user_state = {}


def reset_state(user_id):
    user_state[user_id] = {"step": 1, "baseline": {}, "reported": {}}


# =========================
# COMMANDS (UNCHANGED LOGIC)
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)

    await update.message.reply_text("👋 Bot started")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Help menu")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state(update.effective_user.id)
    await update.message.reply_text("Reset done")


# =========================
# MESSAGE HANDLER (your logic kept)
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_state:
        reset_state(user_id)

    state = user_state[user_id]
    msg = update.message

    if state["step"] == 1:
        if msg.document:
            file = await msg.document.get_file()
            file_bytes = await file.download_as_bytearray()

            state["baseline"] = parse_csv(file_bytes)
            state["step"] = 2

            await msg.reply_text("CSV saved")
        return

    if state["step"] == 2:
        if msg.text:
            state["reported"] = parse_text(msg.text)
            await msg.reply_text("Done")


# =========================
# PARSERS (keep yours unchanged)
# =========================
def parse_csv(file_bytes):
    data = defaultdict(int)
    content = file_bytes.decode("utf-8", errors="ignore")
    reader = csv.reader(StringIO(content))

    for row in reader:
        if len(row) < 2:
            continue
        try:
            data[row[0]] += int(row[1])
        except:
            continue

    return dict(data)


def parse_text(text):
    data = defaultdict(int)

    for line in text.split("\n"):
        match = re.match(r"(.+?)\s*[-:]?\s*([\d,]+)", line)
        if match:
            data[match.group(1)] += int(match.group(2))

    return dict(data)


# =========================
# REGISTER
# =========================
def register_handlers():
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.ALL, handle_message))


register_handlers()


# =========================
# RUNNER (WORKER MODE)
# =========================
async def runner():
    await app.initialize()
    await app.start()

    await app.bot.set_webhook(WEBHOOK_URL)

    print("🔥 BOT RUNNING")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(runner())
