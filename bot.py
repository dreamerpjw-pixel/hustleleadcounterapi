import os
import csv
import re
import asyncio
from io import StringIO
from collections import defaultdict

from aiohttp import web

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
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", 10000))

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set")


# =========================
# STATE STORAGE 🧠
# =========================
user_state = {}


def reset_state(user_id):
    user_state[user_id] = {"step": 1, "baseline": {}, "reported": {}}


# =========================
# COMMANDS 🎮
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)

    await update.message.reply_text(
        "👋 *Welcome to the Leakage Bot*\n\n"
        "Step 1️⃣: Upload your baseline CSV 📎\n"
        "Step 2️⃣: Paste reported leads text 💬\n\n"
        "Use /sample to see format examples.\n"
        "Use /reset anytime to restart.",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *How to use*\n\n"
        "1. Upload CSV\n"
        "2. Paste reported text\n\n"
        "Commands:\n"
        "/start\n/reset\n/sample\n/status",
        parse_mode="Markdown",
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state(update.effective_user.id)
    await update.message.reply_text("🔄 Reset complete.")


async def sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 *Sample Formats*\n\n"
        "Photography - 6 Apr, 10\n"
        "Videography - 23 Mar, 5\n\n"
        "PPE - 8\n"
        "VVE - 3",
        parse_mode="Markdown",
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {"step": 1})

    step = state["step"]
    baseline = "✅" if state.get("baseline") else "❌"
    reported = "✅" if state.get("reported") else "❌"

    step_text = (
        "Waiting for CSV 📎" if step == 1
        else "Waiting for text 💬" if step == 2
        else "Done"
    )

    await update.message.reply_text(
        f"📊 *Status*\n\nStep: {step_text}\nBaseline: {baseline}\nReported: {reported}",
        parse_mode="Markdown",
    )


# =========================
# RULE ENGINE
# =========================
IGNORE = {"PCA"}
MERGE = {"CAM": "DSLR", "PPECAM": "DSLR"}


def normalize(w):
    return w.strip().upper()


def apply_rules(w):
    if w in IGNORE:
        return None
    return MERGE.get(w, w)


WORKSHOP_MAP = {
    "PHOTOGRAPHY": "PPE",
    "VIDEOGRAPHY": "VVE",
    "ACRYLIC PAINTING": "CCA",
    "DIGITAL ART": "DAR",
    "WATERCOLOR": "WAR",
    "DSLR": "DSLR",
}
WORKSHOP_MAP = {k.upper(): v for k, v in WORKSHOP_MAP.items()}


# =========================
# PARSERS
# =========================
def clean_csv_workshop(raw):
    return raw.split("-")[0].split("(")[0].strip()


def parse_csv(file_bytes):
    data = defaultdict(int)

    content = file_bytes.decode("utf-8", errors="ignore")
    reader = csv.reader(StringIO(content))

    for row in reader:
        if len(row) < 2:
            continue

        name = normalize(clean_csv_workshop(row[0]))
        workshop = WORKSHOP_MAP.get(name, name)
        workshop = apply_rules(workshop)

        if not workshop:
            continue

        try:
            count = int(row[1].replace(",", "").strip())
        except:
            continue

        data[workshop] += count

    return dict(data)


def parse_text(text):
    data = defaultdict(int)

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        match = re.match(r"(.+?)\s*[-:]?\s*([\d,]+)", line)
        if not match:
            continue

        w = apply_rules(normalize(match.group(1)))
        if not w:
            continue

        data[w] += int(match.group(2).replace(",", ""))

    return dict(data)


# =========================
# ENGINE
# =========================
def compare(baseline, reported):
    all_keys = set(baseline) | set(reported)
    result = []

    for k in sorted(all_keys):
        base = baseline.get(k, 0)
        rep = reported.get(k, 0)
        diff = base - rep

        if diff > 0:
            status = f"🔻 Leakage: {diff}"
        elif diff < 0:
            status = f"⚠️ Over: {abs(diff)}"
        else:
            status = "✅ Match"

        result.append((k, base, rep, status))

    return result


def build_report(comparison):
    lines = ["📊 LEAKAGE REPORT\n"]
    for k, b, r, s in comparison:
        lines.append(f"{k}")
        lines.append(f"{b} | {r} | {s}\n")
    return "\n".join(lines)


# =========================
# DASHBOARDS
# =========================
def build_lead_alert(reported):
    top = sorted(reported.items(), key=lambda x: x[1], reverse=True)[:3]
    return "📊 LEAD ALERT\n\n" + "\n".join([f"{k}: {v}" for k, v in top])


def build_leakage_alert(baseline, reported):
    lines = ["📉 LEAKAGE ALERT\n"]

    for k in set(baseline) | set(reported):
        b = baseline.get(k, 0)
        r = reported.get(k, 0)
        if b == 0:
            continue

        pct = (b - r) / b
        if pct > 0.4:
            lines.append(f"🚨 {k}: {int(pct*100)}% leak")

    return "\n".join(lines)


# =========================
# STATE HANDLER
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

            await msg.reply_text("✅ CSV saved. Paste text next.")
        else:
            await msg.reply_text("📎 Upload CSV first.")
        return

    if state["step"] == 2:
        if msg.text:
            state["reported"] = parse_text(msg.text)
            state["step"] = 3

            baseline = state["baseline"]
            reported = state["reported"]

            comparison = compare(baseline, reported)

            await msg.reply_text(build_lead_alert(reported))
            await msg.reply_text(build_leakage_alert(baseline, reported))
            await msg.reply_text(build_report(comparison))

            reset_state(user_id)
        else:
            await msg.reply_text("💬 Paste text.")


# =========================
# TELEGRAM APP
# =========================
app = ApplicationBuilder().token(TOKEN).build()


def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("sample", sample))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.ALL, handle_message))


register_handlers(app)


# =========================
# WEBHOOK SERVER
# =========================
async def handle(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="ok")


async def runner():
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(WEBHOOK_URL)

    web_app = web.Application()
    web_app.router.add_post(WEBHOOK_PATH, handle)

    runner = web.AppRunner(web_app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("🔥 BOT RUNNING")

    await asyncio.Event().wait()


def main():
    asyncio.run(runner())


if __name__ == "__main__":
    main()
