#!/usr/bin/env python3
"""
Audit script for Roam city pages.

Scans every cities/<slug>/index.html and flags pages with missing data:
  - Missing region (the "Kent", "Perth and Kinross" etc. value)
  - Missing population number
  - Missing villages/areas list
  - Empty schema fields

Usage:
    cd /path/to/roam-local-app-website
    python3 audit_missing_data.py

Output: prints a summary + writes audit_results.csv with per-page findings.
"""

import os
import re
import csv
import sys
from pathlib import Path


CITIES_DIR = Path("cities")
OUTPUT_CSV = Path("audit_results.csv")


def extract_slot(html: str, label: str) -> str:
    """Try several patterns to pull a value out of the HTML."""
    return ""


def audit_page(path: Path) -> dict:
    """Return a dict of findings for a single city HTML file."""
    html = path.read_text(encoding="utf-8", errors="replace")
    slug = path.parent.name

    findings = {
        "slug": slug,
        "path": str(path),
        "missing_region_title": False,
        "missing_region_eyebrow": False,
        "missing_region_about": False,
        "missing_region_schema": False,
        "missing_population": False,
        "missing_villages": False,
        "issues": [],
    }

    # 1. Missing region in <title> — pattern "Hidden Gems in </title>"
    if re.search(r"Hidden Gems in\s*</title>", html):
        findings["missing_region_title"] = True
        findings["issues"].append("title_empty_region")

    # 2. Missing region in hero-eyebrow pill — pattern '<div class="hero-eyebrow">📍 </div>'
    # The emoji is HTML-encoded as &#x1F4CD;
    if re.search(r'class="hero-eyebrow">[^<]*&#x1F4CD;\s*</div>', html):
        findings["missing_region_eyebrow"] = True
        findings["issues"].append("eyebrow_empty_region")

    # 3. Missing region in hero-sub — pattern "in <CityName>, ."
    # i.e. comma followed by space + period meaning empty region was interpolated
    if re.search(r",\s*\.\s*Download free", html) or re.search(r",\s*\.</p>", html):
        findings["missing_region_about"] = True
        findings["issues"].append("hero_sub_empty_region")

    # 4. Missing region in "Roam is live in X and across ." sentence
    # Catches both the JSON-LD version ("and across .") and the visible HTML body version
    if re.search(r"and across\s*\.\s*(Download|</p>|\")", html):
        findings["missing_region_schema"] = True
        findings["issues"].append("schema_empty_region")

    # 5. Missing population — pattern '<span class="stat-num"></span><span class="stat-label">Population</span>'
    if re.search(r'class="stat-num">\s*</span>\s*<span class="stat-label">Population', html):
        findings["missing_population"] = True
        findings["issues"].append("population_empty")

    # 6. Missing villages/areas — area-tags div with no area-pill children
    area_tags_match = re.search(r'<div class="area-tags">(.*?)</div>', html, re.DOTALL)
    if area_tags_match:
        if 'class="area-pill"' not in area_tags_match.group(1):
            findings["missing_villages"] = True
            findings["issues"].append("villages_empty")
    else:
        findings["missing_villages"] = True
        findings["issues"].append("villages_block_missing")

    return findings


def main():
    if not CITIES_DIR.exists():
        print(f"ERROR: {CITIES_DIR} not found. Run this script from the repo root.")
        sys.exit(1)

    city_dirs = sorted([d for d in CITIES_DIR.iterdir() if d.is_dir()])
    total = len(city_dirs)
    print(f"Auditing {total} city pages...\n")

    all_findings = []
    issue_counts = {
        "title_empty_region": 0,
        "eyebrow_empty_region": 0,
        "hero_sub_empty_region": 0,
        "schema_empty_region": 0,
        "population_empty": 0,
        "villages_empty": 0,
        "villages_block_missing": 0,
    }
    pages_with_any_issue = 0

    for city_dir in city_dirs:
        index_file = city_dir / "index.html"
        if not index_file.exists():
            print(f"  ⚠  {city_dir.name}: no index.html")
            continue

        findings = audit_page(index_file)
        all_findings.append(findings)

        if findings["issues"]:
            pages_with_any_issue += 1
            for issue in findings["issues"]:
                if issue in issue_counts:
                    issue_counts[issue] += 1

    # Summary
    print("=" * 60)
    print(f"AUDIT SUMMARY ({total} pages scanned)")
    print("=" * 60)
    print(f"Pages with at least one issue: {pages_with_any_issue}")
    print()
    print("Issue breakdown:")
    for issue, count in issue_counts.items():
        if count > 0:
            print(f"  {issue:30s} {count:5d} pages")
    print()

    # Show first 20 broken pages
    broken = [f for f in all_findings if f["issues"]]
    if broken:
        print(f"First 20 pages with issues (of {len(broken)} total):")
        for f in broken[:20]:
            print(f"  {f['slug']:30s} {', '.join(f['issues'])}")
        if len(broken) > 20:
            print(f"  ... and {len(broken) - 20} more (see {OUTPUT_CSV})")

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "slug",
            "issues",
            "missing_region_title",
            "missing_region_eyebrow",
            "missing_region_hero_sub",
            "missing_region_schema",
            "missing_population",
            "missing_villages",
        ])
        for finding in all_findings:
            writer.writerow([
                finding["slug"],
                "; ".join(finding["issues"]),
                finding["missing_region_title"],
                finding["missing_region_eyebrow"],
                finding["missing_region_about"],
                finding["missing_region_schema"],
                finding["missing_population"],
                finding["missing_villages"],
            ])

    print(f"\nFull results written to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
