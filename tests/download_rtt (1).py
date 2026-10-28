"""Download monthly RTT 'Full CSV data file' ZIPs from NHS England year pages.

Only months between START and END (inclusive) are downloaded.

Usage (from the project root):
    pip install requests beautifulsoup4
    python src/pipeline/download_rtt.py

Downloads into data/raw/, extracts the CSVs, and appends each file
to data/SOURCES.md.
"""
import re
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup # type: ignore

BASE = "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/"
YEAR_PAGES = [
    BASE + "rtt-data-2026-27/",   # Apr 2026 onwards
    BASE + "rtt-data-2025-26/",   # Apr 2025 - Mar 2026
]
START = (2025, 9)   # Sep 2025
END = (2026, 8)     # Aug 2026

RAW = Path("data/raw")
SOURCES = Path("data/SOURCES.md")
HEADERS = {"User-Agent": "Mozilla/5.0 (student capstone project)"}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def month_of(filename: str):
    """'Full-CSV-data-file-Aug26-ZIP-3M-xxxx.zip' -> (2026, 8), else None."""
    m = re.search(r"data-file-([A-Za-z]{3})(\d{2})", filename)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    return 2000 + int(m.group(2)), MONTHS[m.group(1).lower()]


def zip_links(page_url: str) -> list[str]:
    html = requests.get(page_url, headers=HEADERS, timeout=60).text
    soup = BeautifulSoup(html, "html.parser")
    links = {
        urljoin(page_url, a["href"])
        for a in soup.find_all("a", href=True)
        if a["href"].lower().endswith(".zip") and "csv" in a["href"].lower()
    }
    return sorted(links)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    got = set()
    for page in YEAR_PAGES:
        print(f"\nPage: {page}")
        for url in zip_links(page):
            name = url.rsplit("/", 1)[-1]
            ym = month_of(name)
            if ym is None or not (START <= ym <= END):
                continue
            got.add(ym)
            target = RAW / name
            if target.exists():
                print(f"  skip (already have) {name}")
                continue
            print(f"  downloading {name}")
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            target.write_bytes(r.content)
            with zipfile.ZipFile(target) as z:
                z.extractall(RAW)
            with SOURCES.open("a", encoding="utf-8") as f:
                f.write(f"| RTT full extract {ym[0]}-{ym[1]:02d} | NHS England | {page} | {url} | {date.today()} | |\n")

    print(f"\nMonths found: {len(got)} -> {sorted(got)}")
    if len(got) < 12:
        print("WARNING: fewer than 12 months found - check the year pages manually.")
    print("Now run build_master.py")


if __name__ == "__main__":
    main()
