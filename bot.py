import os
import csv
import re
from io import StringIO
from collections import defaultdict

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

# =========================
# STATE STORAGE 🧠
# =========================
user_state = {}


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
            count = int(row[1])
        except:
            continue

        data[workshop] += count

    return dict(data)


# =========================
# STEP 2: TEXT PARSER
# =========================
def parse_text(text):
    data = defaultdict(int)
    current = None

    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("["):
            continue

        if line.startswith("*") and line.endswith("*"):
            current = line.strip("*")
            continue

        match = re.match(r"(.+?)\s*[-:]?\s*([\d,]+)", line)
        count = int(match.group(2).replace(",", ""))
        if match:
            w = apply_rules(normalize(match.group(1)))
            if not w:
                continue

            data[w] += int(match.group(2))

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
        user_state[user_id] = {"step": 1, "baseline": {}, "reported": {}}

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
# BOOT 🚀
# =========================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.ALL, handle_message))

app.run_polling()
