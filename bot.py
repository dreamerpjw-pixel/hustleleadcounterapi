print("🔥 BOT STARTING")
print("TOKEN:", bool(TOKEN))
print("WEBHOOK:", WEBHOOK_URL)

import os
import csv
import re
from io import StringIO
from collections import defaultdict

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

import asyncio
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

# =========================
# STATE STORAGE 🧠
# =========================
user_state = {}

# =========================
# COMMANDS 🎮
# =========================
def reset_state(user_id):
    user_state[user_id] = {"step": 1, "baseline": {}, "reported": {}}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)

    await update.message.reply_text(
        "👋 *Welcome to the Leakage Bot*\n\n"
        "Step 1️⃣: Upload your baseline CSV 📎\n"
        "Step 2️⃣: Paste reported leads text 💬\n\n"
        "Use /sample to see format examples.\n"
        "Use /reset anytime to restart.",
        parse_mode="Markdown"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *How to use*\n\n"
        "1. Upload CSV with workshop + count\n"
        "2. Paste reported text\n\n"
        "Commands:\n"
        "/start - Restart flow\n"
        "/reset - Clear session\n"
        "/sample - Show examples\n"
        "/status - Check progress",
        parse_mode="Markdown"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_state(user_id)

    await update.message.reply_text("🔄 Reset complete. Upload a new CSV to start.")


async def sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 *Sample Formats*\n\n"
        "*CSV:*\n"
        "Photography - 6 Apr, 10\n"
        "Videography - 23 Mar, 5\n\n"
        "*Text:*\n"
        "PPE - 8\n"
        "VVE - 3\n",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {"step": 1})

    step = state["step"]
    baseline = "✅" if state.get("baseline") else "❌"
    reported = "✅" if state.get("reported") else "❌"

    if step == 1:
        step_text = "Waiting for CSV upload 📎"
    elif step == 2:
        step_text = "Waiting for text input 💬"
    else:
        step_text = "Processing / Done"

    await update.message.reply_text(
        f"📊 *Current Status*\n\n"
        f"Step: {step_text}\n"
        f"Baseline: {baseline}\n"
        f"Reported: {reported}",
        parse_mode="Markdown"
    )


# =========================
# RULE ENGINE
# =========================
IGNORE = {"PCA"}
MERGE = {
    "CAM": "DSLR",
    "PPECAM": "DSLR"
}


def normalize(w):
    return w.strip().upper()


def apply_rules(w):
    if w in IGNORE:
        return None
    if w in MERGE:
        return MERGE[w]
    return w

WORKSHOP_MAP = {
    "Photography": "PPE",
    "Videography": "VVE",
    "Acrylic Painting": "CCA",
    "Digital Art": "DAR",
    "Watercolour": "WAR",
    "DSLR": "DSLR",
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
    "Floral Arrangement": "FPS",
    "Perfume": "SPD",
    "Vibe Coding": "AIC"
}
WORKSHOP_MAP = {k.upper(): v for k, v in WORKSHOP_MAP.items()}

# =========================
# STEP 1: CSV PARSER
# =========================
def clean_csv_workshop(raw):
    # removes date / extra metadata like:
    # "Photography - 6 Apr" → "Photography"
    return raw.split("-")[0].split("(")[0].strip()


def parse_csv(file_bytes):
    data = defaultdict(int)

    content = file_bytes.decode("utf-8")
    reader = csv.reader(StringIO(content))

    for row in reader:
        if len(row) < 2:
            continue

        # 1. clean raw workshop name
        raw_name = normalize(row[0])
        clean_name = clean_csv_workshop(raw_name)

        # 2. map full name → workshop code
        workshop = WORKSHOP_MAP.get(clean_name, clean_name)

        # 3. apply ignore / merge rules
        workshop = apply_rules(workshop)

        if not workshop:
            continue

        # 4. parse count safely
        try:
            count = int(row[1].replace(",", "").strip())
        except:
            continue

        data[workshop] += count

    return dict(data)


# =========================
# STEP 2: TEXT PARSER
# =========================
def parse_text(text):
    data = defaultdict(int)

    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("["):
            continue

        match = re.match(r"(.+?)\s*[-:]?\s*([\d,]+)", line)
        if not match:
            continue

        w = apply_rules(normalize(match.group(1)))
        if not w:
            continue

        count = int(match.group(2).replace(",", ""))
        data[w] += count

    return dict(data)

# =========================
# STEP 3: LEAKAGE ENGINE 🔍
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
            status = f"⚠️ Over-reporting: {abs(diff)}"
        else:
            status = "✅ Matched"

        result.append((k, base, rep, status))

    return result


# =========================
# FORMAT OUTPUT 📊
# =========================
def build_report(comparison):
    lines = ["📊 *LEAKAGE REPORT*\n"]

    for k, base, rep, status in comparison:
        lines.append(f"{k}")
        lines.append(f"Baseline: {base} | Reported: {rep} | {status}")
        lines.append("")

    return "\n".join(lines)


# =========================
# HANDLER (STATE MACHINE) ⚙️
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_state:
        reset_state(user_id)

    state = user_state[user_id]
    msg = update.message

    # =========================
    # STEP 1: CSV UPLOAD
    # =========================
    if state["step"] == 1:
        if msg.document:
            file = await msg.document.get_file()
            file_bytes = await file.download_as_bytearray()
            
            content = file_bytes.decode("utf-8", errors="ignore")
            state["step"] = 2
            state["baseline"] = parse_csv(file_bytes)

            await msg.reply_text("✅ Baseline CSV saved. Now paste reported text leads.")
        else:
            await msg.reply_text("📎 Please upload CSV first.")
        return

    # =========================
    # STEP 2: TEXT INPUT
    # =========================
    if state["step"] == 2:
        if msg.text:
            state["reported"] = parse_text(msg.text)
            state["step"] = 3

            await msg.reply_text("✅ Reported data saved. Generating reports...")

            baseline = state["baseline"]
            reported = state["reported"]

            # safety check
            if not reported:
                await msg.reply_text("❌ No valid leads found in text.")
                return

            # build outputs
            comparison = compare(baseline, reported)
            report = build_report(comparison)

            lead_alert = build_lead_alert(reported)
            leakage_alert = build_leakage_alert(baseline, reported)

            # send dashboards first
            await msg.reply_text(lead_alert, parse_mode="Markdown")
            await msg.reply_text(leakage_alert, parse_mode="Markdown")

            # then detailed report
            await msg.reply_text(report, parse_mode="Markdown")

            # reset for next cycle
            user_state[user_id] = {"step": 1, "baseline": {}, "reported": {}}

        else:
            await msg.reply_text("💬 Please paste text input.")
        return


# =========================
# DASHBOARD 1: LEAD ALERT 📊
# =========================
def build_lead_alert(reported):
    sorted_data = sorted(reported.items(), key=lambda x: x[1], reverse=True)

    zero = [w for w, v in reported.items() if v == 0]
    low = [w for w, v in reported.items() if 1 <= v <= 2]
    top = sorted_data[:3]

    lines = ["📊 *LEAD COUNT ALERT*\n"]

    if zero:
        lines.append("🚨 *No Leads (0)*")
        for w in zero:
            lines.append(f"• {w} — 0 ❌")
        lines.append("")

    if low:
        lines.append("⚠️ *Low Leads (1–2)*")
        for w in low:
            lines.append(f"• {w} — {reported[w]} ⚠️")
        lines.append("")

    lines.append("🏆 *Top Performers*")
    for i, (w, v) in enumerate(top, 1):
        lines.append(f"{i}. {w} — {v}")

    return "\n".join(lines)


# =========================
# DASHBOARD 2: LEAKAGE ALERT 📉
# =========================
def build_leakage_alert(baseline, reported):
    lines = ["📉 *LEAKAGE ALERT*\n"]

    high_leak = []
    over = []
    healthy = []

    all_keys = set(baseline) | set(reported)

    for w in all_keys:
        base = baseline.get(w, 0)
        rep = reported.get(w, 0)

        if base == 0:
            continue

        diff = base - rep
        leakage_pct = diff / base

        if leakage_pct > 0.4:
            high_leak.append((w, leakage_pct, base, rep))
        elif diff < 0:
            over.append((w, abs(diff)))
        else:
            healthy.append(w)

    if high_leak:
        lines.append("🚨 *High Leakage (>40%)*")
        for w, pct, base, rep in high_leak:
            lines.append(f"• {w} — {int(pct*100)}% (Baseline: {base} | Reported: {rep})")
        lines.append("")

    if over:
        lines.append("⚠️ *Over-Reporting*")
        for w, val in over:
            lines.append(f"• {w} — +{val}")
        lines.append("")

    if healthy:
        lines.append("✅ *Healthy*")
        for w in healthy[:5]:
            lines.append(f"• {w}")

    return "\n".join(lines)



# =========================
# CONFIG
# =========================
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # MUST be set on Render

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set")

app = ApplicationBuilder().token(TOKEN).build()


# =========================
# TELEGRAM HANDLER
# =========================
async def handle(request):
    data = await request.json()

    update = Update.de_json(data, app.bot)
    await app.process_update(update)

    return web.Response(text="ok")


# =========================
# REGISTER HANDLERS
# =========================
def register_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("sample", sample))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_message))


register_handlers(app)


# =========================
# SERVER BOOTSTRAP
# =========================
async def runner():
    await app.initialize()
    await app.start()

    # Register webhook AFTER start
    await app.bot.set_webhook(WEBHOOK_URL)

    web_app = web.Application()
    web_app.router.add_post(WEBHOOK_PATH, handle)

    runner = web.AppRunner(web_app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("Bot is running...")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
        await app.shutdown()


# =========================
# ENTRYPOINT
# =========================
def main():
    asyncio.run(runner())


if __name__ == "__main__":
    main()
