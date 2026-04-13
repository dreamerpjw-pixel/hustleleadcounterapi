import json
from datetime import datetime, timedelta
from collections import defaultdict

DATA_FILE = "history.json"

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


def build_trend_text(today_totals, yesterday_totals):
    lines = ["📈 *TREND TRACKER*"]

    all_workshops = set(today_totals) | set(yesterday_totals)

    for w in sorted(all_workshops):
        today = today_totals.get(w, 0)
        yesterday = yesterday_totals.get(w, 0)
        diff = today - yesterday

        if diff > 0:
            lines.append(f"{w} ↑ +{diff}")
        elif diff < 0:
            lines.append(f"{w} ↓ {diff}")
        else:
            if today == 0:
                lines.append(f"{w} → 0 💀")
            else:
                lines.append(f"{w} → {today}")

    return "\n".join(lines)

# Aggregate totals
totals = defaultdict(int)
for person, workshops in data.items():
    for w, count in workshops.items():
        totals[w] += count

# 🔥 NEW: Trend tracking
save_today_totals(dict(totals))
yesterday_totals = get_yesterday_totals()
trend_text = build_trend_text(totals, yesterday_totals)

lines.append("")
lines.append(trend_text)
