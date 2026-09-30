#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_TOKEN"]

API = "https://api.github.com"
API_VERSION = "2026-03-10"


def github_request(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {TOKEN}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USERNAME,
        },
    )

    with urllib.request.urlopen(request) as response:
        return json.load(response)


def get_all_public_repositories():
    repositories = []
    page = 1

    while True:
        url = (
            f"{API}/users/{USERNAME}/repos?"
            f"type=owner&"
            f"per_page=100&"
            f"page={page}"
        )

        data = github_request(url)

        if not data:
            break

        repositories.extend(data)

        if len(data) < 100:
            break

        page += 1

    return [
        repo
        for repo in repositories
        if not repo["fork"] and not repo["private"]
    ]



def run_git(args, cwd):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )

    return result.stdout


def clone_repository(repo, destination):
    clone_url = repo["clone_url"]

    subprocess.run(
        [
            "git",
            "clone",
            "--mirror",
            "--quiet",
            clone_url,
            str(destination),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def get_branch_commits(repo_path):
    """
    Return every unique commit reachable from every branch.

    Because commits are identified by SHA, a commit shared by multiple
    branches is counted only once.
    """

    output = run_git(
        [
            "rev-list",
            "--branches",
        ],
        repo_path,
    )

    return set(
        sha.strip()
        for sha in output.splitlines()
        if sha.strip()
    )


def get_commit_stats(repo_path, sha):
    """
    Get additions/deletions for a commit.

    --numstat gives:
        additions deletions filename

    Binary files are represented with '- -', which we ignore because
    they do not have meaningful line additions/deletions.
    """

    output = run_git(
        [
            "show",
            "--numstat",
            "--format=",
            "--no-renames",
            sha,
        ],
        repo_path,
    )

    additions = 0
    deletions = 0

    for line in output.splitlines():
        parts = line.split("\t")

        if len(parts) < 3:
            continue

        added, deleted = parts[0], parts[1]

        if added.isdigit():
            additions += int(added)

        if deleted.isdigit():
            deletions += int(deleted)

    return additions, deletions


def get_languages(repo):
    """
    GitHub's language endpoint returns byte counts for the repository.
    """

    url = repo["languages_url"]
    data = github_request(url)

    return data


def escape_xml(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def format_number(number):
    return f"{number:,}"


print("Finding public repositories...")

repositories = get_all_public_repositories()

print(f"Found {len(repositories)} public repositories.")


total_commits = 0
total_additions = 0
total_deletions = 0

all_languages = {}

with tempfile.TemporaryDirectory() as temp_dir:

    temp_path = Path(temp_dir)

    for index, repo in enumerate(repositories, start=1):

        name = repo["full_name"]

        print(
            f"[{index}/{len(repositories)}] "
            f"Processing {name}"
        )

        repo_path = temp_path / repo["name"]

        try:
            clone_repository(
                repo,
                repo_path,
            )

        except subprocess.CalledProcessError:
            print(
                f"  Failed to clone {name}; skipping."
            )
            continue

        # ------------------------------------------------------
        # ALL BRANCH COMMITS
        # ------------------------------------------------------

        try:
            commits = get_branch_commits(repo_path)

        except subprocess.CalledProcessError:
            print(
                f"  Failed to enumerate commits; skipping."
            )
            continue

        print(
            f"  {len(commits):,} unique branch commits"
        )

        total_commits += len(commits)

        # ------------------------------------------------------
        # ADDITIONS / DELETIONS
        # ------------------------------------------------------

        for commit_index, sha in enumerate(
            commits,
            start=1,
        ):

            try:
                additions, deletions = get_commit_stats(
                    repo_path,
                    sha,
                )

                total_additions += additions
                total_deletions += deletions

            except subprocess.CalledProcessError:
                print(
                    f"  Failed to inspect commit {sha}; skipping."
                )

        # ------------------------------------------------------
        # LANGUAGES
        # ------------------------------------------------------

        try:
            languages = get_languages(repo)

            for language, bytes_count in languages.items():

                if language not in all_languages:
                    all_languages[language] = 0

                all_languages[language] += bytes_count

        except Exception:
            print(
                f"  Failed to retrieve languages for {name}."
            )


# --------------------------------------------------------------
# LANGUAGE PROCESSING
# --------------------------------------------------------------

total_language_bytes = sum(
    all_languages.values()
)

top_languages = sorted(
    all_languages.items(),
    key=lambda item: item[1],
    reverse=True,
)[:6]


# GitHub language colors.

LANGUAGE_COLORS = {
    "C++": "#f34b7d",
    "C": "#555555",
    "Python": "#3572A5",
    "Rust": "#dea584",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Shell": "#89e051",
    "Bash": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "C#": "#178600",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Lua": "#000080",
}


def language_color(name):
    return LANGUAGE_COLORS.get(
        name,
        "#8b949e",
    )


# --------------------------------------------------------------
# LANGUAGE ROWS
# --------------------------------------------------------------

language_rows = []

for index, (language, byte_count) in enumerate(
    top_languages
):

    percentage = (
        byte_count / total_language_bytes * 100
        if total_language_bytes
        else 0
    )

    y = 350 + index * 28

    color = language_color(language)

    language_rows.append(
        f"""
        <circle
            cx="35"
            cy="{y - 5}"
            r="5"
            fill="{color}"
        />

        <text
            x="50"
            y="{y}"
            class="label"
        >
            {escape_xml(language)}
        </text>

        <text
            x="500"
            y="{y}"
            text-anchor="end"
            class="value"
        >
            {percentage:.1f}%
        </text>
        """
    )


# --------------------------------------------------------------
# SVG
# --------------------------------------------------------------

svg = f"""<svg
xmlns="http://www.w3.org/2000/svg"
width="760"
height="540"
viewBox="0 0 760 540">

<style>

.title {{
    fill: #f0f6fc;
    font:
        600 20px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}}

.subtitle {{
    fill: #8b949e;
    font:
        13px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}}

.number {{
    fill: #f0f6fc;
    font:
        600 22px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}}

.stat {{
    fill: #8b949e;
    font:
        11px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    letter-spacing: .5px;
}}

.label {{
    fill: #c9d1d9;
    font:
        13px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}}

.value {{
    fill: #8b949e;
    font:
        13px
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}}

</style>

<rect
    width="760"
    height="540"
    rx="12"
    fill="#0d1117"
/>

<!-- Header -->

<text
    x="30"
    y="38"
    class="title"
>
    GitHub Activity
</text>

<text
    x="30"
    y="60"
    class="subtitle"
>
    @{escape_xml(USERNAME)} · public repositories
</text>

<!-- All-time statistics -->

<text
    x="30"
    y="98"
    class="number"
>
    {format_number(total_commits)}
</text>

<text
    x="30"
    y="116"
    class="stat"
>
    COMMITS
</text>

<text
    x="180"
    y="98"
    class="number"
>
    +{format_number(total_additions)}
</text>

<text
    x="180"
    y="116"
    class="stat"
>
    ADDITIONS
</text>

<text
    x="360"
    y="98"
    class="number"
>
    -{format_number(total_deletions)}
</text>

<text
    x="360"
    y="116"
    class="stat"
>
    DELETIONS
</text>

<text
    x="540"
    y="98"
    class="number"
>
    {format_number(len(repositories))}
</text>

<text
    x="540"
    y="116"
    class="stat"
>
    REPOSITORIES
</text>

<!-- Languages -->

<line
    x1="30"
    y1="145"
    x2="730"
    y2="145"
    stroke="#21262d"
/>

<text
    x="30"
    y="178"
    class="title"
>
    Languages
</text>

<text
    x="30"
    y="200"
    class="subtitle"
>
    Combined across public repositories
</text>

{''.join(language_rows)}

</svg>
"""


output = Path(
    "assets/github-stats.svg"
)

output.parent.mkdir(
    parents=True,
    exist_ok=True,
)

output.write_text(
    svg,
    encoding="utf-8",
)

print()
print("=" * 60)
print("GitHub statistics generated")
print("=" * 60)
print(f"Repositories : {len(repositories):,}")
print(f"Commits      : {total_commits:,}")
print(f"Additions    : {total_additions:,}")
print(f"Deletions    : {total_deletions:,}")
print("=" * 60)