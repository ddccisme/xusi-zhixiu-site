#!/usr/bin/env python3
"""
叙思织绣藏品知识库构建脚本

读取 kb/Collections/ 下的 Obsidian Markdown 笔记，解析 YAML frontmatter，
写入 SQLite 数据库，并导出 JSON 供静态站点使用。
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import frontmatter
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    now_str, normalize_list, clean_text, get_image_dimensions,
    safe_slug
)


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_VAULT = PROJECT_ROOT / "kb"
DEFAULT_DB = PROJECT_ROOT / "data" / "collections.sqlite"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

REQUIRED_FIELDS = ["id", "name", "slug", "collection_type", "source", "status"]
VALID_COLLECTION_TYPES = ["文物展示", "自营产品", "当代创作"]
VALID_SOURCES = ["中国历代", "中国当代", "西方", "民族学", "其他", "自营藏品", "当代创作", "文创品牌"]
VALID_CATEGORIES = ["织物", "服装", "工艺品", "配饰", "家纺", "其他", "大师服装", "新秀服装",
                    "品牌服饰", "面料", "家纺", "图案手稿", "古董刺绣", "收藏级织物",
                    "名家古董商专区", "艺术家合作", "文化创作", "展览", "活动", "服饰系列", "文创周边"]


def init_database(db_path: Path) -> sqlite3.Connection:
    """初始化 SQLite 数据库"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS collections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE,
            collection_type TEXT,
            source TEXT,
            category TEXT,
            sub_category TEXT,
            technique TEXT,
            pattern TEXT,
            theme TEXT,
            material TEXT,
            era TEXT,
            dynasty TEXT,
            size TEXT,
            color TEXT,
            quantity TEXT,
            collection_unit TEXT,
            author TEXT,
            level TEXT,
            origin TEXT,
            source_url TEXT,
            source_site TEXT,
            crawled_at TEXT,
            status TEXT DEFAULT 'published',
            description TEXT,
            appreciation TEXT,
            metadata_json TEXT,
            created_at TEXT,
            updated_at TEXT,
            note_path TEXT
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS collection_tags (
            collection_id TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (collection_id, tag_id),
            FOREIGN KEY (collection_id) REFERENCES collections(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        );

        CREATE TABLE IF NOT EXISTS collection_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            alt TEXT,
            is_main BOOLEAN DEFAULT 0,
            width INTEGER,
            height INTEGER,
            file_size INTEGER,
            FOREIGN KEY (collection_id) REFERENCES collections(id)
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id TEXT NOT NULL,
            embedding_type TEXT NOT NULL,
            model_name TEXT,
            vector BLOB,
            dimensions INTEGER,
            created_at TEXT,
            FOREIGN KEY (collection_id) REFERENCES collections(id)
        );

        CREATE TABLE IF NOT EXISTS build_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            build_time TEXT,
            total_notes INTEGER,
            total_images INTEGER,
            new_notes INTEGER,
            updated_notes INTEGER,
            errors TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_collections_source ON collections(source);
        CREATE INDEX IF NOT EXISTS idx_collections_category ON collections(category);
        CREATE INDEX IF NOT EXISTS idx_collections_era ON collections(era);
        CREATE INDEX IF NOT EXISTS idx_collections_status ON collections(status);
        CREATE INDEX IF NOT EXISTS idx_collections_collection_type ON collections(collection_type);
        CREATE INDEX IF NOT EXISTS idx_collection_tags_collection_id ON collection_tags(collection_id);
        CREATE INDEX IF NOT EXISTS idx_collection_tags_tag_id ON collection_tags(tag_id);
        CREATE INDEX IF NOT EXISTS idx_collection_images_collection_id ON collection_images(collection_id);
        CREATE INDEX IF NOT EXISTS idx_embeddings_collection_id ON embeddings(collection_id);
    """)

    conn.commit()
    return conn


def validate_frontmatter(meta: Dict[str, Any], note_path: Path) -> List[str]:
    """校验 frontmatter 字段"""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in meta or meta[field] is None or str(meta[field]).strip() == "":
            errors.append(f"缺少必填字段: {field}")

    if meta.get("collection_type") and meta["collection_type"] not in VALID_COLLECTION_TYPES:
        errors.append(f"collection_type 无效: {meta.get('collection_type')}")

    if meta.get("source") and meta["source"] not in VALID_SOURCES:
        errors.append(f"source 无效: {meta.get('source')}")

    if meta.get("category") and meta["category"] not in VALID_CATEGORIES:
        errors.append(f"category 无效: {meta.get('category')}")

    return errors


def extract_sections(content: str) -> Dict[str, str]:
    """提取 Markdown 正文中的各个章节"""
    sections = {}
    if not content:
        return sections

    # 找到所有 ## 标题
    pattern = r'\n##\s+([^\n]+)\n(.*?)(?=\n##\s+|$)'
    matches = re.findall(pattern, content, re.DOTALL)
    for title, body in matches:
        sections[title.strip()] = body.strip()

    return sections


def parse_note(note_path: Path, vault_path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """解析单个 Obsidian 笔记"""
    errors = []

    try:
        post = frontmatter.load(note_path)
    except Exception as e:
        return None, [f"解析 frontmatter 失败: {e}"]

    meta = post.metadata or {}
    content = post.content or ""

    # 校验
    validation_errors = validate_frontmatter(meta, note_path)
    errors.extend(validation_errors)

    # 生成 slug（如果没有）
    if not meta.get("slug"):
        meta["slug"] = safe_slug(meta.get("name", ""), str(meta.get("id", "")))

    # 解析正文章节
    sections = extract_sections(content)
    description = sections.get("描述", "").strip()
    appreciation = sections.get("艺术评鉴", "").strip()

    # 如果没有描述字段但有正文，尝试用非章节内容作为描述
    if not description:
        # 去掉第一个 # 标题后的内容
        lines = content.split("\n")
        non_header_lines = []
        for line in lines:
            if line.startswith("# "):
                continue
            non_header_lines.append(line)
        description = "\n".join(non_header_lines).strip()

    # 合并标签：显式 tags + technique + pattern + theme
    all_tags = set(normalize_list(meta.get("tags")))
    all_tags.update(normalize_list(meta.get("technique")))
    all_tags.update(normalize_list(meta.get("pattern")))
    all_tags.update(normalize_list(meta.get("theme")))
    all_tags.update(normalize_list(meta.get("material")))
    all_tags.update(normalize_list(meta.get("color")))

    # 处理图片
    images = []
    image_list = meta.get("images", [])
    if not image_list:
        # 尝试从正文中提取图片
        image_list = extract_images_from_content(content)

    for img in image_list:
        img_path = vault_path / img.get("path", "")
        if not img_path.exists():
            errors.append(f"图片不存在: {img.get('path')}")
            continue

        dims = get_image_dimensions(img_path)
        file_size = img_path.stat().st_size
        images.append({
            "filename": img_path.name,
            "relative_path": str(img_path.relative_to(vault_path)),
            "alt": img.get("alt", meta.get("name", "")),
            "is_main": bool(img.get("is_main", False)),
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
            "file_size": file_size
        })

    collection = {
        "id": str(meta.get("id", "")).strip(),
        "name": str(meta.get("name", "")).strip(),
        "slug": str(meta.get("slug", "")).strip(),
        "collection_type": meta.get("collection_type", ""),
        "source": meta.get("source", ""),
        "category": meta.get("category", ""),
        "sub_category": meta.get("sub_category", ""),
        "technique": json.dumps(normalize_list(meta.get("technique")), ensure_ascii=False),
        "pattern": json.dumps(normalize_list(meta.get("pattern")), ensure_ascii=False),
        "theme": json.dumps(normalize_list(meta.get("theme")), ensure_ascii=False),
        "material": meta.get("material", ""),
        "era": meta.get("era", ""),
        "dynasty": meta.get("dynasty", ""),
        "size": meta.get("size", ""),
        "color": json.dumps(normalize_list(meta.get("color")), ensure_ascii=False),
        "quantity": meta.get("quantity", ""),
        "collection_unit": meta.get("collection_unit", ""),
        "author": meta.get("author", ""),
        "level": meta.get("level", ""),
        "origin": meta.get("origin", ""),
        "source_url": meta.get("source_url", ""),
        "source_site": meta.get("source_site", ""),
        "crawled_at": meta.get("crawled_at", ""),
        "status": meta.get("status", "published"),
        "description": description,
        "appreciation": appreciation,
        "metadata_json": json.dumps(meta, ensure_ascii=False),
        "created_at": meta.get("created_at", ""),
        "updated_at": meta.get("updated_at", ""),
        "note_path": str(note_path.relative_to(vault_path)),
        "tags": sorted(all_tags),
        "images": images
    }

    return collection, errors


def extract_images_from_content(content: str) -> List[Dict[str, str]]:
    """从 Markdown 正文中提取图片链接"""
    import re
    images = []
    pattern = r'!\[(.*?)\]\((.*?)\)'
    matches = re.findall(pattern, content)
    for alt, path in matches:
        images.append({
            "alt": alt.strip(),
            "path": path.strip(),
            "is_main": True
        })
    return images


def sync_collection(conn: sqlite3.Connection, collection: Dict[str, Any]) -> bool:
    """同步单条藏品到数据库，返回是否为新增"""
    cursor = conn.cursor()

    # 检查是否已存在
    cursor.execute("SELECT id FROM collections WHERE id = ?", (collection["id"],))
    exists = cursor.fetchone() is not None

    cursor.execute("""
        INSERT OR REPLACE INTO collections (
            id, name, slug, collection_type, source, category, sub_category,
            technique, pattern, theme, material, era, dynasty, size, color,
            quantity, collection_unit, author, level, origin, source_url,
            source_site, crawled_at, status, description, appreciation,
            metadata_json, created_at, updated_at, note_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        collection["id"], collection["name"], collection["slug"],
        collection["collection_type"], collection["source"], collection["category"],
        collection["sub_category"], collection["technique"], collection["pattern"],
        collection["theme"], collection["material"], collection["era"],
        collection["dynasty"], collection["size"], collection["color"],
        collection["quantity"], collection["collection_unit"], collection["author"],
        collection["level"], collection["origin"], collection["source_url"],
        collection["source_site"], collection["crawled_at"], collection["status"],
        collection["description"], collection["appreciation"],
        collection["metadata_json"], collection["created_at"],
        collection["updated_at"], collection["note_path"]
    ))

    collection_id = collection["id"]

    # 同步标签
    cursor.execute("DELETE FROM collection_tags WHERE collection_id = ?", (collection_id,))
    for tag_name in collection["tags"]:
        cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        tag_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT OR IGNORE INTO collection_tags (collection_id, tag_id) VALUES (?, ?)",
            (collection_id, tag_id)
        )

    # 同步图片
    cursor.execute("DELETE FROM collection_images WHERE collection_id = ?", (collection_id,))
    for img in collection["images"]:
        cursor.execute("""
            INSERT INTO collection_images (
                collection_id, filename, relative_path, alt, is_main, width, height, file_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            collection_id, img["filename"], img["relative_path"], img["alt"],
            img["is_main"], img["width"], img["height"], img["file_size"]
        ))

    conn.commit()
    return not exists


def archive_missing_notes(conn: sqlite3.Connection, current_ids: set) -> int:
    """将数据库中存在但笔记目录中不存在的藏品标记为 archived"""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM collections WHERE status = 'published'")
    db_ids = {row[0] for row in cursor.fetchall()}

    missing_ids = db_ids - current_ids
    for missing_id in missing_ids:
        cursor.execute(
            "UPDATE collections SET status = 'archived' WHERE id = ?",
            (missing_id,)
        )

    conn.commit()
    return len(missing_ids)


def export_json(conn: sqlite3.Connection, data_dir: Path) -> None:
    """导出 JSON 文件"""
    data_dir.mkdir(parents=True, exist_ok=True)
    cursor = conn.cursor()

    # 导出 collections.json
    cursor.execute("""
        SELECT c.*, GROUP_CONCAT(t.name) as tags
        FROM collections c
        LEFT JOIN collection_tags ct ON c.id = ct.collection_id
        LEFT JOIN tags t ON ct.tag_id = t.id
        WHERE c.status = 'published'
        GROUP BY c.id
    """)
    collections = []
    for row in cursor.fetchall():
        row_dict = dict(row)
        # 解析 JSON 字段
        for field in ["technique", "pattern", "theme", "color"]:
            try:
                row_dict[field] = json.loads(row_dict.get(field, "[]") or "[]")
            except json.JSONDecodeError:
                row_dict[field] = []
        row_dict["tags"] = row_dict.get("tags", "").split(",") if row_dict.get("tags") else []

        # 查询图片
        cursor.execute(
            "SELECT * FROM collection_images WHERE collection_id = ? ORDER BY is_main DESC",
            (row_dict["id"],)
        )
        row_dict["images"] = [dict(img) for img in cursor.fetchall()]

        collections.append(row_dict)

    with open(data_dir / "collections.json", "w", encoding="utf-8") as f:
        json.dump(collections, f, ensure_ascii=False, indent=2)

    # 导出 tags.json
    cursor.execute("SELECT * FROM tags ORDER BY name")
    tags = [dict(row) for row in cursor.fetchall()]
    with open(data_dir / "tags.json", "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)

    print(f"已导出 {len(collections)} 条藏品到 {data_dir / 'collections.json'}")
    print(f"已导出 {len(tags)} 个标签到 {data_dir / 'tags.json'}")


def build(vault_path: Path, db_path: Path, data_dir: Path, full: bool = False, validate_only: bool = False) -> None:
    """主构建流程"""
    if not vault_path.exists():
        print(f"错误: 知识库目录不存在: {vault_path}")
        sys.exit(1)

    collections_dir = vault_path / "Collections"
    if not collections_dir.exists():
        print(f"错误: Collections 目录不存在: {collections_dir}")
        sys.exit(1)

    conn = None
    if not validate_only:
        conn = init_database(db_path)

    note_files = list(collections_dir.rglob("*.md"))
    print(f"扫描到 {len(note_files)} 个笔记文件")

    all_errors = []
    new_count = 0
    updated_count = 0
    current_ids = set()
    parsed_collections = []

    for note_path in note_files:
        collection, errors = parse_note(note_path, vault_path)
        if collection is None:
            all_errors.extend([f"{note_path}: {e}" for e in errors])
            continue

        current_ids.add(collection["id"])
        parsed_collections.append((collection, errors, note_path))

    if validate_only:
        print("\n=== 校验结果 ===")
        valid_count = 0
        for collection, errors, note_path in parsed_collections:
            if errors:
                print(f"\n{note_path}")
                for e in errors:
                    print(f"  - {e}")
            else:
                valid_count += 1
        print(f"\n有效笔记: {valid_count}/{len(parsed_collections)}")
        if all_errors:
            print(f"解析失败: {len(all_errors)} 条")
            for e in all_errors[:20]:
                print(f"  - {e}")
        return

    for collection, errors, note_path in parsed_collections:
        if errors:
            all_errors.extend([f"{note_path}: {e}" for e in errors])

        is_new = sync_collection(conn, collection)
        if is_new:
            new_count += 1
        else:
            updated_count += 1

    # 处理已删除笔记
    archived_count = 0
    if not full:
        archived_count = archive_missing_notes(conn, current_ids)
    else:
        # full 构建时，所有不在 current_ids 中的都标记为 archived
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM collections WHERE status = 'published'")
        db_ids = {row[0] for row in cursor.fetchall()}
        missing_ids = db_ids - current_ids
        for missing_id in missing_ids:
            cursor.execute("UPDATE collections SET status = 'archived' WHERE id = ?", (missing_id,))
        conn.commit()
        archived_count = len(missing_ids)

    # 导出 JSON
    export_json(conn, data_dir)

    # 记录构建日志
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO build_log (build_time, total_notes, total_images, new_notes, updated_notes, errors)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        now_str(), len(parsed_collections),
        sum(len(c["images"]) for c, _, _ in parsed_collections),
        new_count, updated_count, json.dumps(all_errors, ensure_ascii=False)
    ))
    conn.commit()

    print("\n=== 构建完成 ===")
    print(f"总笔记数: {len(parsed_collections)}")
    print(f"新增: {new_count}")
    print(f"更新: {updated_count}")
    print(f"归档: {archived_count}")
    print(f"错误/警告: {len(all_errors)}")

    if all_errors:
        print("\n=== 错误/警告详情（前 20 条）===")
        for e in all_errors[:20]:
            print(f"  - {e}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="叙思织绣藏品知识库构建脚本")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT), help="Obsidian Vault 路径")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB), help="SQLite 数据库路径")
    parser.add_argument("--data-dir", type=str, default=str(DEFAULT_DATA_DIR), help="JSON 输出目录")
    parser.add_argument("--full", action="store_true", help="完整重建（会归档已删除笔记）")
    parser.add_argument("--validate", action="store_true", help="仅校验笔记格式，不写入数据库")

    args = parser.parse_args()

    build(
        vault_path=Path(args.vault),
        db_path=Path(args.db),
        data_dir=Path(args.data_dir),
        full=args.full,
        validate_only=args.validate
    )


if __name__ == "__main__":
    main()
