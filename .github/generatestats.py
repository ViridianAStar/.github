import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_TOKEN"]

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }

      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalRepositoryContributions

      commitContributionsByRepository(maxRepositories: 100) {
        repository {
          name
          languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
            edges {
              size
              node {
                name
                color
              }
            }
          }
        }
        contributions {
          totalCount
        }
      }
    }
  }
}
"""

payload = json.dumps({
    "query": QUERY,
    "variables": {"login": USERNAME}
}).encode()

request = urllib.request.Request(
    "https://api.github.com/graphql",
    data=payload,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": USERNAME,
    },
)

with urllib.request.urlopen(request) as response:
    result = json.load(response)

if "errors" in result:
    raise RuntimeError(result["errors"])

data = result["data"]["user"]["contributionsCollection"]

calendar = data["contributionCalendar"]
weeks = calendar["weeks"]

total = calendar["totalContributions"]
commits = data["totalCommitContributions"]
prs = data["totalPullRequestContributions"]
issues = data["totalIssueContributions"]
repos = data["totalRepositoryContributions"]

# Flatten contribution days.
days = [
    day
    for week in weeks
    for day in week["contributionDays"]
]

# Last 12 months.
cutoff = datetime.now() - timedelta(days=365)

recent_days = [
    day for day in days
    if datetime.fromisoformat(day["date"]).replace(tzinfo=None) >= cutoff
]

# Contribution grid.
cell_size = 11
cell_gap = 3
grid_x = 30
grid_y = 145

max_daily = max(
    (day["contributionCount"] for day in recent_days),
    default=1
)

def contribution_color(count):
    if count == 0:
        return "#161b22"

    ratio = count / max_daily

    if ratio < 0.25:
        return "#0e4429"
    if ratio < 0.50:
        return "#006d32"
    if ratio < 0.75:
        return "#26a641"

    return "#39d353"


cells = []

for index, day in enumerate(recent_days):
    column = index // 7
    row = index % 7

    x = grid_x + column * (cell_size + cell_gap)
    y = grid_y + row * (cell_size + cell_gap)

    cells.append(
        f'<rect x="{x}" y="{y}" width="{cell_size}" '
        f'height="{cell_size}" rx="2" fill="{contribution_color(day["contributionCount"])}">'
        f'<title>{day["date"]}: {day["contributionCount"]} contributions</title>'
        f'</rect>'
    )

# Language aggregation.
languages = {}

for repo in data["commitContributionsByRepository"]:
    for edge in repo["repository"]["languages"]["edges"]:
        language = edge["node"]["name"]
        color = edge["node"]["color"] or "#888888"

        languages.setdefault(
            language,
            {"size": 0, "color": color}
        )

        languages[language]["size"] += edge["size"]

total_language_size = sum(
    language["size"] for language in languages.values()
)

top_languages = sorted(
    languages.items(),
    key=lambda item: item[1]["size"],
    reverse=True
)[:5]

language_rows = []

for index, (name, language) in enumerate(top_languages):
    percentage = (
        language["size"] / total_language_size * 100
        if total_language_size
        else 0
    )

    y = 285 + index * 26

    language_rows.append(
        f"""
        <circle cx="35" cy="{y - 5}" r="5" fill="{language["color"]}"/>
        <text x="50" y="{y}" class="label">{name}</text>
        <text x="420" y="{y}" text-anchor="end" class="value">
            {percentage:.1f}%
        </text>
        """
    )

svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
width="760"
height="450"
viewBox="0 0 760 450">

<rect width="760" height="450" rx="12" fill="#0d1117"/>

<style>
.title {{
    fill: #f0f6fc;
    font: 600 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}

.subtitle {{
    fill: #8b949e;
    font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}

.number {{
    fill: #f0f6fc;
    font: 600 22px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}

.stat {{
    fill: #8b949e;
    font: 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    letter-spacing: .5px;
}}

.label {{
    fill: #c9d1d9;
    font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}

.value {{
    fill: #8b949e;
    font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
</style>

<text x="30" y="38" class="title">GitHub Activity</text>
<text x="30" y="60" class="subtitle">@{USERNAME} · automatically updated</text>

<text x="30" y="92" class="number">{commits}</text>
<text x="30" y="110" class="stat">COMMITS</text>

<text x="150" y="92" class="number">{prs}</text>
<text x="150" y="110" class="stat">PULL REQUESTS</text>

<text x="310" y="92" class="number">{issues}</text>
<text x="310" y="110" class="stat">ISSUES</text>

<text x="420" y="92" class="number">{repos}</text>
<text x="420" y="110" class="stat">REPOSITORIES</text>

<text x="600" y="92" class="number">{total}</text>
<text x="600" y="110" class="stat">CONTRIBUTIONS</text>

<text x="30" y="135" class="subtitle">Contribution history · last 12 months</text>

{''.join(cells)}

<line x1="30" y1="230" x2="730" y2="230"
      stroke="#21262d"/>

<text x="30" y="260" class="title">Languages</text>

{''.join(language_rows)}

</svg>
"""

output = Path("assets/github-stats.svg")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(svg, encoding="utf-8")

print(f"Generated {output}")
