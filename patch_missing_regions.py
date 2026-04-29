#!/usr/bin/env python3
"""
Patch script for the 30 city pages with missing region/population data.

Fixes (per page):
  1.  <title>...Hidden Gems in </title>           -> ...in {Region}</title>
  2.  og:title  "...Discover Local "              -> "...Discover Local {Region}"
  3.  twitter:title "...Discover Local "          -> "...Discover Local {Region}"
  4.  JSON-LD WebPage.name "...Hidden Gems in "   -> "...Hidden Gems in {Region}"
  5.  JSON-LD AdministrativeArea.name ""          -> "{Region}"
  6.  hero-eyebrow pin with empty value           -> pin {Region}
  7.  hero-sub "...in {City}, ."                  -> "...in {City}, {Region}."
  8.  "...is live in {City} and across ."  (x2)   -> "...across {Region}."
  9.  "...actively exploring ." (x2)              -> "...actively exploring {Region}."
  10. <span class="stat-num"></span> next to Population -> <span class="stat-num">{pop}</span>

Usage:
    cd /path/to/roam-local-app-website
    python3 patch_missing_regions.py [--dry-run]

Flags:
    --dry-run    Print what would change without writing files.

Run without --dry-run to actually apply the changes. Always commit your
working tree first so you can `git diff` to review and revert if needed.
"""

import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

CITIES_DIR = Path("cities")

# Region for each broken slug. Population is set only for the three cities
# whose stat-num is empty (verified by audit).
PATCH_DATA = {
    "birmingham":     {"region": "West Midlands",      "population": "1,140,000"},
    "brighton":       {"region": "East Sussex",        "population": None},
    "cardiff":        {"region": "Wales",              "population": None},
    "coventry":       {"region": "West Midlands",      "population": None},
    "derry":          {"region": "County Londonderry", "population": None},
    "durham":         {"region": "County Durham",      "population": None},
    "edinburgh":      {"region": "Scotland",           "population": None},
    "glasgow":        {"region": "Scotland",           "population": None},
    "guildford":      {"region": "Surrey",             "population": None},
    "hay-on-wye":     {"region": "Powys",              "population": None},
    "inverness":      {"region": "Highland",           "population": None},
    "leeds":          {"region": "West Yorkshire",     "population": None},
    "leicester":      {"region": "Leicestershire",     "population": None},
    "liverpool":      {"region": "Merseyside",         "population": None},
    "london":         {"region": "Greater London",     "population": "8,900,000"},
    "ludlow":         {"region": "Shropshire",         "population": None},
    "manchester":     {"region": "Greater Manchester", "population": "568,000"},
    "newcastle":      {"region": "Tyne and Wear",      "population": None},
    "nottingham":     {"region": "Nottinghamshire",    "population": None},
    "oxford":         {"region": "Oxfordshire",        "population": None},
    "pitlochry":      {"region": "Perth and Kinross",  "population": None},
    "portsmouth":     {"region": "Hampshire",          "population": None},
    "sheffield":      {"region": "South Yorkshire",    "population": None},
    "southampton":    {"region": "Hampshire",          "population": None},
    "st-andrews":     {"region": "Fife",               "population": None},
    "st-ives":        {"region": "Cornwall",           "population": None},
    "stoke-on-trent": {"region": "Staffordshire",      "population": None},
    "totnes":         {"region": "Devon",              "population": None},
    "winchester":     {"region": "Hampshire",          "population": None},
    "windermere":     {"region": "Cumbria",            "population": None},
}


def patch_html(html, region, population):
    """
    Apply all region/population substitutions. Returns (new_html, applied_changes).

    Each substitution checks that the broken pattern is actually present
    before replacing it. This makes the script idempotent — re-running it
    on a fixed page is a no-op.
    """
    changes = []

    # 1. <title>...Hidden Gems in </title>
    new_html, n = re.subn(
        r"(Hidden Gems in)\s*</title>",
        rf"\1 {region}</title>",
        html,
        count=1,
    )
    if n:
        changes.append("title")
        html = new_html

    # 2. og:title "...Discover Local "
    new_html, n = re.subn(
        r'(og:title" content="Roam [^"]+ — Discover Local) "',
        rf'\1 {region}"',
        html,
        count=1,
    )
    if n:
        changes.append("og:title")
        html = new_html

    # 3. twitter:title "...Discover Local "
    new_html, n = re.subn(
        r'(twitter:title" content="Roam [^"]+ — Discover Local) "',
        rf'\1 {region}"',
        html,
        count=1,
    )
    if n:
        changes.append("twitter:title")
        html = new_html

    # 4. JSON-LD WebPage.name "...Hidden Gems in "
    new_html, n = re.subn(
        r'("name":"Roam [^"]+ &#8212; Discover Local Businesses and Hidden Gems in) "',
        rf'\1 {region}"',
        html,
        count=1,
    )
    if n:
        changes.append("schema.WebPage.name")
        html = new_html

    # 5. JSON-LD AdministrativeArea name ""
    new_html, n = re.subn(
        r'("@type":"AdministrativeArea","name":)""',
        rf'\1"{region}"',
        html,
        count=1,
    )
    if n:
        changes.append("schema.AdministrativeArea.name")
        html = new_html

    # 6. hero-eyebrow pin with empty value
    new_html, n = re.subn(
        r'(class="hero-eyebrow">&#x1F4CD;)\s*</div>',
        rf'\1 {region}</div>',
        html,
        count=1,
    )
    if n:
        changes.append("hero-eyebrow")
        html = new_html

    # 7. hero-sub "...in {City}, ." (catches the two known shapes)
    # Shape A: "...in {City}, . Download free..."
    # Shape B: "...in {City}, .</p>"
    new_html, n = re.subn(
        r"(in [A-Z][^,<>]+),\s*\.(\s*(?:Download free|</p>))",
        rf"\1, {region}.\2",
        html,
        count=1,
    )
    if n:
        changes.append("hero-sub")
        html = new_html

    # 8. "...is live in {City} and across ." (occurs twice: schema + visible HTML body)
    # Use re.sub (not subn count=1) so both instances are fixed.
    new_html, n = re.subn(
        r"(is live in [A-Z][^.<>\"]+ and across)\s*\.",
        rf"\1 {region}.",
        html,
    )
    if n:
        changes.append(f"is-live-in (x{n})")
        html = new_html

    # 9. "...actively exploring ." (occurs twice: schema + visible HTML body)
    new_html, n = re.subn(
        r"(actively exploring)\s*\.",
        rf"\1 {region}.",
        html,
    )
    if n:
        changes.append(f"actively-exploring (x{n})")
        html = new_html

    # 10. Population stat-num (only if a population value was provided)
    # Use a lambda for the replacement to avoid backreference collisions
    # when the population string contains digits (e.g. "8,900,000" → \18 collision).
    if population is not None:
        new_html, n = re.subn(
            r'(class="stat-num">)\s*(</span>\s*<span class="stat-label">Population)',
            lambda m: f'{m.group(1)}{population}{m.group(2)}',
            html,
            count=1,
        )
        if n:
            changes.append(f"population={population}")
            html = new_html

    return html, changes


def main():
    dry_run = "--dry-run" in sys.argv

    if not CITIES_DIR.exists():
        print(f"ERROR: {CITIES_DIR} not found. Run from repo root.")
        sys.exit(1)

    print(f"{'DRY RUN — ' if dry_run else ''}Patching {len(PATCH_DATA)} pages with missing region data\n")

    summary = []

    for slug, data in PATCH_DATA.items():
        path = CITIES_DIR / slug / "index.html"
        if not path.exists():
            print(f"  ⚠  {slug}: no index.html, skipping")
            summary.append((slug, "MISSING_FILE", []))
            continue

        original = path.read_text(encoding="utf-8")
        patched, changes = patch_html(original, data["region"], data["population"])

        if not changes:
            print(f"  •  {slug:18s} no changes (already clean?)")
            summary.append((slug, "NO_CHANGES", []))
            continue

        print(f"  ✓  {slug:18s} -> {data['region']:22s} [{', '.join(changes)}]")
        summary.append((slug, "PATCHED", changes))

        if not dry_run:
            path.write_text(patched, encoding="utf-8")

    # Summary
    patched_count = sum(1 for _, status, _ in summary if status == "PATCHED")
    no_change_count = sum(1 for _, status, _ in summary if status == "NO_CHANGES")
    missing_count = sum(1 for _, status, _ in summary if status == "MISSING_FILE")

    print()
    print("=" * 60)
    print(f"{'WOULD PATCH' if dry_run else 'PATCHED'}: {patched_count} pages")
    if no_change_count:
        print(f"NO CHANGES NEEDED: {no_change_count} pages")
    if missing_count:
        print(f"MISSING FILES:     {missing_count} pages")
    print("=" * 60)

    if dry_run:
        print("\nThis was a dry run. No files were written.")
        print("Run without --dry-run to apply changes.")
    else:
        print("\nDone. Recommended next steps:")
        print("  1. Spot-check a couple of pages: e.g. open cities/london/index.html")
        print("  2. Re-run audit_missing_data.py — should report 0 issues")
        print("  3. git diff to review")


if __name__ == "__main__":
    main()
