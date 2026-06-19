#!/usr/bin/env python3
"""
叙思织绣知识库管理后端

提供知识库管理页面的核心逻辑：
- 解析上传文件夹为草稿
- Markdown 文件读写
- 图片移动与重命名
- 标签生成（规则 + AI）
- 藏品搜索、详情、保存、归档
- 调用构建脚本同步数据
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import frontmatter
import yaml
from slugify import slugify

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    extract_tags_from_text,
    get_image_dimensions,
    normalize_list,
    safe_slug,
)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
VAULT_PATH = PROJECT_ROOT / "kb"
COLLECTIONS_DIR = VAULT_PATH / "Collections"
ATTACHMENTS_DIR = VAULT_PATH / "Attachments"
TEMPLATES_DIR = VAULT_PATH / "Templates"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "collections.sqlite"

# 来源与分类选项
SOURCE_OPTIONS = ["中国历代", "中国当代", "西方", "民族学", "其他", "自营藏品", "当代创作"]
COLLECTION_TYPE_OPTIONS = ["文物展示", "自营产品", "当代创作"]
# 与 build_kb.py VALID_CATEGORIES 保持一致（去重后）
_ALL_CATEGORIES = sorted(set([
    "织物", "服装", "工艺品", "配饰", "家纺", "其他",
    "大师服装", "新秀服装", "品牌服饰", "面料", "图案手稿",
    "古董刺绣", "收藏级织物", "名家古董商专区",
    "艺术家合作", "文化创作", "展览", "活动", "服饰系列", "文创周边"
]))
CATEGORY_OPTIONS = {s: _ALL_CATEGORIES for s in SOURCE_OPTIONS}
STATUS_OPTIONS = ["published", "draft", "archived"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def ensure_dirs():
    """确保知识库目录存在"""
    for source in SOURCE_OPTIONS:
        (COLLECTIONS_DIR / source).mkdir(parents=True, exist_ok=True)
        (ATTACHMENTS_DIR / source).mkdir(parents=True, exist_ok=True)


def load_template(template_name: str) -> Dict[str, Any]:
    """加载 Obsidian 模板作为默认值"""
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        return {}
    try:
        post = frontmatter.load(template_path)
        return post.metadata or {}
    except Exception:
        return {}


# 模板映射
def get_template_for(source: str, collection_type: str = "") -> Dict[str, Any]:
    if collection_type == "自营产品" or source in ("自营藏品", "当代创作"):
        if source == "当代创作":
            return load_template("当代创作模板.md")
        return load_template("自营藏品模板.md")
    return load_template("文物模板.md")


def parse_note_file(note_path: Path) -> Optional[frontmatter.Post]:
    """解析单个 Markdown 笔记"""
    try:
        return frontmatter.load(note_path)
    except Exception as e:
        print(f"解析笔记失败 {note_path}: {e}")
        return None


def extract_sections(content: str) -> Dict[str, str]:
    """提取 Markdown 正文中的章节"""
    sections = {}
    pattern = re.compile(r'^##\s+(.+?)\s*\n', re.MULTILINE)
    matches = list(pattern.finditer(content))
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections[title] = content[start:end].strip()
    return sections


def build_content_from_sections(sections: Dict[str, str], name: str) -> str:
    """根据章节字典重建 Markdown 正文"""
    lines = [f"# {name}", ""]
    for title in ["描述", "艺术评鉴", "创作理念", "藏品故事", "展览/活动信息", "数据来源"]:
        if title in sections and sections[title].strip():
            lines.append(f"## {title}")
            lines.append("")
            lines.append(sections[title].strip())
            lines.append("")
    return "\n".join(lines)


def normalize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """规范化 frontmatter 字段"""
    meta = dict(meta)
    # 字符串列表字段
    for key in ["technique", "pattern", "theme", "color", "tags"]:
        meta[key] = normalize_list(meta.get(key, []))
    # 字符串字段
    for key in ["name", "slug", "collection_type", "source", "category", "sub_category",
                "material", "era", "dynasty", "size", "quantity", "collection_unit",
                "author", "level", "origin", "source_url", "source_site", "crawled_at", "status"]:
        meta[key] = str(meta.get(key, "")) if meta.get(key) is not None else ""
    # 图片字段
    images = meta.get("images", [])
    if not isinstance(images, list):
        images = []
    normalized_images = []
    for img in images:
        if isinstance(img, dict):
            normalized_images.append({
                "path": str(img.get("path", "")),
                "alt": str(img.get("alt", "")),
                "is_main": bool(img.get("is_main", False))
            })
    meta["images"] = normalized_images
    if not meta.get("status"):
        meta["status"] = "published"
    if not meta.get("created_at"):
        meta["created_at"] = now_str()
    if not meta.get("updated_at"):
        meta["updated_at"] = now_str()
    return meta


def generate_id(name: str) -> str:
    """生成唯一短 ID"""
    base = slugify(name, lowercase=True, separator="-")[:20] or "item"
    timestamp = datetime.now().strftime("%y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{base}-{timestamp}-{suffix}"


def note_filename(id_str: str, name: str) -> str:
    """生成笔记文件名"""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return f"{id_str}_{safe_name}.md"


def image_filename(id_str: str, name: str, role: str, suffix: str) -> str:
    """生成图片文件名"""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    safe_role = re.sub(r'[\\/:*?"<>|]', "_", role).strip() or "图"
    return f"{id_str}_{safe_name}_{safe_role}{suffix}"


def match_images_by_prefix(files: List[Path], id_str: str, name: str) -> List[Dict[str, Any]]:
    safe_name = re.sub(r'[\\/:*?\"<>|]', '_', name).strip()
    prefix = f"{id_str}_{safe_name}"
    matched = []
    for f in files:
        if f.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        stem = f.stem
        if stem.startswith(prefix):
            role = stem[len(prefix):].lstrip("_") or "图"
            matched.append({
                "filename": f.name,
                "role": role,
                "alt": role,
                "is_main": role == "主图" or "main" in role.lower(),
            })
    # 排序：主图在前，其余按文件名
    matched.sort(key=lambda x: (not x["is_main"], x["filename"]))
    return matched


def parse_import_folder(temp_dir: Path) -> List[Dict[str, Any]]:
    """解析上传的临时文件夹，返回草稿列表"""
    ensure_dirs()
    md_files = list(temp_dir.rglob("*.md"))
    image_files = []
    for suffix in IMAGE_SUFFIXES:
        image_files.extend(temp_dir.rglob(f"*{suffix}"))
        image_files.extend(temp_dir.rglob(f"*{suffix.upper()}"))

    # 去重
    image_files = list({f: f for f in image_files}.values())

    drafts = []
    all_image_files = image_files

    for md_path in md_files:
        post = parse_note_file(md_path)
        if not post:
            continue

        meta = normalize_metadata(post.metadata or {})
        sections = extract_sections(post.content or "")

        # 确定 id 和 name
        id_str = str(meta.get("id", "")).strip()
        name = str(meta.get("name", "")).strip() or md_path.stem
        if not id_str:
            id_str = generate_id(name)
            meta["id"] = id_str
        if not meta.get("name"):
            meta["name"] = name
        if not meta.get("slug"):
            meta["slug"] = safe_slug(name, id_str)

        source = meta.get("source", "")
        if source not in SOURCE_OPTIONS:
            source = "其他"
            meta["source"] = source

        # 图片匹配：frontmatter 优先，缺失时按前缀
        images = meta.get("images", [])
        matched_by_name = False
        if images:
            # 验证 frontmatter 中的图片是否存在
            valid_images = []
            for img in images:
                img_path = temp_dir / Path(img.get("path", "")).name
                if not img_path.exists():
                    # 尝试在临时目录任意位置查找
                    candidates = [f for f in image_files if f.name == Path(img.get("path", "")).name]
                    if candidates:
                        img_path = candidates[0]
                    else:
                        continue
                valid_images.append({
                    "filename": img_path.name,
                    "role": Path(img.get("path", "")).stem.split("_")[-1] if "_" in Path(img.get("path", "")).stem else "图",
                    "alt": img.get("alt", "") or img_path.stem,
                    "is_main": bool(img.get("is_main", False)),
                })
            if valid_images:
                matched_by_name = True
            images = valid_images

        if not images:
            images = match_images_by_prefix(all_image_files, id_str, name)

        # 如果没有匹配到，也尝试按文件名前缀忽略 ID
        if not images:
            name_only_prefix = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
            for f in all_image_files:
                if f.stem.startswith(name_only_prefix):
                    role = f.stem[len(name_only_prefix):].lstrip("_") or "图"
                    images.append({
                        "filename": f.name,
                        "role": role,
                        "alt": role,
                        "is_main": role == "主图",
                    })

        # 警告信息
        warnings = []
        if not meta.get("description") and not sections.get("描述"):
            warnings.append("缺少描述")
        if not meta.get("category"):
            warnings.append("未设置分类")
        if not images:
            warnings.append("未识别到图片")
        if not meta.get("era") and not meta.get("dynasty"):
            warnings.append("未识别到年代/朝代")

        drafts.append({
            "draft_id": str(uuid.uuid4()),
            "id": id_str,
            "name": name,
            "source": source,
            "metadata": meta,
            "sections": sections,
            "images": images,
            "md_filename": md_path.name,
            "warnings": warnings,
            "exists": False,
        })

    # 检测已存在
    for draft in drafts:
        target_dir = COLLECTIONS_DIR / draft["source"]
        target_path = target_dir / note_filename(draft["id"], draft["name"])
        draft["exists"] = target_path.exists()
        if draft["exists"]:
            draft["warnings"].insert(0, "已存在，保存将覆盖")

    return drafts


def generate_tags_by_rules(name: str, description: str, material: str = "") -> Dict[str, List[str]]:
    """基于规则生成标签"""
    text = f"{name} {description} {material}"
    return extract_tags_from_text(text)


def generate_tags_by_ai(name: str, description: str, material: str = "", provider: str = "ollama", config: Optional[Dict] = None) -> List[str]:
    """基于 AI 生成通用标签"""
    try:
        from ai_appreciation import generate_appreciation
    except ImportError:
        return []

    prompt = f"""请为以下织绣藏品生成 5-10 个中文标签，用于网站检索与分类。
标签应涵盖：工艺、纹样、材质、色彩、题材。
仅输出标签列表，用中文逗号分隔，不要解释。

藏品名称：{name}
质地/材质：{material or '未知'}
藏品描述：{description or '暂无描述'}
"""
    try:
        result = generate_appreciation(prompt, provider, config or {})
        # 解析逗号分隔的标签
        tags = [t.strip() for t in re.split(r'[，,、\n]', result) if t.strip()]
        return tags[:15]
    except Exception as e:
        print(f"AI 标签生成失败: {e}")
        return []


def merge_tags(rule_tags: Dict[str, List[str]], ai_tags: List[str]) -> Dict[str, Any]:
    """合并规则标签与 AI 标签"""
    all_tags = set()
    for key in ["technique", "pattern", "theme", "material", "color"]:
        all_tags.update(rule_tags.get(key, []))
    all_tags.update(ai_tags)

    return {
        "technique": rule_tags.get("technique", []),
        "pattern": rule_tags.get("pattern", []),
        "theme": rule_tags.get("theme", []),
        "material": rule_tags.get("material", []),
        "color": rule_tags.get("color", []),
        "tags": sorted(list(all_tags)),
        "ai_tags": ai_tags,
    }


def save_draft(draft: Dict[str, Any], temp_dir: Path, backup: bool = True) -> Dict[str, Any]:
    """将草稿保存到知识库"""
    ensure_dirs()
    meta = normalize_metadata(draft.get("metadata", {}))
    sections = draft.get("sections", {})
    name = meta.get("name", "未命名")
    id_str = meta.get("id", generate_id(name))
    source = meta.get("source", "其他")

    if source not in SOURCE_OPTIONS:
        source = "其他"
        meta["source"] = source

    target_dir = COLLECTIONS_DIR / source
    attach_dir = ATTACHMENTS_DIR / source
    target_dir.mkdir(parents=True, exist_ok=True)
    attach_dir.mkdir(parents=True, exist_ok=True)

    # 处理图片
    new_images = []
    images = draft.get("images", [])
    for idx, img in enumerate(images):
        filename = img.get("filename", "")
        if not filename:
            continue
        src_path = temp_dir / filename
        # 如果临时目录找不到，尝试在 attach_dir 找（已保存过的图片）
        if not src_path.exists():
            src_path = attach_dir / filename
        if not src_path.exists():
            continue

        role = img.get("role") or ("主图" if idx == 0 else f"细节{idx}")
        new_filename = image_filename(id_str, name, role, src_path.suffix.lower())
        dst_path = attach_dir / new_filename

        # 备份原文件（如果目标已存在）
        if backup and dst_path.exists():
            backup_path = dst_path.with_suffix(dst_path.suffix + ".bak")
            shutil.copy2(dst_path, backup_path)

        shutil.copy2(src_path, dst_path)

        # 图片尺寸
        dims = get_image_dimensions(dst_path)

        new_images.append({
            "path": f"Attachments/{source}/{new_filename}",
            "alt": img.get("alt", role) or role,
            "is_main": img.get("is_main", False) if "is_main" in img else (idx == 0),
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
            "file_size": dst_path.stat().st_size if dst_path.exists() else 0,
        })

    # 确保有且仅有一个主图
    if new_images:
        has_main = any(img.get("is_main") for img in new_images)
        if not has_main:
            new_images[0]["is_main"] = True
        # 其他设为非主图
        for img in new_images:
            if img is not new_images[0] and not has_main:
                img["is_main"] = False

    meta["images"] = [{"path": img["path"], "alt": img["alt"], "is_main": img["is_main"]} for img in new_images]
    meta["updated_at"] = now_str()

    # 描述与艺术评鉴写入正文
    if "描述" not in sections or not sections["描述"].strip():
        sections["描述"] = meta.get("description", "（暂无描述）")
    if "艺术评鉴" not in sections:
        sections["艺术评鉴"] = meta.get("appreciation", "（待生成）")

    # 移除 meta 中的 description 和 appreciation（它们存储在正文中）
    meta.pop("description", None)
    meta.pop("appreciation", None)

    content = build_content_from_sections(sections, name)

    # 数据来源章节
    if "数据来源" not in sections:
        source_lines = [
            "- **来源网站**: " + (meta.get("source_site") or "叙思织绣"),
            "- **原始链接**: " + (meta.get("source_url") or ""),
            "- **采集时间**: " + (meta.get("crawled_at") or now_str()),
            f"- **栏目**: {source}",
        ]
        content += "\n## 数据来源\n\n" + "\n".join(source_lines) + "\n"

    # 保存 Markdown
    post = frontmatter.Post(content, **meta)
    note_path = target_dir / note_filename(id_str, name)

    if backup and note_path.exists():
        backup_path = note_path.with_suffix(note_path.suffix + ".bak")
        shutil.copy2(note_path, backup_path)

    note_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    return {
        "id": id_str,
        "name": name,
        "source": source,
        "note_path": str(note_path.relative_to(PROJECT_ROOT)),
        "images": new_images,
        "saved": True,
    }


def archive_collection(id_str: str, source: str) -> bool:
    """归档藏品：将 status 改为 archived"""
    if source:
        search_dirs = [COLLECTIONS_DIR / source]
    else:
        search_dirs = [COLLECTIONS_DIR / s for s in SOURCE_OPTIONS if (COLLECTIONS_DIR / s).exists()]

    note_path = None
    for dir_path in search_dirs:
        candidates = list(dir_path.glob(f"{id_str}_*.md"))
        if candidates:
            note_path = candidates[0]
            break

    if not note_path:
        return False
    try:
        post = frontmatter.load(note_path)
        post.metadata["status"] = "archived"
        post.metadata["updated_at"] = now_str()
        note_path.write_text(frontmatter.dumps(post), encoding="utf-8")
        return True
    except Exception as e:
        print(f"归档失败 {note_path}: {e}")
        return False


def list_collections(
    q: str = "",
    source: str = "",
    category: str = "",
    status: str = "",
    tag: str = "",
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """列出已入库藏品"""
    results = []
    search_dirs = [COLLECTIONS_DIR / s for s in SOURCE_OPTIONS if (COLLECTIONS_DIR / s).exists()]

    for dir_path in search_dirs:
        if source and dir_path.name != source:
            continue
        for md_path in sorted(dir_path.glob("*.md")):
            post = parse_note_file(md_path)
            if not post:
                continue
            meta = normalize_metadata(post.metadata or {})

            # 状态筛选
            if status and meta.get("status") != status:
                continue
            # 分类筛选
            if category and meta.get("category") != category:
                continue
            # 标签筛选
            if tag and tag not in meta.get("tags", []):
                continue
            # 关键词筛选
            if q:
                text = f"{meta.get('id', '')} {meta.get('name', '')} {meta.get('description', '')} {' '.join(meta.get('tags', []))}"
                if q.lower() not in text.lower():
                    continue

            sections = extract_sections(post.content or "")
            main_image = None
            for img in meta.get("images", []):
                if img.get("is_main"):
                    main_image = img
                    break
            if not main_image and meta.get("images"):
                main_image = meta["images"][0]

            results.append({
                "id": meta.get("id", ""),
                "name": meta.get("name", ""),
                "slug": meta.get("slug", ""),
                "source": meta.get("source", ""),
                "category": meta.get("category", ""),
                "status": meta.get("status", ""),
                "era": meta.get("era", ""),
                "collection_unit": meta.get("collection_unit", ""),
                "tags": meta.get("tags", []),
                "main_image": main_image,
                "description": sections.get("描述", "（暂无描述）"),
                "updated_at": meta.get("updated_at", ""),
                "note_path": str(md_path.relative_to(PROJECT_ROOT)),
            })

    total = len(results)
    return results[offset:offset + limit], total


def get_collection_detail(id_str: str, source: str = "") -> Optional[Dict[str, Any]]:
    """获取藏品详情"""
    if source and source in SOURCE_OPTIONS:
        search_dirs = [COLLECTIONS_DIR / source]
    else:
        search_dirs = [COLLECTIONS_DIR / s for s in SOURCE_OPTIONS if (COLLECTIONS_DIR / s).exists()]

    for dir_path in search_dirs:
        candidates = list(dir_path.glob(f"{id_str}_*.md"))
        if candidates:
            note_path = candidates[0]
            post = parse_note_file(note_path)
            if not post:
                return None
            meta = normalize_metadata(post.metadata or {})
            sections = extract_sections(post.content or "")
            return {
                "metadata": meta,
                "sections": sections,
                "note_path": str(note_path.relative_to(PROJECT_ROOT)),
            }
    return None


def save_existing_collection(id_str: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """保存已存在的藏品，支持来源变更时自动移动文件"""
    metadata = data.get("metadata", {})
    new_source = metadata.get("source") or data.get("source", "其他")
    if new_source not in SOURCE_OPTIONS:
        new_source = "其他"
        metadata["source"] = new_source

    # 在所有来源目录中查找现有笔记
    note_path = None
    old_source = ""
    for src in SOURCE_OPTIONS:
        candidates = list((COLLECTIONS_DIR / src).glob(f"{id_str}_*.md"))
        if candidates:
            note_path = candidates[0]
            old_source = src
            break

    if not note_path:
        return {"saved": False, "error": "藏品不存在"}

    post = parse_note_file(note_path)
    if not post:
        return {"saved": False, "error": "笔记解析失败"}

    new_meta = normalize_metadata(metadata)
    new_meta["created_at"] = post.metadata.get("created_at", now_str())
    new_meta["updated_at"] = now_str()

    name = new_meta.get("name", post.metadata.get("name", "未命名"))

    # 来源变更时，移动图片到新的 Attachments 目录并更新路径
    old_attach_dir = ATTACHMENTS_DIR / old_source if old_source else None
    new_attach_dir = ATTACHMENTS_DIR / new_source
    new_attach_dir.mkdir(parents=True, exist_ok=True)

    images = new_meta.get("images", [])
    normalized_images = []
    for img in images:
        if not isinstance(img, dict):
            continue
        path = str(img.get("path", ""))
        if old_source and old_source != new_source and path.startswith(f"Attachments/{old_source}/"):
            old_img_path = PROJECT_ROOT / path
            filename = Path(path).name
            new_path_rel = f"Attachments/{new_source}/{filename}"
            new_img_path = PROJECT_ROOT / new_path_rel
            if old_img_path.exists() and old_img_path != new_img_path:
                if new_img_path.exists():
                    backup_path = new_img_path.with_suffix(new_img_path.suffix + ".bak")
                    shutil.copy2(new_img_path, backup_path)
                shutil.move(str(old_img_path), str(new_img_path))
            path = new_path_rel
        normalized_images.append({
            "path": path,
            "alt": str(img.get("alt", "")),
            "is_main": bool(img.get("is_main", False))
        })
    new_meta["images"] = normalized_images

    sections = data.get("sections", extract_sections(post.content or ""))
    if "描述" not in sections:
        sections["描述"] = "（暂无描述）"
    if "艺术评鉴" not in sections:
        sections["艺术评鉴"] = "（待生成）"

    new_meta.pop("description", None)
    new_meta.pop("appreciation", None)

    content = build_content_from_sections(sections, name)

    new_target_dir = COLLECTIONS_DIR / new_source
    new_target_dir.mkdir(parents=True, exist_ok=True)
    new_note_path = new_target_dir / note_filename(id_str, name)

    new_post = frontmatter.Post(content, **new_meta)
    new_note_path.write_text(frontmatter.dumps(new_post), encoding="utf-8")

    if new_note_path != note_path and note_path.exists():
        note_path.unlink()

    return {
        "saved": True,
        "id": id_str,
        "name": name,
        "note_path": str(new_note_path.relative_to(PROJECT_ROOT)),
    }


def run_build_kb(full: bool = True) -> Dict[str, Any]:
    """调用 build_kb.py"""
    try:
        cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "build_kb.py")]
        if full:
            cmd.append("--full")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "构建超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_build_vectors() -> Dict[str, Any]:
    """调用 build_vectors.py"""
    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "build_vectors.py")],
            capture_output=True, text=True, timeout=1800
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "向量构建超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # 简单测试
    print("kb_admin 模块加载成功")
    print("来源选项:", SOURCE_OPTIONS)
