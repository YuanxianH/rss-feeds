#!/usr/bin/env python3
"""Analyze a webpage's HTML structure to find CSS selectors for RSS feed generation."""

import sys
import requests
from bs4 import BeautifulSoup
from collections import Counter

def analyze(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    print(f"Status: {resp.status_code}, Content length: {len(resp.text)}")

    # Find repeated container elements (likely list items)
    tag_class_counts = Counter()
    for tag in soup.find_all(True):
        classes = tag.get("class", [])
        key = f"{tag.name}" + (f".{'.'.join(classes)}" if classes else "")
        tag_class_counts[key] += 1

    print("\n=== Repeated elements (potential item containers) ===")
    for key, count in tag_class_counts.most_common(30):
        if count >= 3 and count <= 200:
            print(f"  {key}: {count}")

    # Show first few articles/items
    for selector in ["article", "li", "div.card", "div.post", "div.item"]:
        items = soup.select(selector)
        if 3 <= len(items) <= 200:
            print(f"\n=== First item for '{selector}' ({len(items)} total) ===")
            print(items[0].prettify()[:1500])
            break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_page.py <url>")
        sys.exit(1)
    analyze(sys.argv[1])
