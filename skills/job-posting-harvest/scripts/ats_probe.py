#!/usr/bin/env python3
"""Classify the ATS behind each careers-page URL (curl-based, no browser).

Usage:
  python ats_probe.py "Name|url" "Name|url" ...
Example:
  python ats_probe.py "US Bank|https://careers.usbank.com/" "SoFi|https://sofi.com/careers"

Output: one line per company — ATS fingerprints found + Workday host/tenant
candidates extracted from HTML. Dated info: re-run before relying on it.
"""
import re
import subprocess
import sys
import time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def get(url: str, timeout: int = 16) -> tuple[str, str]:
    cmd = ["curl", "-sL", "--max-time", str(timeout),
           "-H", "User-Agent: " + UA, "-H", "Accept: text/html", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 8)
    return str(r.returncode), r.stdout


def classify(html: str) -> tuple[set, list, list]:
    ats = set()
    if re.search(r"boards-api\.greenhouse\.io|boards\.greenhouse\.io", html):
        ats.add("greenhouse")
    if re.search(r"myworkdayjobs\.com|workday\.com", html):
        ats.add("workday")
    if re.search(r"api\.phenom\.io|phenom\.io|phenom", html, re.I):
        ats.add("phenom")
    if re.search(r"workable\.com", html):
        ats.add("workable")
    if re.search(r"jobmatch\.jpmorganchase", html):
        ats.add("jpmc_jobmatch")
    if re.search(r"lever\.co", html):
        ats.add("lever")
    if re.search(r"ashbyhq\.com", html):
        ats.add("ashby")
    if re.search(r"successfactors\.com", html):
        ats.add("successfactors")
    if re.search(r"careers\.tal\.net", html):
        ats.add("talnet")
    if re.search(r"icims\.com", html):
        ats.add("icims")
    wd = list(dict.fromkeys(re.findall(r"([a-z0-9\-]+\.wd\d+\.myworkdayjobs\.com/[^\"'/?#\s]+)", html)))[:4]
    gh = list(dict.fromkeys(re.findall(r"boards?[-.]?api?\.greenhouse\.io/[a-z]+/boards/([a-z0-9\-]+)", html)))[:3]
    return ats, wd, gh


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    for spec in sys.argv[1:]:
        name, _, url = spec.partition("|")
        if not url:
            print(f"{name:14} BAD SPEC (want Name|url)")
            continue
        rc, html = get(url)
        ats, wd, gh = classify(html)
        print(f"{name:14} curl_rc={rc} len={len(html):7} ats={sorted(ats) or '-'} wd={wd or '-'} gh={gh or '-'}")
        time.sleep(0.4)


if __name__ == "__main__":
    main()
