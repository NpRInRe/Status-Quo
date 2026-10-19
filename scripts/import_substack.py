#!/usr/bin/env python3
"""
scripts/import_substack.py
Substack Newsletter Archive & Live RSS Feed Importer.
Supports:
1. Local exported CSV or folder (posts.csv)
2. Direct live Substack publication RSS feed (e.g. https://statusquotoday.substack.com/feed)
Maps excerpts to policy frameworks and outputs assets/newsletter_excerpts.json.
"""

import os
import sys
import csv
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

def clean_html(raw_html):
    """Strips HTML tags to extract clean prose text."""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = re.sub(r"&[a-z]+;|&#\d+;", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

def chunk_text(text, max_words=100):
    """Splits an article into readable paragraphs/chunks."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current_chunk = []
    current_count = 0
    
    for p in paragraphs:
        words = p.split()
        if current_count + len(words) > max_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = words
            current_count = len(words)
        else:
            current_chunk.extend(words)
            current_count += len(words)
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def load_framework_keywords(frameworks_graph_path):
    framework_keywords = {}
    if frameworks_graph_path and Path(frameworks_graph_path).exists():
        with open(frameworks_graph_path, "r", encoding="utf-8") as f:
            gdata = json.load(f)
            for node in gdata.get("nodes", []):
                framework_keywords[node["id"]] = [
                    node["id"].replace("-", " ").lower(),
                    node["title"].lower()
                ]
    # Add domain terms
    if "goodharts-law" in framework_keywords:
        framework_keywords["goodharts-law"].extend(["metric", "target", "measure", "gaming"])
    if "regulatory-capture" in framework_keywords:
        framework_keywords["regulatory-capture"].extend(["regulator", "corporate interest", "lobbying", "revolving door"])
    if "subsidiarity" in framework_keywords:
        framework_keywords["subsidiarity"].extend(["decentralized", "local authority", "jurisdiction"])
    return framework_keywords

def match_frameworks(text, framework_keywords):
    matched = set()
    t_lower = text.lower()
    for fid, kw_list in framework_keywords.items():
        if any(kw in t_lower for kw in kw_list):
            matched.add(fid)
    # Default fallback associations for privacy/data/policy posts
    if any(w in t_lower for w in ["privacy", "facial scan", "digiyatra", "aadhaar", "surveillance", "data"]):
        matched.add("regulatory-capture")
        matched.add("goodharts-law")
        matched.add("subsidiarity")
    return list(matched)

def parse_from_xml(xml_content, framework_keywords):
    root = ET.fromstring(xml_content)
    channel = root.find("channel")
    if channel is None:
        return []
    
    pub_title = channel.findtext("title") or "Status Quo"
    default_author = channel.findtext("copyright") or "Neeraj Paulose Raj"
    
    posts = []
    for item in channel.findall("item"):
        title = item.findtext("title") or "Untitled Post"
        link = item.findtext("link") or "#"
        pub_date = item.findtext("pubDate") or ""
        desc = item.findtext("description") or ""
        
        # Substack stores full body in <content:encoded>
        content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        raw_body = content_el.text if content_el is not None else desc
        clean_body = clean_html(raw_body)
        
        # Filter out short placeholder "Coming soon"
        if len(clean_body) < 100:
            continue
            
        chunks = chunk_text(clean_body)
        matched_fws = match_frameworks(clean_body, framework_keywords)
        
        posts.append({
            "title": title,
            "publication": pub_title,
            "author": default_author,
            "date": pub_date,
            "url": link,
            "description": desc,
            "excerpt": chunks[3] if len(chunks) > 3 else (chunks[0] if chunks else clean_body[:250]),
            "all_chunks": chunks[:5],
            "matched_frameworks": matched_fws
        })
        
    return posts

def fetch_from_rss(feed_url, framework_keywords):
    print(f"Fetching live RSS feed: {feed_url}...")
    req = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req) as resp:
        xml_content = resp.read()
    return parse_from_xml(xml_content, framework_keywords)

def process_substack(source=None, frameworks_graph_path=None):
    if frameworks_graph_path is None:
        frameworks_graph_path = ASSETS_DIR / "graph.json"
    framework_keywords = load_framework_keywords(frameworks_graph_path)
    posts = []
    
    # Check if local xml file
    if source and Path(source).exists():
        src_path = Path(source)
        if src_path.suffix in [".xml", ".rss", ".md"]:
            content = src_path.read_text(encoding="utf-8")
            # Remove any markdown header if present
            if "<?xml" in content:
                content = content[content.find("<?xml"):]
            posts = parse_from_xml(content, framework_keywords)
        elif src_path.suffix == ".csv" or (src_path / "posts.csv").exists():
            csv_file = src_path if src_path.suffix == ".csv" else (src_path / "posts.csv")
            with open(csv_file, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = row.get("title") or "Untitled Post"
                    body = row.get("body_html") or row.get("content") or ""
                    clean_b = clean_html(body)
                    chunks = chunk_text(clean_b)
                    matched_fws = match_frameworks(clean_b, framework_keywords)
                    posts.append({
                        "title": title,
                        "publication": "Status Quo",
                        "author": row.get("author") or "NPR",
                        "date": row.get("post_date") or "",
                        "url": row.get("canonical_url") or "#",
                        "excerpt": chunks[0] if chunks else clean_b[:200],
                        "matched_frameworks": matched_fws
                    })
    elif source and (source.startswith("http://") or source.startswith("https://")):
        feed_url = source if source.endswith("/feed") else source.rstrip("/") + "/feed"
        try:
            posts = fetch_from_rss(feed_url, framework_keywords)
        except Exception as e:
            print(f"Error fetching RSS from {feed_url}: {e}")
                    
    # Default fallback to Status Quo live feed
    if not posts:
        try:
            posts = fetch_from_rss("https://statusquotoday.substack.com/feed", framework_keywords)
        except Exception as e:
            print("Fallback to local cached item:", e)
            posts = [{
                "title": "Of Faces, Flights and Forgotten IDs",
                "publication": "Status Quo",
                "author": "Neeraj Paulose Raj",
                "date": "Sat, 30 May 2026",
                "url": "https://statusquotoday.substack.com/p/of-faces-flights-and-forgotten-ids",
                "description": "On eleven years, a facial scan, and the privacy we may have given away without noticing",
                "excerpt": "That moment gave me an annoying itch to pontificate about the evolution of data and how the internet has reshaped our understanding of privacy in ways we barely notice until they are already upon us... Somewhere in that silence between the question and its disappearance lies everything I intend to find out: how the law has scrambled to keep up, how a largely internet-illiterate country quietly surrendered what it never knew it had, what convenience has cost us in ways we are only beginning to count.",
                "matched_frameworks": ["regulatory-capture", "goodharts-law", "subsidiarity"]
            }]
            
    out_path = ASSETS_DIR / "newsletter_excerpts.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2)
    print(f"Successfully wrote {len(posts)} newsletter articles to {out_path}")

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "https://statusquotoday.substack.com/feed"
    process_substack(src)
