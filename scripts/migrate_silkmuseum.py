#!/usr/bin/env python3
"""
中国丝绸博物馆展品数据迁移脚本

将 03_中国丝绸博物馆展品/ 下的 Markdown + 图片 迁移到项目知识库 kb/ 中，
转换为 Obsidian 友好的 YAML frontmatter + Markdown 格式。
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import frontmatter
from slugify import slugify

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    parse_markdown_table, extract_description, extract_source_info,
    extract_image_links, extract_tags_from_text, safe_slug, now_str
)


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_SOURCE_DIR = PROJECT_ROOT.parent / "03_中国丝绸博物馆展品"
DEFAULT_VAULT = PROJECT_ROOT / "kb"

SOURCE_MAP = {
    "中国历代": "中国历代",
    "中国当代": "中国当代",
    "西方": "西方",
    "民族学": "民族学",
    "其他": "其他"
}

CATEGORY_MAP = {
    "中国历代": ["织物", "服装", "工艺品", "其他"],
    "中国当代": ["大师服装", "新秀服装", "品牌服饰", "面料", "家纺", "图案手稿", "其他"],
    "西方": ["织物", "服装", "配饰", "家纺", "其他"],
    "民族学": ["织物", "服装", "配饰", "家纺", "其他"],
    "其他": ["其他"]
}


def extract_itemid_from_filename(filename: str) -> Optional[str]:
    """从文件名提取 itemid，如 name_1234.md → 1234"""
    # 匹配末尾或中间的下划线数字
    match = re.search(r'_\d+$', Path(filename).stem)
    if match:
        return match.group(0)[1:]
    return None


def map_source_to_category(source: str, description: str, basic_info: Dict[str, str]) -> str:
    """根据来源和描述推断 category"""
    valid_cats = CATEGORY_MAP.get(source, ["其他"])

    # 从描述和基本信息中查找关键词
    text = (basic_info.get("质地", "") + " " + description).lower()
    if "服装" in text or "裙" in text or "袍" in text or "衣" in text:
        if "服装" in valid_cats:
            return "服装"
    if "织物" in text or "锦" in text or "缎" in text or "绸" in text or "面料" in text:
        if "织物" in valid_cats:
            return "织物"
        if "面料" in valid_cats:
            return "面料"
    if "配饰" in text or "帽" in text or "鞋" in text or "包" in text or "扇套" in text:
        if "配饰" in valid_cats:
            return "配饰"
    if "家纺" in text or "垫" in text or "帘" in text or "被" in text:
        if "家纺" in valid_cats:
            return "家纺"

    return valid_cats[0] if valid_cats else "其他"


def convert_basic_info(basic_info: Dict[str, str]) -> Dict[str, any]:
    """将旧的基本信息表转换为 frontmatter 字段"""
    field_map = {
        "文物名称": "name",
        "尺寸": "size",
        "时代": "era",
        "质地": "material",
        "来源": "origin",
        "级别": "level",
        "收藏单位": "collection_unit",
        "作者": "author"
    }

    result = {}
    for old_key, new_key in field_map.items():
        value = basic_info.get(old_key, "")
        if value and value != "未知":
            result[new_key] = value
        else:
            result[new_key] = ""

    # 处理 dynasty
    era = result.get("era", "")
    dynasty = ""
    if era:
        # 从时代中提取朝代
        match = re.search(r'(战国|汉晋|南北朝|隋唐|宋|辽|元|明|清|民国|现代|当代|\d+世纪|\d{2,4})', era)
        if match:
            dynasty = match.group(1)
    result["dynasty"] = dynasty

    return result


def find_images_for_note(note_path: Path, source_dir: Path) -> List[Tuple[Path, Dict[str, str]]]:
    """查找与笔记相关的图片文件"""
    images = []
    stem = note_path.stem
    parent = note_path.parent

    # 直接搜索同级目录下的图片
    for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        # 文件名以笔记名开头
        for img_path in parent.glob(f"{stem}*{ext}"):
            images.append((img_path, {"alt": f"{stem} 图片", "is_main": True}))

    # 也搜索不含 itemid 的版本
    if "_" in stem:
        base_stem = stem.rsplit("_", 1)[0]
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            for img_path in parent.glob(f"{base_stem}*{ext}"):
                if img_path not in [p for p, _ in images]:
                    images.append((img_path, {"alt": f"{base_stem} 图片", "is_main": True}))

    # 按文件名长度排序，通常主图较短
    images.sort(key=lambda x: len(x[0].name))

    return images


def extract_itemid_from_url(url: str) -> Optional[str]:
    """从 URL 中提取 itemid，如 ?itemid=30667"""
    match = re.search(r'itemid=(\d+)', url)
    if match:
        return match.group(1)
    return None


def migrate_note(source_path: Path, source: str, vault_path: Path) -> Tuple[Optional[Path], List[str]]:
    """迁移单个笔记"""
    errors = []

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return None, [f"读取失败: {e}"]

    # 先解析数据来源，尝试从 URL 提取 itemid
    source_info = extract_source_info(text)
    source_url = source_info.get("原始链接", "")
    source_site = source_info.get("来源网站", "中国丝绸博物馆")
    crawled_at = source_info.get("采集时间", "2026-06-13")

    # 提取 itemid：优先文件名，其次 URL，最后 hash
    itemid = extract_itemid_from_filename(source_path.name)
    if not itemid and source_url:
        itemid = extract_itemid_from_url(source_url)
    if not itemid:
        # 如果没有 itemid，使用短 hash
        itemid = str(abs(hash(source_path.stem)) % 1000000).zfill(6)

    # 解析基本信息表
    basic_info = parse_markdown_table(text, "## 基本信息")
    name = basic_info.get("文物名称", source_path.stem)

    # 描述
    description = extract_description(text)

    # 数据来源已提前解析

    # 转换 frontmatter 字段
    converted = convert_basic_info(basic_info)

    # 推断 category
    category = map_source_to_category(source, description, basic_info)

    # 提取标签
    combined_text = f"{name} {description} {converted.get('material', '')}"
    tags_result = extract_tags_from_text(combined_text)

    # 查找图片
    related_images = find_images_for_note(source_path, source_path.parent)

    # 生成 slug
    slug = safe_slug(name, itemid)

    # 准备新 frontmatter
    now = datetime.now().strftime("%Y-%m-%d")
    frontmatter_data = {
        "id": itemid,
        "name": name,
        "slug": slug,
        "collection_type": "文物展示",
        "source": source,
        "category": category,
        "technique": tags_result["technique"],
        "pattern": tags_result["pattern"],
        "theme": tags_result["theme"],
        "material": converted.get("material", ""),
        "era": converted.get("era", ""),
        "dynasty": converted.get("dynasty", ""),
        "size": converted.get("size", ""),
        "color": tags_result["color"],
        "quantity": "",
        "collection_unit": converted.get("collection_unit", "中国丝绸博物馆"),
        "author": converted.get("author", ""),
        "level": converted.get("level", ""),
        "origin": converted.get("origin", ""),
        "source_url": source_url,
        "source_site": source_site,
        "crawled_at": crawled_at,
        "status": "published",
        "tags": list(set(
            tags_result["technique"] + tags_result["pattern"] + tags_result["theme"] +
            tags_result["color"] + tags_result["material"]
        )),
        "images": [],
        "created_at": now,
        "updated_at": now
    }

    # 复制图片
    target_attach_dir = vault_path / "Attachments" / source
    target_attach_dir.mkdir(parents=True, exist_ok=True)

    image_entries = []
    for idx, (img_path, img_meta) in enumerate(related_images):
        new_filename = f"{itemid}_{slugify(name, lowercase=True, separator='_')}_主图{idx if idx > 0 else ''}{img_path.suffix}"
        if idx == 0:
            new_filename = f"{itemid}_{slugify(name, lowercase=True, separator='_')}_主图{img_path.suffix}"

        target_path = target_attach_dir / new_filename
        try:
            shutil.copy2(img_path, target_path)
            rel_path = str(target_path.relative_to(vault_path))
            image_entries.append({
                "path": rel_path,
                "alt": f"{name} {'主图' if idx == 0 else '细节'}",
                "is_main": idx == 0
            })
        except Exception as e:
            errors.append(f"复制图片失败 {img_path}: {e}")

    frontmatter_data["images"] = image_entries

    # 构建新 Markdown 内容
    content_lines = [f"# {name}", "", "## 描述", ""]
    if description:
        content_lines.append(description)
    else:
        content_lines.append("（暂无描述）")

    content_lines.extend(["", "## 艺术评鉴", "", "（待生成）", "", "## 数据来源", ""])
    content_lines.append(f"- **来源网站**: {source_site}")
    if source_url:
        content_lines.append(f"- **原始链接**: {source_url}")
    content_lines.append(f"- **采集时间**: {crawled_at}")
    content_lines.append(f"- **栏目**: {source}")

    content = "\n".join(content_lines)

    # 写入新笔记
    target_note_dir = vault_path / "Collections" / source
    target_note_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace('/', '_').replace('\\', '_').replace(':', '_').replace('：', '_').strip()
    new_filename = f"{itemid}_{safe_name}.md"
    target_note_path = target_note_dir / new_filename

    new_post = frontmatter.Post(content, **frontmatter_data)
    try:
        with open(target_note_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(new_post))
    except Exception as e:
        return None, [f"写入笔记失败: {e}"]

    return target_note_path, errors


def migrate(source_dir: Path, vault_path: Path, limit: Optional[int] = None, sources: Optional[List[str]] = None) -> Dict:
    """主迁移流程"""
    if not source_dir.exists():
        print(f"错误: 源目录不存在: {source_dir}")
        sys.exit(1)

    vault_path.mkdir(parents=True, exist_ok=True)

    if sources is None:
        sources = list(SOURCE_MAP.keys())

    stats = {
        "total_notes": 0,
        "migrated_notes": 0,
        "copied_images": 0,
        "errors": [],
        "by_source": {}
    }

    for source in sources:
        source_subdir = source_dir / source
        if not source_subdir.exists():
            print(f"跳过不存在的来源: {source}")
            continue

        note_files = sorted(source_subdir.glob("*.md"))
        if limit:
            note_files = note_files[:limit]

        print(f"\n处理来源 [{source}]: 找到 {len(note_files)} 个笔记")

        source_stats = {"total": len(note_files), "migrated": 0, "images": 0, "errors": []}

        for idx, note_path in enumerate(note_files, 1):
            target_path, errors = migrate_note(note_path, source, vault_path)
            stats["total_notes"] += 1
            source_stats["total"] = len(note_files)

            if target_path:
                stats["migrated_notes"] += 1
                source_stats["migrated"] += 1
                # 统计图片
                with open(target_path, "r", encoding="utf-8") as f:
                    post = frontmatter.load(f)
                    source_stats["images"] += len(post.metadata.get("images", []))
                    stats["copied_images"] += len(post.metadata.get("images", []))

            if errors:
                stats["errors"].extend([f"{note_path}: {e}" for e in errors])
                source_stats["errors"].extend(errors)

            if idx % 100 == 0:
                print(f"  已处理 {idx}/{len(note_files)}")

        stats["by_source"][source] = source_stats

    return stats


def print_stats(stats: Dict) -> None:
    """打印迁移统计"""
    print("\n" + "=" * 50)
    print("迁移完成统计")
    print("=" * 50)
    print(f"总笔记数: {stats['total_notes']}")
    print(f"成功迁移: {stats['migrated_notes']}")
    print(f"复制图片: {stats['copied_images']}")
    print(f"错误数: {len(stats['errors'])}")

    print("\n按来源统计:")
    for source, s in stats["by_source"].items():
        print(f"  {source}: 笔记 {s['migrated']}/{s['total']}, 图片 {s['images']}, 错误 {len(s['errors'])}")

    if stats["errors"]:
        print("\n=== 错误详情（前 20 条）===")
        for e in stats["errors"][:20]:
            print(f"  - {e}")


def main():
    parser = argparse.ArgumentParser(description="中国丝绸博物馆展品数据迁移脚本")
    parser.add_argument("--source", type=str, default=str(DEFAULT_SOURCE_DIR), help="源数据目录")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT), help="目标 Obsidian Vault 路径")
    parser.add_argument("--limit", type=int, default=None, help="每个来源最多迁移条数（用于测试）")
    parser.add_argument("--sources", type=str, default=None, help="指定迁移的来源，逗号分隔，如：其他，西方")

    args = parser.parse_args()

    sources = None
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",")]

    stats = migrate(
        source_dir=Path(args.source),
        vault_path=Path(args.vault),
        limit=args.limit,
        sources=sources
    )
    print_stats(stats)


if __name__ == "__main__":
    main()
