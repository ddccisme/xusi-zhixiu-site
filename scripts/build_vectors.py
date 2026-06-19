#!/usr/bin/env python3
"""
向量检索构建脚本

使用 Ollama 本地模型生成文本 Embedding，使用 perceptual hash 生成图片相似度索引。
"""

import argparse
import base64
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

import faiss
import imagehash
import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from utils import now_str

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_DB = PROJECT_ROOT / "data" / "collections.sqlite"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

OLLAMA_BASE_URL = "http://localhost:11434"
TEXT_EMBEDDING_MODEL = "qwen3-embedding:0.6b"


def get_ollama_embedding(text: str) -> Optional[np.ndarray]:
    """使用 Ollama 生成文本 Embedding"""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": TEXT_EMBEDDING_MODEL, "prompt": text},
            timeout=60
        )
        resp.raise_for_status()
        vec = np.array(resp.json()["embedding"], dtype=np.float32)
        # L2 归一化，便于使用内积索引计算余弦相似度
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec
    except Exception as e:
        print(f"  [警告] Ollama embedding 失败: {e}")
        return None


def get_image_phash(image_path: Path) -> Optional[str]:
    """生成图片 perceptual hash"""
    try:
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))
    except Exception as e:
        print(f"  [警告] pHash 生成失败 {image_path}: {e}")
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """计算两个 64 位 hash 的汉明距离"""
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def save_faiss_index(index: faiss.IndexFlatIP, path: Path, mapping: List[Dict]):
    """保存 FAISS 索引和映射文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))
    mapping_path = path.with_suffix(".mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def build_vectors(db_path: Path, data_dir: Path, vault_path: Path, text_only: bool = False, limit: Optional[int] = None):
    """构建向量索引"""
    if not db_path.exists():
        print(f"错误: 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 获取所有 published 藏品
    cursor.execute("""
        SELECT c.id, c.name, c.description, c.appreciation, c.technique, c.pattern, c.theme, c.material, c.color,
               GROUP_CONCAT(t.name) as tags
        FROM collections c
        LEFT JOIN collection_tags ct ON c.id = ct.collection_id
        LEFT JOIN tags t ON ct.tag_id = t.id
        WHERE c.status = 'published'
        GROUP BY c.id
    """)

    collections = [dict(row) for row in cursor.fetchall()]
    if limit:
        collections = collections[:limit]

    print(f"处理 {len(collections)} 条藏品")
    print(f"文本 Embedding 模型: {TEXT_EMBEDDING_MODEL} (Ollama)")
    if not text_only:
        print("图片索引: perceptual hash (pHash)")

    text_vectors = []
    text_mapping = []
    image_hashes = []

    for idx, coll in enumerate(collections, 1):
        # 构建文本输入
        tags = coll.get("tags", "") or ""
        technique = coll.get("technique", "[]")
        pattern = coll.get("pattern", "[]")
        theme = coll.get("theme", "[]")
        material = coll.get("material", "")
        color = coll.get("color", "[]")

        def parse_json_field(value):
            try:
                return json.loads(value) if value else []
            except json.JSONDecodeError:
                return []

        technique_list = parse_json_field(technique)
        pattern_list = parse_json_field(pattern)
        theme_list = parse_json_field(theme)
        color_list = parse_json_field(color)

        text_parts = [
            coll.get("name", ""),
            coll.get("description", ""),
            coll.get("appreciation", ""),
            " ".join(technique_list),
            " ".join(pattern_list),
            " ".join(theme_list),
            material,
            " ".join(color_list),
            tags
        ]
        text_input = " ".join([p for p in text_parts if p and p != "（待生成）"])
        text_input = text_input.strip()

        if text_input:
            vec = get_ollama_embedding(text_input)
            if vec is not None:
                text_vectors.append(vec)
                text_mapping.append({
                    "collection_id": coll["id"],
                    "name": coll["name"],
                    "type": "text"
                })

                cursor.execute("""
                    INSERT OR REPLACE INTO embeddings (collection_id, embedding_type, model_name, vector, dimensions, created_at)
                    VALUES (?, 'text', ?, ?, ?, ?)
                """, (coll["id"], TEXT_EMBEDDING_MODEL, vec.tobytes(), len(vec), now_str()))

        # 图片 pHash
        if not text_only:
            cursor.execute("""
                SELECT * FROM collection_images
                WHERE collection_id = ? AND is_main = 1
                ORDER BY id LIMIT 1
            """, (coll["id"],))
            main_image = cursor.fetchone()

            if main_image:
                img_path = vault_path / main_image["relative_path"]
                if img_path.exists():
                    phash = get_image_phash(img_path)
                    if phash:
                        image_hashes.append({
                            "collection_id": coll["id"],
                            "image_id": main_image["id"],
                            "filename": main_image["filename"],
                            "phash": phash
                        })

        if idx % 100 == 0:
            print(f"  已处理 {idx}/{len(collections)}")
            conn.commit()

    conn.commit()

    # 构建 FAISS 文本索引
    if text_vectors:
        dim = len(text_vectors[0])
        text_index = faiss.IndexFlatIP(dim)
        text_index.add(np.array(text_vectors).astype("float32"))
        save_faiss_index(text_index, data_dir / "text.index", text_mapping)
        print(f"\n文本索引: {len(text_vectors)} 条，维度 {dim}")

    # 保存图片 hash 索引
    if image_hashes:
        with open(data_dir / "image_hashes.json", "w", encoding="utf-8") as f:
            json.dump(image_hashes, f, ensure_ascii=False, indent=2)
        print(f"图片索引: {len(image_hashes)} 条")

    conn.close()
    print("\n向量索引构建完成")


def main():
    parser = argparse.ArgumentParser(description="构建藏品向量索引")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB), help="SQLite 数据库路径")
    parser.add_argument("--data-dir", type=str, default=str(DEFAULT_DATA_DIR), help="索引输出目录")
    parser.add_argument("--vault", type=str, default=str(PROJECT_ROOT / "kb"), help="Obsidian Vault 路径")
    parser.add_argument("--text-only", action="store_true", help="仅构建文本索引")
    parser.add_argument("--limit", type=int, default=None, help="最多处理条数")

    args = parser.parse_args()

    build_vectors(
        db_path=Path(args.db),
        data_dir=Path(args.data_dir),
        vault_path=Path(args.vault),
        text_only=args.text_only,
        limit=args.limit
    )


if __name__ == "__main__":
    main()
