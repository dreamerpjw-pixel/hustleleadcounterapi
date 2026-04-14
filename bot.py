import os
import re
import json
import csv
from datetime import datetime, timedelta
from collections import defaultdict
from io import StringIO

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
# WORKSHOP ALIAS MAP 🧠
# =========================
WORKSHOP_MAP = {
    "Photography": "PPE",
    "Videography": "VVE",
    "Acrylic Painting": "CCA",
    "Digital Art": "DAR",
    "Watercolour": "WAR",
    "DSLR Photography": "DSLR",
    "Canva Social Media": "CSM",
    "Canva Pro": "GDC",
    "DJ Sound Mixing": "PSM",
    "General AI": "PHG",
    "Music Production": "DMP",
    "Guitar": "GMP",
    "Public Speaking": "PPS",
    "AI Video": "AVC",
    "Money Management": "MMW",
    "Leica": "LVS",
    "Negotiation": "BNG",
    "Floral Styling": "FPS",
    "Perfume": "SPD",
    "Vibe Coding": "AIC"
}


def normalize_workshop(name: str) -> str:
    name = name.strip()
    return WORKSHOP_MAP.get(name, name)


# =========================
# PARSER (TEXT MODE)
# =========================
def parse_leads(text):
    data = {}
    current_person = None

    for line in text.split("\n"):
        line = line.strip()

        if line.startswith("["):
            continue

        if line.startswith("*") and line.endswith("*"):
            current_person = line.strip("*")
            data[current_person] = {}
            continue

        if line and not any(c.isdigit() for c in line) and ":" not in line:
            current_person = line
            data[current_person] = {}
            continue

        match = re.match(r"([A-Za-z]+)\s*[-:]?\s*(\d+)", line)
        if match and current_person:
            workshop = normalize_workshop(match.group(1))
            count = int(match.group(2))
            data[current_person][workshop] = count

    return data


# =========================
# PARSER (CSV MODE)
# =========================
def parse_csv(file_bytes):
    data = defaultdict(dict)

    content = file_bytes.decode("utf-8")
    reader = csv.reader(StringIO(content))

    for row in reader:
        if len(row) < 3:
            continue

        person = row[0].strip()
        workshop = normalize_workshop(row[1])
        try:
            count = int(row[2])
        except:
            continue

        data[person][workshop] = count

    return data


# =========================
# STORAGE
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
            lines.append(f"{w} → {today.get(w, 0)}")

    return "\n".join(lines)


# =========================
# MAIN HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = {}

    # =========================
    # CSV INPUT 📎
    # =========================
    if update.message.document:
        file = await update.message.document.get_file()
        file_bytes = await file.download_as_bytearray()
        data = parse_csv(file_bytes)

    # =========================
    # TEXT INPUT 💬
    # =========================
    elif update.message.text:
        data = parse_leads(update.message.text)

    if not data:
        await update.message.reply_text("No data found — check format.")
        return

    # =========================
    # AGGREGATE
    # =========================
    totals = defaultdict(int)

    for person, workshops in data.items():
        for w, count in workshops.items():
            totals[w] += count

    totals_dict = dict(totals)

    # =========================
    # SAVE + TREND
    # =========================
    save_today_totals(totals_dict)
    yesterday = get_yesterday_totals()
    trend_text = build_trend_text(totals_dict, yesterday)

    # =========================
    # ANALYTICS
    # =========================
    sorted_workshops = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    top = sorted_workshops[:3]
    zero = [w for w, v in totals.items() if v == 0]
    low = [w for w, v in totals.items() if 1 <= v <= 2]

    today_date = datetime.now().strftime("%d %b %Y")

    # =========================
    # DASHBOARD BUILD
    # =========================
    lines = [f"📊 *WORKSHOP DASHBOARD — {today_date}*\n"]

    lines.append("🏆 *Top Workshops*")
    for i, (w, v) in enumerate(top, 1):
        lines.append(f"{i}. {w} — {v}")
    lines.append("")

    if zero:
        lines.append("🚨 *Needs Attention (0 leads)*")
        for w in zero:
            lines.append(f"• {w} — 0 ❌")
        lines.append("")

    if low:
        lines.append("⚠️ *Low Leads (1–2)*")
        for w in low:
            lines.append(f"• {w} — {totals[w]} ⚠️")
        lines.append("")

    lines.append("👤 *By Salesperson*")
    for person, workshops in data.items():
        rows = []
        for w, v in workshops.items():
            if v == 0:
                rows.append(f"{w} {v} ❌")
            elif v <= 2:
                rows.append(f"{w} {v} ⚠️")
            else:
                rows.append(f"{w} {v}")

        lines.append(f"\n*{person}*")
        lines.append(" | ".join(rows))

    lines.append("\n" + trend_text)

    # =========================
    # SEND OUTPUT
    # =========================
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# =========================
# BOOT
# =========================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.ALL, handle_message))

app.run_polling()
