#!/usr/bin/env python3
"""
本地搜索服务

提供 REST API：
- GET  /api/search/text?q=...
- GET  /api/search/name?q=...
- GET  /api/search/tags?tags=...
- POST /api/search/image (multipart/form-data, file=image)
- GET  /api/collections
- GET  /api/collections/{id}
- GET  /api/tags

静态文件托管根目录为项目根目录。
"""

import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path
from typing import List, Dict, Optional

import faiss
import imagehash
import numpy as np
import requests
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
from utils import now_str
import kb_admin

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"
VAULT_PATH = PROJECT_ROOT / "kb"
DB_PATH = DATA_DIR / "collections.sqlite"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
TEXT_EMBEDDING_MODEL = os.environ.get("TEXT_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
TOP_K = int(os.environ.get("TOP_K", "20"))
MAX_TOP_K = int(os.environ.get("MAX_TOP_K", "100"))
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", "10")) * 1024 * 1024  # 10MB

# 允许跨域来源：本地开发默认 localhost；生产通过环境变量配置，逗号分隔
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS if origin.strip()]

app = FastAPI(title="叙思织绣搜索服务")

# CORS：生产环境应限制为具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 加载索引
text_index = None
text_mapping = []
image_hashes = []


def load_indexes():
    """加载搜索索引"""
    global text_index, text_mapping, image_hashes

    text_index_path = DATA_DIR / "text.index"
    if text_index_path.exists():
        text_index = faiss.read_index(str(text_index_path))
        mapping_path = text_index_path.with_suffix(".mapping.json")
        with open(mapping_path, "r", encoding="utf-8") as f:
            text_mapping = json.load(f)
        print(f"加载文本索引: {len(text_mapping)} 条")

    image_hashes_path = DATA_DIR / "image_hashes.json"
    if image_hashes_path.exists():
        with open(image_hashes_path, "r", encoding="utf-8") as f:
            image_hashes = json.load(f)
        print(f"加载图片索引: {len(image_hashes)} 条")


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> Dict:
    """将数据库行转换为字典"""
    d = dict(row)
    # 解析 JSON 字段
    for field in ["technique", "pattern", "theme", "color"]:
        try:
            d[field] = json.loads(d.get(field, "[]") or "[]")
        except json.JSONDecodeError:
            d[field] = []
    return d


def get_collection_by_id(conn: sqlite3.Connection, collection_id: str) -> Dict:
    """根据 ID 获取藏品详情"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
    row = cursor.fetchone()
    if not row:
        return None

    coll = row_to_dict(row)

    # 标签
    cursor.execute("""
        SELECT t.name FROM tags t
        JOIN collection_tags ct ON t.id = ct.tag_id
        WHERE ct.collection_id = ?
    """, (collection_id,))
    coll["tags"] = [r[0] for r in cursor.fetchall()]

    # 图片
    cursor.execute("SELECT * FROM collection_images WHERE collection_id = ? ORDER BY is_main DESC", (collection_id,))
    coll["images"] = [dict(r) for r in cursor.fetchall()]

    return coll


def search_by_text_faiss(query: str, top_k: int = TOP_K) -> List[Dict]:
    """基于文本 Embedding 的语义搜索"""
    if text_index is None:
        return []

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": TEXT_EMBEDDING_MODEL, "prompt": query},
            timeout=60
        )
        resp.raise_for_status()
        vec = np.array(resp.json()["embedding"], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
    except Exception as e:
        print(f"Embedding 失败: {e}")
        return []

    vec = vec.reshape(1, -1)
    scores, indices = text_index.search(vec, min(top_k, len(text_mapping)))

    results = []
    conn = get_db_connection()
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(text_mapping):
            continue
        mapping = text_mapping[idx]
        coll = get_collection_by_id(conn, mapping["collection_id"])
        if coll:
            coll["score"] = float(score)
            results.append(coll)
    conn.close()
    return results


def search_by_name(query: str, top_k: int = TOP_K) -> List[Dict]:
    """按藏品名称模糊搜索"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM collections
        WHERE status = 'published' AND name LIKE ?
        ORDER BY name LIMIT ?
    """, (f"%{query}%", top_k))

    results = []
    for row in cursor.fetchall():
        coll = get_collection_by_id(conn, row["id"])
        if coll:
            coll["score"] = 1.0
            results.append(coll)
    conn.close()
    return results


def search_by_tags(tags: List[str], top_k: int = TOP_K) -> List[Dict]:
    """按标签搜索"""
    if not tags:
        return []

    placeholders = ",".join("?" * len(tags))
    conn = get_db_connection()
    cursor = conn.cursor()

    # 匹配标签数量越多越靠前
    cursor.execute(f"""
        SELECT c.*, COUNT(ct.tag_id) as tag_count
        FROM collections c
        JOIN collection_tags ct ON c.id = ct.collection_id
        JOIN tags t ON ct.tag_id = t.id
        WHERE c.status = 'published' AND t.name IN ({placeholders})
        GROUP BY c.id
        ORDER BY tag_count DESC, c.name
        LIMIT ?
    """, (*tags, top_k))

    results = []
    for row in cursor.fetchall():
        row_dict = dict(row)
        tag_count = row_dict.pop("tag_count", 0)
        coll = get_collection_by_id(conn, row_dict["id"])
        if coll:
            coll["score"] = tag_count / len(tags)
            results.append(coll)
    conn.close()
    return results


def search_by_image(uploaded_image_path: Path, top_k: int = TOP_K) -> List[Dict]:
    """基于 pHash 的图片相似度搜索"""
    if not image_hashes:
        return []

    try:
        query_hash = str(imagehash.phash(Image.open(uploaded_image_path)))
    except Exception as e:
        print(f"pHash 计算失败: {e}")
        return []

    # 计算汉明距离并排序
    distances = []
    for item in image_hashes:
        dist = sum(c1 != c2 for c1, c2 in zip(query_hash, item["phash"]))
        distances.append((dist, item))

    distances.sort(key=lambda x: x[0])

    results = []
    conn = get_db_connection()
    for dist, item in distances[:top_k]:
        coll = get_collection_by_id(conn, item["collection_id"])
        if coll:
            coll["score"] = max(0, 1 - dist / 64.0)
            results.append(coll)
    conn.close()
    return results


@app.on_event("startup")
def startup():
    load_indexes()


@app.get("/health")
def health():
    return {"status": "ok", "text_index": len(text_mapping), "image_index": len(image_hashes)}


def _clamp_top_k(top_k: int) -> int:
    """限制 top_k 上限，防止滥用"""
    if top_k <= 0:
        return TOP_K
    return min(top_k, MAX_TOP_K)


@app.get("/api/search/text")
def api_search_text(q: str = Query(..., description="搜索文本"), top_k: int = Query(default=TOP_K)):
    top_k = _clamp_top_k(top_k)
    results = search_by_text_faiss(q, top_k)
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/search/name")
def api_search_name(q: str = Query(..., description="藏品名称"), top_k: int = Query(default=TOP_K)):
    top_k = _clamp_top_k(top_k)
    results = search_by_name(q, top_k)
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/search/tags")
def api_search_tags(tags: str = Query(..., description="标签，逗号分隔"), top_k: int = Query(default=TOP_K)):
    top_k = _clamp_top_k(top_k)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    results = search_by_tags(tag_list, top_k)
    return {"tags": tag_list, "count": len(results), "results": results}


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@app.post("/api/search/image")
def api_search_image(file: UploadFile = File(...), top_k: int = Query(default=TOP_K)):
    top_k = _clamp_top_k(top_k)

    # 文件类型与大小校验
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        return JSONResponse(status_code=400, content={"error": f"不支持的图片格式: {suffix}"})

    content_type = file.content_type or ""
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        return JSONResponse(status_code=400, content={"error": f"不支持的文件类型: {content_type}"})

    file_bytes = file.file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        return JSONResponse(status_code=400, content={"error": "图片大小超过限制"})

    # 使用 PIL 二次校验确实是图片
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        Image.open(tmp_path).verify()
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        return JSONResponse(status_code=400, content={"error": f"无效的图片文件: {e}"})

    try:
        results = search_by_image(tmp_path, top_k)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"count": len(results), "results": results}


@app.get("/api/collections")
def api_collections(
    source: str = Query(default=None),
    category: str = Query(default=None),
    era: str = Query(default=None),
    limit: int = Query(default=100),
    offset: int = Query(default=0)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    where = ["status = 'published'"]
    params = []
    if source:
        where.append("source = ?")
        params.append(source)
    if category:
        where.append("category = ?")
        params.append(category)
    if era:
        where.append("era = ?")
        params.append(era)

    where_sql = " AND ".join(where)

    # limit <= 0 表示不限制数量
    if limit > 0:
        params.extend([limit, offset])
        cursor.execute(f"""
            SELECT * FROM collections WHERE {where_sql}
            ORDER BY name LIMIT ? OFFSET ?
        """, params)
    else:
        cursor.execute(f"""
            SELECT * FROM collections WHERE {where_sql}
            ORDER BY name
        """, params)

    results = []
    for row in cursor.fetchall():
        results.append(get_collection_by_id(conn, row["id"]))

    conn.close()
    return {"count": len(results), "results": results}


@app.get("/api/collections/{collection_id}")
def api_collection_detail(collection_id: str):
    conn = get_db_connection()
    coll = get_collection_by_id(conn, collection_id)
    conn.close()
    if not coll:
        return JSONResponse(status_code=404, content={"error": "藏品不存在"})
    return coll


@app.get("/api/tags")
def api_tags():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.*, COUNT(ct.collection_id) as count
        FROM tags t
        LEFT JOIN collection_tags ct ON t.id = ct.tag_id
        GROUP BY t.id
        ORDER BY count DESC, t.name
    """)
    tags = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"count": len(tags), "tags": tags}


# ==================== 管理后台 API ====================

class CollectionSaveRequest(BaseModel):
    metadata: Dict
    sections: Optional[Dict] = {}


class DraftCommitRequest(BaseModel):
    drafts: List[Dict]


class TagGenerateRequest(BaseModel):
    name: str
    description: str = ""
    material: str = ""
    provider: str = "ollama"
    config: Optional[Dict] = {}


@app.get("/api/admin/options")
def api_admin_options():
    """返回管理页面所需选项"""
    return {
        "sources": kb_admin.SOURCE_OPTIONS,
        "collection_types": kb_admin.COLLECTION_TYPE_OPTIONS,
        "categories": kb_admin.CATEGORY_OPTIONS,
        "status_options": kb_admin.STATUS_OPTIONS,
    }


@app.get("/api/admin/collections")
def api_admin_collections(
    q: str = Query(default=""),
    source: str = Query(default=""),
    category: str = Query(default=""),
    status: str = Query(default=""),
    tag: str = Query(default=""),
    limit: int = Query(default=50),
    offset: int = Query(default=0)
):
    """管理后台：检索已入库藏品"""
    results, total = kb_admin.list_collections(
        q=q, source=source, category=category, status=status, tag=tag,
        limit=limit, offset=offset
    )
    return {"count": len(results), "total": total, "results": results}


@app.get("/api/admin/collections/{collection_id}")
def api_admin_collection_detail(collection_id: str, source: str = Query(default="")):
    """管理后台：获取藏品详情"""
    detail = kb_admin.get_collection_detail(collection_id, source=source)
    if not detail:
        return JSONResponse(status_code=404, content={"error": "藏品不存在"})
    return detail


@app.post("/api/admin/collections/{collection_id}")
def api_admin_collection_save(collection_id: str, req: CollectionSaveRequest):
    """管理后台：保存/更新藏品"""
    data = {"metadata": req.metadata, "sections": req.sections}
    result = kb_admin.save_existing_collection(collection_id, data)
    if not result.get("saved"):
        return JSONResponse(status_code=400, content={"error": result.get("error", "保存失败")})
    return result


@app.delete("/api/admin/collections/{collection_id}")
def api_admin_collection_archive(collection_id: str, source: str = Query(default="")):
    """管理后台：归档藏品"""
    success = kb_admin.archive_collection(collection_id, source=source)
    if not success:
        return JSONResponse(status_code=404, content={"error": "藏品不存在"})
    return {"archived": True, "id": collection_id}


@app.post("/api/admin/import/preview")
def api_admin_import_preview(files: List[UploadFile] = File(...)):
    """管理后台：预览导入文件夹"""
    temp_dir = Path(tempfile.mkdtemp(prefix="kb_import_"))
    try:
        # 保存所有上传文件到临时目录，保留相对路径
        for file in files:
            rel_path = file.filename or ""
            if not rel_path:
                continue
            target_path = temp_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            content = file.file.read()
            target_path.write_bytes(content)

        drafts = kb_admin.parse_import_folder(temp_dir)
        return {
            "count": len(drafts),
            "drafts": drafts,
            "temp_dir": str(temp_dir),
        }
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": f"导入解析失败: {e}"})


@app.post("/api/admin/import/commit")
def api_admin_import_commit(req: DraftCommitRequest):
    """管理后台：确认导入草稿"""
    # 需要从请求中恢复临时目录
    # 这里简化：前端提交 drafts 时一并提交 temp_dir
    # 但为了安全，temp_dir 应通过其他方式传递，例如 preview 返回 temp_dir，commit 时再传回
    # 本次实现：前端将 temp_dir 放在第一个 draft 的 _temp_dir 中
    if not req.drafts:
        return JSONResponse(status_code=400, content={"error": "没有要保存的草稿"})

    temp_dir_str = req.drafts[0].get("_temp_dir", "")
    temp_dir = Path(temp_dir_str) if temp_dir_str else None

    saved = []
    errors = []
    for draft in req.drafts:
        try:
            result = kb_admin.save_draft(draft, temp_dir=temp_dir or Path(tempfile.gettempdir()))
            saved.append(result)
        except Exception as e:
            errors.append({"draft_id": draft.get("draft_id"), "error": str(e)})

    # 清理临时目录
    if temp_dir and temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {"saved": saved, "errors": errors, "count": len(saved)}


@app.post("/api/admin/images/upload")
def api_admin_image_upload(
    file: UploadFile = File(...),
    source: str = Form(...),
    id: str = Form(default=""),
    name: str = Form(default=""),
    role: str = Form(default="图")
):
    """管理后台：上传单张图片到 Attachments"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        return JSONResponse(status_code=400, content={"error": f"不支持的图片格式: {suffix}"})

    content_type = file.content_type or ""
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        return JSONResponse(status_code=400, content={"error": f"不支持的文件类型: {content_type}"})

    file_bytes = file.file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        return JSONResponse(status_code=400, content={"error": "图片大小超过限制"})

    attach_dir = kb_admin.ATTACHMENTS_DIR / source
    attach_dir.mkdir(parents=True, exist_ok=True)

    if id and name:
        filename = kb_admin.image_filename(id, name, role, suffix)
    else:
        filename = f"{uuid.uuid4().hex[:12]}_{role}{suffix}"

    target_path = attach_dir / filename
    target_path.write_bytes(file_bytes)

    dims = kb_admin.get_image_dimensions(target_path)
    return {
        "path": f"Attachments/{source}/{filename}",
        "filename": filename,
        "alt": role,
        "is_main": False,
        "width": dims[0] if dims else None,
        "height": dims[1] if dims else None,
        "file_size": target_path.stat().st_size,
    }


@app.post("/api/admin/tags/generate")
def api_admin_tags_generate(req: TagGenerateRequest):
    """管理后台：生成标签"""
    rule_tags = kb_admin.generate_tags_by_rules(req.name, req.description, req.material)
    ai_tags = kb_admin.generate_tags_by_ai(req.name, req.description, req.material, req.provider, req.config)
    merged = kb_admin.merge_tags(rule_tags, ai_tags)
    return merged


@app.post("/api/admin/build")
def api_admin_build(full: bool = Query(default=True)):
    """管理后台：重建数据库与 JSON"""
    result = kb_admin.run_build_kb(full=full)
    return result


@app.post("/api/admin/build/vectors")
def api_admin_build_vectors():
    """管理后台：重建向量索引"""
    result = kb_admin.run_build_vectors()
    return result


# 静态文件托管：仅暴露前端页面与 assets，不暴露 data、scripts、.venv 等敏感目录
static_dir = PROJECT_ROOT / "__static__"
if static_dir.exists():
    import shutil
    shutil.rmtree(static_dir)
static_dir.mkdir(exist_ok=True)

import os

# 符号链接前端页面，便于开发时实时反映修改
for html_file in PROJECT_ROOT.glob("*.html"):
    if html_file.name.startswith("_"):
        continue
    dst = static_dir / html_file.name
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    os.symlink(html_file.resolve(), dst)

# 创建 assets 符号链接
assets_src = PROJECT_ROOT / "assets"
assets_dst = static_dir / "assets"
if assets_src.exists() and not assets_dst.exists():
    os.symlink(assets_src.resolve(), assets_dst, target_is_directory=True)

# 创建 kb/Attachments 符号链接，兼容前端 ./kb/Attachments/... 路径
kb_dir = static_dir / "kb"
kb_dir.mkdir(exist_ok=True)
attachments_src = PROJECT_ROOT / "kb" / "Attachments"
attachments_dst = kb_dir / "Attachments"
if attachments_src.exists() and not attachments_dst.exists():
    os.symlink(attachments_src.resolve(), attachments_dst, target_is_directory=True)

# 暴露标签权重文件（不暴露整个 data 目录）
data_dir_static = static_dir / "data"
data_dir_static.mkdir(exist_ok=True)
tag_weights_src = PROJECT_ROOT / "data" / "tag_weights.json"
tag_weights_dst = data_dir_static / "tag_weights.json"
if tag_weights_src.exists() and not tag_weights_dst.exists():
    os.symlink(tag_weights_src.resolve(), tag_weights_dst)

app.mount("/", StaticFiles(directory=str(static_dir), html=True, follow_symlink=True), name="static")


def main():
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
