#!/usr/bin/env python3

import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_TOKEN"]

API = "https://api.github.com"
API_VERSION = "2026-03-10"


# ============================================================
# GitHub API
# ============================================================

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

    try:
        with urllib.request.urlopen(request) as response:
            return __import__("json").load(response)

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"GitHub API returned HTTP {error.code} for {url}\n"
            f"{body}"
        ) from error


# ============================================================
# Repository discovery
# ============================================================

def get_all_accessible_public_repositories():
    """
    Get public repositories that the authenticated user can access.

    This includes:
      - repositories owned by the user
      - repositories where the user is a collaborator
      - repositories accessible through organization membership

    Private repositories are explicitly excluded.
    Forks are also excluded.
    """

    repositories = []
    page = 1

    print("Finding public repositories you can access...")

    while True:
        query = urllib.parse.urlencode(
            {
                "visibility": "public",
                "affiliation": (
                    "owner,"
                    "collaborator,"
                    "organization_member"
                ),
                "per_page": 100,
                "page": page,
            }
        )

        url = f"{API}/user/repos?{query}"

        data = github_request(url)

        if not data:
            break

        repositories.extend(data)

        print(
            f"  API page {page}: "
            f"{len(data)} repositories"
        )

        if len(data) < 100:
            break

        page += 1

    # Deduplicate by repository ID.
    unique = {}

    for repo in repositories:
        unique[repo["id"]] = repo

    repositories = list(unique.values())

    # Public + non-fork only.
    repositories = [
        repo
        for repo in repositories
        if not repo["private"]
        and not repo["fork"]
        and not repo["archived"]
        and not repo["disabled"]
    ]

    repositories.sort(
        key=lambda repo: repo["full_name"].lower()
    )

    return repositories


# ============================================================
# Git helpers
# ============================================================

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
    """
    Mirror-clone the repository.

    --mirror fetches all refs, including branches, rather than
    just the default branch.
    """

    subprocess.run(
        [
            "git",
            "clone",
            "--mirror",
            "--quiet",
            repo["clone_url"],
            str(destination),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def get_all_branch_commits(repo_path):
    """
    Return unique commits reachable from every branch.

    A commit shared by multiple branches is counted only once.
    """

    output = run_git(
        [
            "rev-list",
            "--branches",
        ],
        repo_path,
    )

    return {
        sha.strip()
        for sha in output.splitlines()
        if sha.strip()
    }


def get_repository_line_stats(repo_path):
    """
    Calculate additions/deletions across all branch history.

    We process the entire history in one Git invocation rather
    than running `git show` separately for every commit.
    """

    output = run_git(
        [
            "log",
            "--all",
            "--numstat",
            "--format=%H",
            "--no-renames",
        ],
        repo_path,
    )

    additions = 0
    deletions = 0

    for line in output.splitlines():

        parts = line.split("\t")

        if len(parts) != 3:
            continue

        added, deleted, _filename = parts

        # Binary files are represented by '-'.
        if added.isdigit():
            additions += int(added)

        if deleted.isdigit():
            deletions += int(deleted)

    return additions, deletions


# ============================================================
# GitHub language statistics
# ============================================================

def get_languages(repo):
    """
    GitHub reports language usage as bytes of source code.
    """

    return github_request(repo["languages_url"])


# ============================================================
# Language colors
# ============================================================

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
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Dart": "#00B4AB",
    "R": "#198CE7",
    "Makefile": "#427819",
}


def language_color(language):
    return LANGUAGE_COLORS.get(
        language,
        "#8b949e",
    )


# ============================================================
# Formatting
# ============================================================

def format_number(value):
    return f"{value:,}"


def xml_escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# ============================================================
# Main statistics collection
# ============================================================

repositories = get_all_accessible_public_repositories()

print()
print(
    f"Found {len(repositories)} "
    f"public repositories."
)
print()

total_commits = 0
total_additions = 0
total_deletions = 0

all_languages = {}


with tempfile.TemporaryDirectory() as temporary_directory:

    temporary_directory = Path(
        temporary_directory
    )

    for index, repo in enumerate(
        repositories,
        start=1,
    ):

        full_name = repo["full_name"]

        print(
            f"[{index}/{len(repositories)}] "
            f"{full_name}"
        )

        repo_path = (
            temporary_directory
            / f"repo-{repo['id']}"
        )

        # ----------------------------------------------------
        # Clone
        # ----------------------------------------------------

        try:
            clone_repository(
                repo,
                repo_path,
            )

        except subprocess.CalledProcessError as error:

            print(
                "  WARNING: clone failed; skipping."
            )

            if error.stderr:
                print(
                    error.stderr[-1000:]
                )

            continue

        # ----------------------------------------------------
        # Commits
        # ----------------------------------------------------

        try:

            commits = get_all_branch_commits(
                repo_path
            )

            commit_count = len(commits)

            total_commits += commit_count

            print(
                f"  Commits: {commit_count:,}"
            )

        except subprocess.CalledProcessError:

            print(
                "  WARNING: could not enumerate commits."
            )

        # ----------------------------------------------------
        # Additions / deletions
        # ----------------------------------------------------

        try:

            additions, deletions = (
                get_repository_line_stats(
                    repo_path
                )
            )

            total_additions += additions
            total_deletions += deletions

            print(
                f"  Lines: "
                f"+{additions:,} "
                f"-{deletions:,}"
            )

        except subprocess.CalledProcessError:

            print(
                "  WARNING: could not calculate "
                "line statistics."
            )

        # ----------------------------------------------------
        # Languages
        # ----------------------------------------------------

        try:

            languages = get_languages(repo)

            for language, byte_count in (
                languages.items()
            ):

                all_languages[language] = (
                    all_languages.get(
                        language,
                        0,
                    )
                    + byte_count
                )

        except Exception as error:

            print(
                f"  WARNING: language lookup failed: "
                f"{error}"
            )


# ============================================================
# Language processing
# ============================================================

total_language_bytes = sum(
    all_languages.values()
)

top_languages = sorted(
    all_languages.items(),
    key=lambda item: item[1],
    reverse=True,
)[:8]


# ============================================================
# Generate language rows
# ============================================================

language_rows = []

for index, (language, byte_count) in enumerate(
    top_languages
):

    percentage = (
        byte_count / total_language_bytes * 100
        if total_language_bytes
        else 0
    )

    y = 360 + index * 25

    language_rows.append(
        f"""
        <circle
            cx="35"
            cy="{y - 5}"
            r="5"
            fill="{language_color(language)}"
        />

        <text
            x="50"
            y="{y}"
            class="label"
        >
            {xml_escape(language)}
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


# ============================================================
# Generate SVG
# ============================================================

svg = f"""<svg
xmlns="http://www.w3.org/2000/svg"
width="760"
height="590"
viewBox="0 0 760 590">

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
    height="590"
    rx="12"
    fill="#0d1117"
/>

<!-- Header -->

<text
    x="30"
    y="40"
    class="title"
>
    GitHub Activity
</text>

<text
    x="30"
    y="62"
    class="subtitle"
>
    @{xml_escape(USERNAME)} · public repositories
    you can access
</text>


<!-- Main statistics -->

<text
    x="30"
    y="105"
    class="number"
>
    {format_number(total_commits)}
</text>

<text
    x="30"
    y="123"
    class="stat"
>
    COMMITS
</text>


<text
    x="180"
    y="105"
    class="number"
>
    +{format_number(total_additions)}
</text>

<text
    x="180"
    y="123"
    class="stat"
>
    ADDITIONS
</text>


<text
    x="365"
    y="105"
    class="number"
>
    -{format_number(total_deletions)}
</text>

<text
    x="365"
    y="123"
    class="stat"
>
    DELETIONS
</text>


<text
    x="555"
    y="105"
    class="number"
>
    {format_number(len(repositories))}
</text>

<text
    x="555"
    y="123"
    class="stat"
>
    REPOSITORIES
</text>


<!-- Divider -->

<line
    x1="30"
    y1="150"
    x2="730"
    y2="150"
    stroke="#21262d"
/>


<!-- Languages -->

<text
    x="30"
    y="185"
    class="title"
>
    Languages
</text>

<text
    x="30"
    y="207"
    class="subtitle"
>
    Combined across accessible public repositories
</text>

{''.join(language_rows)}


<!-- Footer -->

<line
    x1="30"
    y1="555"
    x2="730"
    y2="555"
    stroke="#21262d"
/>

<text
    x="30"
    y="578"
    class="subtitle"
>
    All branches · unique commits · public repositories only
</text>

</svg>
"""


# ============================================================
# Write output
# ============================================================

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


# ============================================================
# Console summary
# ============================================================

print()
print("=" * 64)
print("GitHub statistics generated")
print("=" * 64)
print(
    f"Repositories : {len(repositories):,}"
)
print(
    f"Commits      : {total_commits:,}"
)
print(
    f"Additions    : +{total_additions:,}"
)
print(
    f"Deletions    : -{total_deletions:,}"
)
print("=" * 64)