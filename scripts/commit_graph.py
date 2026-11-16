"""Render a monthly commit chart for all public repositories of the organization.

Data source: GET /repos/{org}/{repo}/stats/commit_activity (daily counts for the
last 52 weeks, default branch). Output: profile/assets/commit-activity.svg.
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ORG = os.environ.get("ORG", "Manacost-Labs")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
OUT = Path(__file__).resolve().parent.parent / "profile" / "assets" / "commit-activity.svg"
SKIP = {".github"}

MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def api(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "commit-graph")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        return resp.status, (json.loads(body) if body else None)


def public_repos():
    repos, page = [], 1
    while True:
        _, data = api(f"/orgs/{ORG}/repos?type=public&per_page=100&page={page}")
        if not data:
            return repos
        repos += [r["name"] for r in data if not r["archived"] and not r["fork"] and r["name"] not in SKIP]
        page += 1


def commit_activity(repo):
    for _ in range(8):
        status, data = api(f"/repos/{ORG}/{repo}/stats/commit_activity")
        if status == 200 and isinstance(data, list):
            return data
        if status == 204:
            return []
        time.sleep(3)  # 202: GitHub is computing the statistics
    print(f"warning: no stats for {repo}", file=sys.stderr)
    return []


def collect():
    daily, per_repo = {}, {}
    for repo in public_repos():
        total = 0
        for week in commit_activity(repo):
            start = dt.datetime.fromtimestamp(week["week"], dt.timezone.utc).date()
            for i, n in enumerate(week["days"]):
                if n:
                    day = start + dt.timedelta(days=i)
                    daily[day] = daily.get(day, 0) + n
                    total += n
        if total:
            per_repo[repo] = total
    return daily, per_repo


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def render(daily, per_repo, today):
    # Twelve calendar months ending with the current (partial) one.
    end = today.year * 12 + today.month - 1
    months = [divmod(i, 12) for i in range(end - 11, end + 1)]
    first = dt.date(months[0][0], months[0][1] + 1, 1)
    days = [first + dt.timedelta(days=i) for i in range((today - first).days + 1)]
    counts = [daily.get(d, 0) for d in days]
    values = [sum(c for d, c in zip(days, counts) if (d.year, d.month - 1) == m) for m in months]

    total = sum(counts)
    active = sum(1 for c in counts if c)
    streak = best = 0
    for c in counts:
        streak = streak + 1 if c else 0
        best = max(best, streak)

    stats = [
        (f"{total:,}".replace(",", " "), plural(total, "коммит", "коммита", "коммитов")),
        (str(active), plural(active, "активный день", "активных дня", "активных дней")),
        (str(best), plural(best, "день подряд", "дня подряд", "дней подряд")),
    ]
    stat_svg = "".join(
        f'<text x="{64 + i * 400}" y="196" font-size="72" font-weight="800" fill="#ffffff">{v}</text>'
        f'<text x="{68 + i * 400}" y="238" font-size="28" fill="#c9dcdd">{label}</text>'
        for i, (v, label) in enumerate(stats)
    )

    base, top, step, width = 520, 300, 96, 68
    peak = max(values) or 1
    bars = []
    for i, ((year, month), n) in enumerate(zip(months, values)):
        x = 64 + i * step
        h = round((base - top) * n / peak)
        fill = "url(#barNow)" if i == 11 else "url(#bar)"
        tip = f"{MONTHS[month]} {year}: {n}"
        if n:
            bars.append(f'<rect x="{x}" y="{base - h}" width="{width}" height="{h}" rx="10" fill="{fill}"{' stroke="#4fd8cc" stroke-width="2" stroke-dasharray="6 5"' if i == 11 else ''}><title>{tip}</title></rect>')
            bars.append(f'<text x="{x + width / 2}" y="{base - h - 14}" text-anchor="middle" font-size="26" font-weight="700" fill="#ffffff">{n}</text>')
        else:
            bars.append(f'<rect x="{x}" y="{base - 4}" width="{width}" height="4" rx="2" fill="#24393d"><title>{tip}</title></rect>')
        bars.append(f'<text x="{x + width / 2}" y="{base + 42}" text-anchor="middle" font-size="26" fill="#c9dcdd">{MONTHS[month]}</text>')

    period = f"{MONTHS[months[0][1]]} {months[0][0]} — {MONTHS[months[-1][1]]} {months[-1][0]}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="620" viewBox="0 0 1280 620" role="img" aria-labelledby="t d">
<title id="t">Активность Manacost Labs</title>
<desc id="d">Коммиты во всех открытых репозиториях по месяцам, {period}: всего {total}, активных дней {active}.</desc>
<defs>
<linearGradient id="bg" x2="1" y2=".7"><stop stop-color="#0d1417"/><stop offset=".55" stop-color="#0a1013"/><stop offset="1" stop-color="#0c2326"/></linearGradient>
<linearGradient id="bar" x2="0" y2="1"><stop stop-color="#4fd8cc"/><stop offset="1" stop-color="#1f8f8a"/></linearGradient>
<linearGradient id="barNow" x2="0" y2="1"><stop stop-color="#4fd8cc" stop-opacity=".45"/><stop offset="1" stop-color="#1f8f8a" stop-opacity=".35"/></linearGradient>
</defs>
<rect width="1280" height="620" rx="28" fill="url(#bg)"/>
<rect x="1" y="1" width="1278" height="618" rx="27" fill="none" stroke="#7fe0d6" stroke-opacity=".22" stroke-width="2"/>
<g font-family="'Segoe UI', Inter, 'Helvetica Neue', Arial, sans-serif">
<text x="64" y="84" font-size="40" font-weight="800" fill="#ffffff">Активность команды</text>
<text x="1216" y="82" text-anchor="end" font-size="26" fill="#5fe3d6">{period}</text>
{stat_svg}
<line x1="64" y1="{base}" x2="1216" y2="{base}" stroke="#2c4549" stroke-width="2"/>
{''.join(bars)}
<text x="64" y="598" font-size="22" fill="#8fa9ac">Коммиты в открытых репозиториях · обновлено {today.strftime('%d.%m.%Y')}</text>
</g>
</svg>
"""


def main():
    daily, per_repo = collect()
    today = dt.datetime.now(dt.timezone.utc).date()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(daily, per_repo, today), encoding="utf-8", newline="\n")
    print(f"{OUT}: {sum(daily.values())} commits, {len(per_repo)} repos")


if __name__ == "__main__":
    main()
