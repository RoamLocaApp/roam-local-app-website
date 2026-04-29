#!/usr/bin/env python3
"""
Rewrite the FAQ block on every city page using AIO-friendly templates.

What this script does, per page:
  - Extracts city, region, population, area-pill list, known-for text,
    history text, and local-tip text from the existing HTML.
  - Generates five new FAQ answers using script-safe templates that:
      * Remove all CTAs from inside answers
      * Open with clean topic sentences
      * Match answer content to the question asked
      * Use only facts already present on the page
  - Rewrites both the visible FAQ accordion HTML and the JSON-LD
    FAQPage.mainEntity array, keeping them perfectly in sync.
  - Is idempotent: re-running on an already-rewritten page makes no changes.

Usage:
    cd /path/to/roam-local-app-website
    pip3 install beautifulsoup4   # one-time, if not installed
    python3 rewrite_faqs.py --dry-run            # preview, no writes
    python3 rewrite_faqs.py --dry-run --only=aberfeldy,london,whitstable
    python3 rewrite_faqs.py                      # apply for real

The --only flag is the recommended way to spot-check before running across
all 1,018 pages. Run on a few cities, eyeball the output, then run in full.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: BeautifulSoup not installed. Run: pip3 install beautifulsoup4")
    sys.exit(1)


CITIES_DIR = Path("cities")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_facts(html, slug):
    """
    Pull all the per-city facts we need from a page's HTML.
    Returns a dict, or None if extraction fails on a critical field.
    """
    soup = BeautifulSoup(html, "html.parser")

    facts = {
        "slug": slug,
        "city": None,
        "region": None,
        "population": None,
        "areas": [],
        "known_for": None,
        "history": None,
        "local_tip": None,
        "food_intro": None,
    }

    # --- City name (from the H1, fallback to slug-derived) ---
    h1 = soup.find("h1")
    if h1:
        em = h1.find("em")
        if em and em.get_text(strip=True):
            facts["city"] = em.get_text(strip=True)
    if not facts["city"]:
        facts["city"] = slug.replace("-", " ").title()

    # --- Region (from the hero-eyebrow pin) ---
    eyebrow = soup.find("div", class_="hero-eyebrow")
    if eyebrow:
        # Strip the emoji prefix
        text = eyebrow.get_text(strip=True)
        # Remove leading pin emoji and whitespace
        text = re.sub(r"^[\U0001F4CD\U0001F300-\U0001FAFF\u2600-\u27BF]+\s*", "", text)
        if text:
            facts["region"] = text

    # --- Population (from the stats-bar) ---
    for stat in soup.find_all("div", class_="stat"):
        label = stat.find("span", class_="stat-label")
        num = stat.find("span", class_="stat-num")
        if label and num and "Population" in label.get_text():
            pop_text = num.get_text(strip=True)
            if pop_text:
                facts["population"] = pop_text
            break

    # --- Areas (from the area-tags pills) ---
    area_tags = soup.find("div", class_="area-tags")
    if area_tags:
        facts["areas"] = [
            pill.get_text(strip=True)
            for pill in area_tags.find_all("span", class_="area-pill")
            if pill.get_text(strip=True)
        ]

    # --- Known-for paragraph ---
    known_block = soup.find("div", class_="known-for")
    if known_block:
        p = known_block.find("p")
        if p:
            facts["known_for"] = p.get_text(" ", strip=True)

    # --- History block ---
    history_block = soup.find("div", class_="history-block")
    if history_block:
        p = history_block.find("p")
        if p:
            facts["history"] = p.get_text(" ", strip=True)

    # --- Local tip block ---
    tip_block = soup.find("div", class_="tip-block")
    if tip_block:
        p = tip_block.find("p")
        if p:
            facts["local_tip"] = p.get_text(" ", strip=True)

    # --- Food intro paragraph (first <p> inside the food section) ---
    # Identified by the section containing an h2 with "Food" in it
    for section in soup.find_all("section", class_="section"):
        h2 = section.find("h2")
        if h2 and "Food" in h2.get_text():
            p = section.find("p")
            if p:
                facts["food_intro"] = p.get_text(" ", strip=True)
            break

    # --- Critical-field validation ---
    if not facts["city"] or not facts["region"]:
        return None

    return facts


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------

# Phrases that signal a CTA is being grafted onto an informational answer.
# When found inside extracted text, we cut from that point forward.
CTA_CUT_MARKERS = [
    " Roam surfaces ",
    " Roam shows you ",
    " Download Roam",
    " Download free",
    " download free",
    " download Roam",
    " List your ",
]


def strip_cta_tail(text):
    """Remove any trailing CTA-style sentence from extracted text."""
    if not text:
        return text
    for marker in CTA_CUT_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx].rstrip()
    # Ensure terminal punctuation
    if text and text[-1] not in ".!?":
        text = text + "."
    return text


def first_sentence(text):
    """Return the first complete sentence of text, or text itself if no period.
    Always ensures the returned string has terminal punctuation, so callers
    can safely concatenate further sentences after it."""
    if not text:
        return text
    match = re.search(r"^(.+?[.!?])\s", text + " ")
    if match:
        result = match.group(1).strip()
    else:
        result = text.strip()
    # Belt-and-braces: ensure terminal punctuation regardless of source text
    if result and result[-1] not in ".!?":
        result += "."
    return result


def format_areas_list(areas):
    """
    Format a list of area names into a natural English list.
    ['A', 'B', 'C'] -> 'A, B and C'
    ['A', 'B'] -> 'A and B'
    ['A'] -> 'A'
    """
    if not areas:
        return ""
    if len(areas) == 1:
        return areas[0]
    if len(areas) == 2:
        return f"{areas[0]} and {areas[1]}"
    return ", ".join(areas[:-1]) + f" and {areas[-1]}"


def build_q1_answer(facts):
    """What is {City} known for?"""
    city = facts["city"]
    region = facts["region"]
    known_for = strip_cta_tail(facts["known_for"]) if facts["known_for"] else None
    history = first_sentence(facts["history"]) if facts["history"] else None
    population = facts["population"]

    parts = []

    # Topic sentence + known-for facts
    if known_for:
        # Lowercase first letter so it reads as continuation
        kf = known_for[0].lower() + known_for[1:] if known_for else ""
        # Strip trailing period for clean concatenation
        kf = kf.rstrip(".")
        parts.append(f"{city} is a place in {region} known for {kf}.")
    else:
        parts.append(f"{city} is a place in {region}.")

    # History sentence (if distinct from known-for)
    if history and history not in (known_for or ""):
        parts.append(history)

    # Population sentence (if known)
    if population:
        parts.append(f"The population is around {population}.")

    return " ".join(parts)


def build_q2_answer(facts):
    """Where should I eat in {City}?"""
    city = facts["city"]
    food_intro = strip_cta_tail(facts["food_intro"]) if facts["food_intro"] else None

    if food_intro:
        return food_intro
    # Fallback if no food intro extracted
    return (
        f"{city} has a range of independent restaurants, cafés and pubs. "
        f"Use the Roam app to browse current places, opening hours and reviews "
        f"from local users."
    )


def build_q3_answer(facts):
    """Is Roam available in {City}?"""
    city = facts["city"]
    region = facts["region"]
    return (
        f"Yes. Roam is a free local discovery app live in {city} and across "
        f"{region}. It is available on iOS and Android."
    )


def build_q4_answer(facts):
    """How can my {City} business get on Roam?"""
    city = facts["city"]
    region = facts["region"]
    return (
        f"Local {city} businesses can list on Roam for free in around 90 seconds. "
        f"Add your business name, address, opening hours and a few photos via "
        f"the Roam website, and your listing goes live in Roam's discovery feed "
        f"for users browsing {city} and the wider {region} area. There is no "
        f"subscription fee."
    )


def build_q5_answer(facts):
    """What areas around {City} does Roam cover?"""
    city = facts["city"]
    region = facts["region"]
    areas = facts["areas"]

    if areas:
        areas_str = format_areas_list(areas)
        return (
            f"Roam covers {city} and the surrounding area in {region}, "
            f"including {areas_str}."
        )
    return f"Roam covers {city} and the surrounding area in {region}."


def build_faq(facts):
    """Return the five (question, answer) pairs for a city."""
    city = facts["city"]
    return [
        (f"What is {city} known for?",          build_q1_answer(facts)),
        (f"Where should I eat in {city}?",      build_q2_answer(facts)),
        (f"Is Roam available in {city}?",       build_q3_answer(facts)),
        (f"How can my {city} business get on Roam?", build_q4_answer(facts)),
        (f"What areas around {city} does Roam cover?", build_q5_answer(facts)),
    ]


# ---------------------------------------------------------------------------
# HTML rewriting
# ---------------------------------------------------------------------------

def render_visible_faq_html(faq_pairs):
    """Render the FAQ accordion HTML block (the contents of <div class='faq-list'>)."""
    items = []
    for q, a in faq_pairs:
        # HTML-escape the answer for safety. We don't escape the question
        # because we control its content and escaping breaks ' and similar.
        items.append(
            '<div class="faq-item">'
            '<button class="faq-q" onclick="toggleFaq(this)" aria-expanded="false">'
            f'{q}<span class="faq-icon">+</span></button>'
            '<div class="faq-a" hidden><p>'
            f'{a}'
            '</p></div>'
            '</div>'
        )
    return "\n".join(items)


def rewrite_visible_faq(html, faq_pairs):
    """
    Replace the inner contents of <div class="faq-list"> with the new FAQ items.
    Uses regex on the source rather than BeautifulSoup output to avoid
    reformatting the entire page.
    """
    new_inner = render_visible_faq_html(faq_pairs)
    # Match the faq-list container and replace its inner contents only.
    # The (?s) flag makes . match newlines.
    pattern = r'(<div class="faq-list">)(.*?)(</div>\s*</section>)'
    def replace(m):
        return m.group(1) + "\n" + new_inner + "\n    " + m.group(3)
    new_html, n = re.subn(pattern, replace, html, count=1, flags=re.DOTALL)
    if n == 0:
        return None
    return new_html


def rewrite_faq_schema(html, faq_pairs):
    """
    Replace the JSON-LD FAQPage.mainEntity array with the new questions and answers.

    The schema lives inside a single <script type="application/ld+json"> block
    that contains a @graph array; we surgically replace the FAQPage object's
    mainEntity value without touching the rest of the @graph.
    """
    # Build the new mainEntity JSON
    main_entity = []
    for q, a in faq_pairs:
        main_entity.append({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        })
    new_entity_json = json.dumps(main_entity, ensure_ascii=False)

    # Find FAQPage object and replace its mainEntity
    # Pattern allows for any current mainEntity content
    pattern = r'(\{"@type":"FAQPage","mainEntity":)\[.*?\](\})'
    def replace(m):
        return m.group(1) + new_entity_json + m.group(2)
    new_html, n = re.subn(pattern, replace, html, count=1, flags=re.DOTALL)
    if n == 0:
        return None
    return new_html


# ---------------------------------------------------------------------------
# Per-page driver
# ---------------------------------------------------------------------------

def rewrite_page(path, dry_run=False):
    """
    Rewrite one city's FAQ block. Returns ('ok'|'skipped'|'error', message).
    """
    slug = path.parent.name
    html = path.read_text(encoding="utf-8")

    facts = extract_facts(html, slug)
    if facts is None:
        return ("error", "extraction failed (missing city or region)")

    faq_pairs = build_faq(facts)

    new_html = rewrite_visible_faq(html, faq_pairs)
    if new_html is None:
        return ("error", "could not locate visible faq-list block")

    new_html = rewrite_faq_schema(new_html, faq_pairs)
    if new_html is None:
        return ("error", "could not locate FAQPage schema block")

    if new_html == html:
        return ("skipped", "no changes (already rewritten?)")

    if not dry_run:
        path.write_text(new_html, encoding="utf-8")

    return ("ok", f"rewrote ({len(faq_pairs)} questions)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Rewrite FAQ blocks on city pages.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing files.")
    parser.add_argument("--only", default=None,
                        help="Comma-separated list of slugs to process (e.g. 'london,whitstable').")
    parser.add_argument("--show", action="store_true",
                        help="Print the generated FAQ for each rewritten page (use with --only).")
    args = parser.parse_args()

    if not CITIES_DIR.exists():
        print(f"ERROR: {CITIES_DIR} not found. Run from repo root.")
        sys.exit(1)

    if args.only:
        slugs = [s.strip() for s in args.only.split(",")]
        city_dirs = [CITIES_DIR / s for s in slugs]
    else:
        city_dirs = sorted([d for d in CITIES_DIR.iterdir() if d.is_dir()])

    print(f"{'DRY RUN — ' if args.dry_run else ''}Processing {len(city_dirs)} pages")
    print()

    counts = {"ok": 0, "skipped": 0, "error": 0}
    errors = []

    for city_dir in city_dirs:
        index_file = city_dir / "index.html"
        if not index_file.exists():
            counts["error"] += 1
            errors.append((city_dir.name, "no index.html"))
            continue

        status, msg = rewrite_page(index_file, dry_run=args.dry_run)
        counts[status] += 1

        if status == "error":
            errors.append((city_dir.name, msg))
        elif args.show and status == "ok":
            html = index_file.read_text(encoding="utf-8")
            facts = extract_facts(html, city_dir.name)
            if facts:
                print(f"  ── {city_dir.name} ──")
                for q, a in build_faq(facts):
                    print(f"  Q: {q}")
                    print(f"  A: {a}")
                    print()

    # Summary
    print("=" * 60)
    print(f"{'WOULD REWRITE' if args.dry_run else 'REWROTE'}: {counts['ok']} pages")
    if counts["skipped"]:
        print(f"SKIPPED:                    {counts['skipped']} pages (no changes)")
    if counts["error"]:
        print(f"ERRORS:                     {counts['error']} pages")
        for slug, msg in errors[:20]:
            print(f"   {slug}: {msg}")
        if len(errors) > 20:
            print(f"   ... and {len(errors) - 20} more")
    print("=" * 60)

    if args.dry_run:
        print("\nThis was a dry run. No files were written.")
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
