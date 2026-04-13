import os
import re
import json
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "history.json"

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")


# =========================
# PARSER (WhatsApp-friendly)
# =========================
def parse_leads(text):
    data = {}
    current_person = None

    for line in text.split("\n"):
        line = line.strip()

        # Skip WhatsApp timestamps
        if line.startswith("["):
            continue

        # Detect names (*Ryan* or plain names)
        if line.startswith("*") and line.endswith("*"):
            current_person = line.strip("*")
            data[current_person] = {}
            continue

        # Plain name line (Phoebe, Khian, etc.)
        if line and not any(c.isdigit() for c in line) and ":" not in line:
            current_person = line
            data[current_person] = {}
            continue

        # Match workshop patterns:
        match = re.match(r"([A-Za-z]+)\s*[-:]?\s*(\d+)", line)
        if match and current_person:
            workshop = match.group(1).strip()
            count = int(match.group(2))
            data[current_person][workshop] = count

    return data


# =========================
# STORAGE (trend tracking)
# =========================
def save_today_totals(totals):
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        with open(DATA_FILE, "r") as f:
            history = json.load(f)
    except:
        history = {}

    history[today] = totals

    with open(DATA_FILE, "w") as f:
        json.dump(history, f)


def get_yesterday_totals():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        with open(DATA_FILE, "r") as f:
            history = json.load(f)
        return history.get(yesterday, {})
    except:
        return {}


def build_trend_text(today, yesterday):
    lines = ["📈 *TREND TRACKER*"]

    all_keys = set(today.keys()) | set(yesterday.keys())

    for w in sorted(all_keys):
        diff = today.get(w, 0) - yesterday.get(w, 0)

        if diff > 0:
            lines.append(f"{w} ↑ +{diff}")
        elif diff < 0:
            lines.append(f"{w} ↓ {diff}")
        else:
            if today.get(w, 0) == 0:
                lines.append(f"{w} → 0 💀")
            else:
                lines.append(f"{w} → {today.get(w, 0)}")

    return "\n".join(lines)


# =========================
# MAIN HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    data = parse_leads(text)

    if not data:
        await update.message.reply_text("No data found — check format.")
        return

    # =========================
    # Aggregate totals
    # =========================
    totals = defaultdict(int)

    for person, workshops in data.items():
        for w, count in workshops.items():
            totals[w] += count

    totals_dict = dict(totals)

    # =========================
    # Save + trends
    # =========================
    save_today_totals(totals_dict)
    yesterday = get_yesterday_totals()
    trend_text = build_trend_text(totals_dict, yesterday)

    # =========================
    # Categories
    # =========================
    sorted_workshops = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    top = sorted_workshops[:3]
    zero = [w for w, v in totals.items() if v == 0]
    low = [w for w, v in totals.items() if 1 <= v <= 2]

    today_date = datetime.now().strftime("%d %b %Y")

    # =========================
    # BUILD DASHBOARD
    # =========================
    lines = [f"📊 *WORKSHOP DASHBOARD — {today_date}*\n"]

    # 🏆 Top
    lines.append("🏆 *Top Workshops*")
    for i, (w, v) in enumerate(top, 1):
        lines.append(f"{i}. {w} — {v}")
    lines.append("")

    # 🚨 Zero
    if zero:
        lines.append("🚨 *Needs Attention (0 leads)*")
        for w in zero:
            lines.append(f"• {w} — 0 ❌")
        lines.append("")

    # ⚠️ Low
    if low:
        lines.append("⚠️ *Low Leads (1–2)*")
        for w in low:
            lines.append(f"• {w} — {totals[w]} ⚠️")
        lines.append("")

    # 👤 By Salesperson
    lines.append("👤 *By Salesperson*")
    for person, workshops in data.items():
        row = []
        for w, v in workshops.items():
            if v == 0:
                row.append(f"{w} {v} ❌")
            elif 1 <= v <= 2:
                row.append(f"{w} {v} ⚠️")
            else:
                row.append(f"{w} {v}")
        lines.append(f"\n*{person}*")
        lines.append(" | ".join(row))

    # 📈 Trend
    lines.append("")
    lines.append(trend_text)

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# =========================
# BOOT
# =========================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
