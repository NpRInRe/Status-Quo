#!/usr/bin/env python3
"""
build_graph.py
Scans Quarto .qmd framework files, extracts front matter and [[wikilinks]],
computes graph nodes/edges, resolves backlinks, and writes:
1. assets/graph.json
2. Injects backlinks, typed relations, and local interactive graph blocks.
"""

import os
import re
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
CATEGORIES = ["law", "policy", "economics", "society"]

def parse_simple_yaml(yaml_text):
    """Zero-dependency parser for .qmd YAML frontmatter."""
    data = {}
    lines = yaml_text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        
        # Check list of dicts: 'related:'
        match_key = re.match(r"^([a-zA-Z0-9_\-]+)\s*:\s*(.*)$", line)
        if match_key:
            key = match_key.group(1).strip()
            val = match_key.group(2).strip()
            
            if key == "related" and not val:
                related_list = []
                i += 1
                curr_item = {}
                while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("    ") or not lines[i].strip()):
                    subline = lines[i].strip()
                    if subline.startswith("- "):
                        if curr_item:
                            related_list.append(curr_item)
                            curr_item = {}
                        subline = subline[2:].strip()
                        m_sub = re.match(r"^([a-zA-Z0-9_\-]+)\s*:\s*[\"']?(.*?)[\"']?$", subline)
                        if m_sub:
                            curr_item[m_sub.group(1)] = m_sub.group(2)
                    elif subline and ":" in subline:
                        m_sub = re.match(r"^([a-zA-Z0-9_\-]+)\s*:\s*[\"']?(.*?)[\"']?$", subline)
                        if m_sub:
                            curr_item[m_sub.group(1)] = m_sub.group(2)
                    i += 1
                if curr_item:
                    related_list.append(curr_item)
                data["related"] = related_list
                continue
            
            # List format: categories: ["Economics", "Law"] or categories: [Economics, Law]
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                data[key] = items
            elif val.lower() in ("true", "false"):
                data[key] = (val.lower() == "true")
            elif (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                data[key] = val[1:-1]
            else:
                data[key] = val
        i += 1
    return data

def extract_wikilinks(text):
    """Extracts [[target-id]] or [[target-id|Label]] wikilinks."""
    pattern = r"\[\[([a-zA-Z0-9_\-]+)(?:\|([^\]]+))?\]\]"
    return re.findall(pattern, text)

def scan_frameworks():
    frameworks = {}
    
    for cat in CATEGORIES:
        cat_dir = BASE_DIR / cat
        if not cat_dir.exists():
            continue
        for qmd_path in cat_dir.glob("*.qmd"):
            if qmd_path.name == "index.qmd":
                continue
            
            content = qmd_path.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
            if not fm_match:
                continue
            
            fm_text, body = fm_match.group(1), fm_match.group(2)
            meta = parse_simple_yaml(fm_text)
            
            item_id = meta.get("id") or qmd_path.stem
            meta["id"] = item_id
            meta["path"] = str(qmd_path)
            meta["rel_path"] = f"{cat}/{qmd_path.name}"
            meta["url"] = f"/{cat}/{qmd_path.stem}.html"
            meta["category_folder"] = cat
            meta["body"] = body
            meta["wikilinks"] = extract_wikilinks(body)
            
            frameworks[item_id] = meta
            
    return frameworks

def build_graph(frameworks):
    nodes = []
    edges = []
    edge_set = set()
    backlinks = {item_id: [] for item_id in frameworks}
    
    # 1. Register Nodes
    for item_id, data in frameworks.items():
        cats = data.get("categories", [data["category_folder"].capitalize()])
        nodes.append({
            "id": item_id,
            "title": data.get("title", item_id.replace("-", " ").title()),
            "category": cats[0] if cats else "General",
            "categories": cats,
            "summary": data.get("summary", ""),
            "url": data["url"],
            "start_here": bool(data.get("start_here", False))
        })
    
    # 2. Register Edges from Frontmatter 'related'
    for item_id, data in frameworks.items():
        related = data.get("related", [])
        for rel in related:
            target_id = rel.get("id")
            rel_type = rel.get("type", "related to")
            if target_id in frameworks:
                edge_key = (item_id, target_id, rel_type)
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    edges.append({
                        "source": item_id,
                        "target": target_id,
                        "type": rel_type,
                        "label": rel_type
                    })
                backlinks[target_id].append({
                    "id": item_id,
                    "title": frameworks[item_id].get("title", item_id),
                    "url": frameworks[item_id]["url"],
                    "category": frameworks[item_id].get("categories", ["General"])[0],
                    "type": f"is {rel_type}"
                })
                
    # 3. Register Edges from [[wikilinks]]
    for item_id, data in frameworks.items():
        for target_id, alias in data.get("wikilinks", []):
            if target_id in frameworks:
                edge_key = (item_id, target_id, "references")
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    edges.append({
                        "source": item_id,
                        "target": target_id,
                        "type": "references",
                        "label": "mentions"
                    })
                # Add to backlinks if not already present
                if not any(b["id"] == item_id for b in backlinks[target_id]):
                    backlinks[target_id].append({
                        "id": item_id,
                        "title": frameworks[item_id].get("title", item_id),
                        "url": frameworks[item_id]["url"],
                        "category": frameworks[item_id].get("categories", ["General"])[0],
                        "type": "mentions this"
                    })
                    
    # Calculate degree
    degree_map = {n["id"]: 0 for n in nodes}
    for e in edges:
        degree_map[e["source"]] += 1
        degree_map[e["target"]] += 1
    for n in nodes:
        n["degree"] = degree_map[n["id"]]
        
    return {
        "nodes": nodes,
        "edges": edges,
        "categories": ["Law", "Policy", "Economics", "Society"]
    }, backlinks

def update_qmd_footers(frameworks, backlinks):
    """Injects Backlinks, Typed Relations, and Local Graph widget into each .qmd file."""
    for item_id, data in frameworks.items():
        qmd_path = Path(data["path"])
        content = qmd_path.read_text(encoding="utf-8")
        
        # Remove existing autogenerated block if present
        clean_content = re.sub(
            r"\n*<!-- AUTOGENERATED_RELATIONS_START -->.*?<!-- AUTOGENERATED_RELATIONS_END -->",
            "",
            content,
            flags=re.DOTALL
        ).rstrip()
        
        # Build Related block grouped by relation type
        related_items = data.get("related", [])
        rel_by_type = {}
        for rel in related_items:
            tgt_id = rel.get("id")
            rtype = rel.get("type", "Related").capitalize()
            if tgt_id in frameworks:
                rel_by_type.setdefault(rtype, []).append((tgt_id, frameworks[tgt_id]))
                
        # Build Backlinks
        item_backlinks = backlinks.get(item_id, [])
        
        footer_parts = [
            "\n\n<!-- AUTOGENERATED_RELATIONS_START -->",
            "## Network & Connections",
            "",
            "::: {.local-graph-box}",
            '<div class="local-graph-header">',
            f'  <span><strong>{data.get("title", item_id)}</strong> in Network (1-2 Hops)</span>',
            '  <button id="btn-toggle-hops" class="btn btn-sm btn-outline-primary">1 Hop</button>',
            "</div>",
            f'<div id="local-graph-canvas" class="local-graph-canvas" data-node-id="{item_id}"></div>',
            ":::",
            ""
        ]
        
        if rel_by_type or item_backlinks:
            footer_parts.append("::: {.relations-container}")
            
            if rel_by_type:
                footer_parts.append("### Typed Relations\n")
                for rtype, targets in rel_by_type.items():
                    footer_parts.append(f"**{rtype}:**")
                    for tid, tdata in targets:
                        footer_parts.append(f"- [{tdata.get('title', tid)}]({tdata['url']}) — *{tdata.get('summary', '')}*")
                    footer_parts.append("")
                    
            if item_backlinks:
                footer_parts.append("### Backlinks (Linked From)\n")
                for bl in item_backlinks:
                    footer_parts.append(f"- [{bl['title']}]({bl['url']}) `({bl['type']})`")
                footer_parts.append("")
                
            footer_parts.append(":::")
            
        footer_parts.append("<!-- AUTOGENERATED_RELATIONS_END -->\n")
        
        updated_content = clean_content + "\n" + "\n".join(footer_parts)
        qmd_path.write_text(updated_content, encoding="utf-8")
        
    print(f"Updated {len(frameworks)} .qmd files with interactive graph and relation blocks.")

def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    frameworks = scan_frameworks()
    print(f"Found {len(frameworks)} frameworks.")
    
    graph_data, backlinks = build_graph(frameworks)
    
    # Save graph.json
    graph_path = ASSETS_DIR / "graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)
    print(f"Saved graph data ({len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges) to {graph_path}")
    
    # Save backlinks.json
    backlinks_path = ASSETS_DIR / "backlinks.json"
    with open(backlinks_path, "w", encoding="utf-8") as f:
        json.dump(backlinks, f, indent=2)
    print(f"Saved backlinks index to {backlinks_path}")

    # Inject into .qmd files
    update_qmd_footers(frameworks, backlinks)

if __name__ == "__main__":
    main()
