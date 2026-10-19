#!/usr/bin/env python3
"""
scripts/build_embeddings.py
Phase 2 Semantic Search Pipeline.
Computes dense normalized semantic vectors for each essay/concept in graph.json.
Generates assets/embeddings.json for client-side cosine similarity ranking
and graph-neighbor expansion.
"""

import json
import math
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
GRAPH_FILE = ASSETS_DIR / "graph.json"
OUT_EMBEDDINGS_FILE = ASSETS_DIR / "embeddings.json"

VECTOR_DIM = 64

def tokenize(text):
    """Clean and tokenize text into words and 3-char n-grams."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    # Stopwords to filter
    stopwords = {
        "the", "and", "that", "this", "with", "from", "for", "are", "was",
        "were", "which", "about", "into", "their", "when", "what", "over",
        "more", "than", "then", "will", "would", "could", "should", "have"
    }
    return [w for w in words if w not in stopwords]

def hash_token_to_features(token, dim=VECTOR_DIM):
    """Maps a token to deterministic feature indices and sign weights."""
    h1 = hash(token) % dim
    h2 = hash(token + "_2") % dim
    sign = 1 if (hash(token + "_sign") % 2 == 0) else -1
    return [(h1, sign * 1.0), (h2, sign * 0.7)]

def compute_dense_vector(text, idf_weights, dim=VECTOR_DIM):
    """Computes an L2-normalized dense embedding vector for the text."""
    tokens = tokenize(text)
    vec = [0.0] * dim
    
    if not tokens:
        return vec
        
    for tok in tokens:
        weight = idf_weights.get(tok, 1.0)
        for idx, val in hash_token_to_features(tok, dim):
            vec[idx] += val * weight
            
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [round(x / norm, 5) for x in vec]
    return vec

def build_embeddings():
    if not GRAPH_FILE.exists():
        print(f"Error: {GRAPH_FILE} does not exist. Run scripts/build_graph.py first.")
        return
        
    with open(GRAPH_FILE, "r", encoding="utf-8") as f:
        graph_data = json.load(f)
        
    nodes = graph_data.get("nodes", [])
    print(f"Building semantic embeddings for {len(nodes)} items...")
    
    # 1. Compute corpus frequencies for IDF weighting
    doc_tokens = []
    df_counts = {}
    N = len(nodes)
    
    for node in nodes:
        rich_text = f"{node['title']} {node.get('summary', '')} {node['category']} {' '.join(node.get('categories', []))}"
        toks = set(tokenize(rich_text))
        doc_tokens.append((node, rich_text, toks))
        for t in toks:
            df_counts[t] = df_counts.get(t, 0) + 1
            
    idf_weights = {}
    for t, count in df_counts.items():
        idf_weights[t] = math.log(1.0 + (N / (1.0 + count)))
        
    # 2. Compute vectors for all nodes
    embeddings_list = []
    for node, rich_text, toks in doc_tokens:
        vec = compute_dense_vector(rich_text, idf_weights, dim=VECTOR_DIM)
        embeddings_list.append({
            "id": node["id"],
            "title": node["title"],
            "category": node["category"],
            "summary": node.get("summary", ""),
            "url": node["url"],
            "keywords": list(toks)[:12],
            "vector": vec
        })
        
    # Save embeddings.json
    with open(OUT_EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "dimension": VECTOR_DIM,
            "idf_vocab": {k: round(v, 4) for k, v in idf_weights.items() if v > 0.5},
            "documents": embeddings_list
        }, f, indent=2)
        
    print(f"Generated {len(embeddings_list)} embeddings in {OUT_EMBEDDINGS_FILE}")

if __name__ == "__main__":
    build_embeddings()
