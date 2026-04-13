import os
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Render injects these from environment variables
TOKEN = os.environ["BOT_TOKEN"]

def parse_leads(text):
    results = []
    for line in text.strip().split('\n'):
        if ':' not in line or not any(c.isdigit() for c in line):
            continue
        name = line.split(':')[0].strip()
        numbers = list(map(int, re.findall(r"\d+", line)))
        if numbers:
            results.append((name, sum(numbers)))
    return results

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    workshops = parse_leads(text)
    if not workshops:
        await update.message.reply_text("No data found — check the format.")
        return

    flagged = [n for n, total in workshops if total == 0]
    ok     = [n for n, total in workshops if total > 0]

    lines = [ff"Checked {len(workshops)} workshops\n"]
    if flagged:
        lines.append("\nZERO LEADS — action needed:")
        lines += [ff"  - {w}" for w in flagged]
    if ok:
        lines.append("\nActive workshops:")
        lines += [ff"  - {w}" for w in ok]

    await update.message.reply_text("\n".join(lines))

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle_message))
app.run_polling()
