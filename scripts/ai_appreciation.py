#!/usr/bin/env python3
"""
AI 艺术评鉴生成脚本

读取 Obsidian 笔记中的描述与元信息，调用 AI 生成高水平艺术评鉴，并写回笔记。
支持 Ollama（本地）、Kimi API、OpenAI API、自定义 API 等多种后端。

特性：
- 支持断点续跑（记录已处理笔记 ID）
- 支持并发请求（可配置 workers）
- 支持失败重试（默认 3 次）
- 提示词包含名称、描述、质地、年代、来源等元信息
- 生成进度实时保存到 data/appreciation_progress.json
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import frontmatter
import requests

sys.path.insert(0, str(Path(__file__).parent))
from utils import now_str

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_VAULT = PROJECT_ROOT / "kb"
PROGRESS_FILE = PROJECT_ROOT / "data" / "appreciation_progress.json"

PROMPT_TEMPLATE = """你是一位深耕中国传统织绣艺术的研究者与策展人，文笔典雅、见解独到。
请根据以下藏品信息，撰写一段 200-300 字的艺术评鉴。

藏品名称：{name}
质地/材质：{material}
年代：{era}
来源：{source}
收藏单位：{collection_unit}

藏品描述：
{description}

要求：
1. 语言优美，富有文学性与文化厚度；
2. 从工艺、纹样、色彩、历史意蕴、审美价值等角度切入；
3. 避免空话套话，要有具体观察和独到观点；
4. 保持客观，不夸大；
5. 只输出评鉴正文，不要标题、不要分点、不要"综上所述"等总结词；
6. 不要复述上述基础信息，而是基于这些信息进行艺术解读。
"""


def generate_with_ollama(prompt: str, model: str = "qwen3:0.6b", base_url: str = "http://localhost:11434") -> str:
    """使用 Ollama 本地模型生成文本"""
    url = f"{base_url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 512
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        raise RuntimeError(f"Ollama 调用失败: {e}")


def generate_with_openai_compatible(prompt: str, api_key: str, base_url: str, model: str, max_retries: int = 3) -> str:
    """使用 OpenAI 兼容 API 生成文本，支持重试"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位中国传统织绣艺术研究专家，擅长撰写典雅、专业的艺术评鉴。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 512
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"      [重试 {attempt + 1}/{max_retries}] 等待 {wait}s 后重试...")
                time.sleep(wait)
            continue
    raise RuntimeError(f"API 调用失败（重试 {max_retries} 次）: {last_error}")


def generate_with_kimi(prompt: str, api_key: str, model: str = "moonshot-v1-8k", max_retries: int = 3) -> str:
    """使用 Kimi API 生成文本"""
    return generate_with_openai_compatible(
        prompt=prompt,
        api_key=api_key,
        base_url="https://api.moonshot.cn/v1",
        model=model,
        max_retries=max_retries
    )


def load_kimi_claw_config() -> dict:
    """从本地 Kimi Claw 配置读取 API 信息"""
    claw_config_path = Path.home() / ".kimi" / "kimi-claw" / "openclaw.json"
    if not claw_config_path.exists():
        raise FileNotFoundError(f"找不到 Kimi Claw 配置文件: {claw_config_path}")
    try:
        data = json.loads(claw_config_path.read_text(encoding="utf-8"))
        provider = data["models"]["providers"]["kimi-coding"]
        model_info = provider["models"][0]
        return {
            "api_key": provider["apiKey"],
            "base_url": provider["baseUrl"],
            "model": model_info["id"],
            "headers": provider.get("headers", {}),
        }
    except Exception as e:
        raise RuntimeError(f"解析 Kimi Claw 配置失败: {e}")


def generate_with_kimi_claw(prompt: str, max_retries: int = 3) -> str:
    """使用本地 Kimi Claw 服务生成文本（Anthropic Messages API 格式）"""
    claw_config = load_kimi_claw_config()
    url = f"{claw_config['base_url'].rstrip('/')}/v1/messages"
    headers = {
        "Authorization": f"Bearer {claw_config['api_key']}",
        "Content-Type": "application/json",
        **claw_config["headers"]
    }
    payload = {
        "model": claw_config["model"],
        "max_tokens": 512,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    last_error = None
    for attempt in range(max_retries):
        start_time = time.time()
        try:
            print(f"      [KimiClaw] 请求发送 (attempt {attempt + 1}/{max_retries})...", flush=True)
            response = requests.post(url, headers=headers, json=payload, timeout=(10, 60))
            elapsed = time.time() - start_time
            print(f"      [KimiClaw] 请求返回，耗时 {elapsed:.1f}s, status={response.status_code}", flush=True)
            response.raise_for_status()
            data = response.json()
            # Anthropic 格式：content 是数组
            contents = data.get("content", [])
            texts = [item.get("text", "") for item in contents if item.get("type") == "text"]
            result = "\n".join(texts).strip()
            print(f"      [KimiClaw] 生成结果长度 {len(result)} 字", flush=True)
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            last_error = e
            print(f"      [KimiClaw] 请求失败 (attempt {attempt + 1}/{max_retries}), 耗时 {elapsed:.1f}s: {e}", flush=True)
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"      [重试 {attempt + 1}/{max_retries}] 等待 {wait}s 后重试...", flush=True)
                time.sleep(wait)
            continue
    raise RuntimeError(f"Kimi Claw 调用失败（重试 {max_retries} 次）: {last_error}")


def generate_with_openai(prompt: str, api_key: str, model: str = "gpt-4o-mini", max_retries: int = 3) -> str:
    """使用 OpenAI API 生成文本"""
    return generate_with_openai_compatible(
        prompt=prompt,
        api_key=api_key,
        base_url="https://api.openai.com/v1",
        model=model,
        max_retries=max_retries
    )


def generate_appreciation(prompt: str, provider: str, config: dict) -> str:
    """根据 provider 选择对应后端生成评鉴"""
    max_retries = config.get("max_retries", 3)

    if provider == "ollama":
        return generate_with_ollama(
            prompt,
            model=config.get("model", "qwen3:0.6b"),
            base_url=config.get("base_url", "http://localhost:11434")
        )
    elif provider == "kimi-claw":
        return generate_with_kimi_claw(
            prompt,
            max_retries=max_retries
        )
    elif provider == "kimi":
        return generate_with_kimi(
            prompt,
            api_key=config["api_key"],
            model=config.get("model", "moonshot-v1-8k"),
            max_retries=max_retries
        )
    elif provider == "openai":
        return generate_with_openai(
            prompt,
            api_key=config["api_key"],
            model=config.get("model", "gpt-4o-mini"),
            max_retries=max_retries
        )
    elif provider == "custom":
        return generate_with_openai_compatible(
            prompt,
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            max_retries=max_retries
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}")


def extract_description_from_content(content: str) -> str:
    """从 Markdown 正文中提取描述部分"""
    if "## 描述" not in content:
        return content.strip()

    section = content.split("## 描述", 1)[1]
    next_header = re.search(r'\n##\s+', section)
    if next_header:
        section = section[:next_header.start()]
    return section.strip()


def extract_appreciation_section(content: str) -> Tuple[str, str]:
    """提取当前艺术评鉴内容，返回 (当前评鉴, 是否占位)"""
    if "## 艺术评鉴" not in content:
        return "", True

    section = content.split("## 艺术评鉴", 1)[1]
    next_header = re.search(r'\n##\s+', section)
    if next_header:
        section = section[:next_header.start()]
    current = section.strip()

    is_placeholder = current in ["（待生成）", "待生成", ""]
    return current, is_placeholder


def build_prompt(post: frontmatter.Post) -> str:
    """基于笔记元信息和描述构建提示词"""
    content = post.content or ""
    description = extract_description_from_content(content)

    meta = post.metadata or {}
    name = meta.get("name", "") or meta.get("文物名称", "")
    material = meta.get("material", "") or meta.get("质地", "")
    era = meta.get("era", "") or meta.get("年代", "")
    source = meta.get("source", "") or meta.get("来源", "")
    collection_unit = meta.get("collection_unit", "") or meta.get("收藏单位", "")

    return PROMPT_TEMPLATE.format(
        name=name or "未知",
        material=material or "未知",
        era=era or "未知",
        source=source or "未知",
        collection_unit=collection_unit or "未知",
        description=description or "（暂无描述）"
    )


def load_progress() -> set:
    """加载已处理的笔记 ID 集合"""
    if not PROGRESS_FILE.exists():
        return set()
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return set(data.get("completed", []))
    except Exception:
        return set()


def save_progress(completed: set, failed: list):
    """保存处理进度"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "completed": sorted(list(completed)),
        "failed": failed,
        "updated_at": now_str()
    }
    PROGRESS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_appreciation_section(content: str, appreciation: str) -> str:
    """更新正文中的艺术评鉴章节"""
    if "## 艺术评鉴" not in content:
        return content + f"\n\n## 艺术评鉴\n\n{appreciation}\n"

    parts = content.split("## 艺术评鉴", 1)
    before = parts[0]
    after = parts[1]

    next_header = re.search(r'\n##\s+', after)
    if next_header:
        after_section = after[next_header.start():]
    else:
        after_section = ""

    return before + f"## 艺术评鉴\n\n{appreciation}\n" + after_section


def process_single_note(args_tuple) -> dict:
    """处理单个笔记，返回处理结果"""
    note_path, provider, config, dry_run = args_tuple
    note_id = note_path.stem

    result = {
        "id": note_id,
        "path": str(note_path),
        "status": "unknown",
        "error": None
    }

    try:
        post = frontmatter.load(note_path)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"解析失败: {e}"
        return result

    content = post.content or ""
    description = extract_description_from_content(content)

    if not description or description == "（暂无描述）":
        result["status"] = "skip"
        result["error"] = "描述为空"
        return result

    _, is_placeholder = extract_appreciation_section(content)
    if not is_placeholder:
        result["status"] = "skip"
        result["error"] = "已有评鉴"
        return result

    prompt = build_prompt(post)

    try:
        appreciation = generate_appreciation(prompt, provider, config)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"生成失败: {e}"
        return result

    if not appreciation:
        result["status"] = "error"
        result["error"] = "生成结果为空"
        return result

    if dry_run:
        print(f"\n  [预览] {note_path.name}\n  {'='*50}\n  {appreciation}\n  {'='*50}")
        result["status"] = "preview"
        return result

    new_content = update_appreciation_section(content, appreciation)
    post.metadata["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    post.content = new_content

    try:
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        result["status"] = "success"
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"写入失败: {e}"

    return result


def main():
    parser = argparse.ArgumentParser(description="AI 艺术评鉴生成脚本")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT), help="Obsidian Vault 路径")
    parser.add_argument("--provider", type=str, default="ollama",
                        choices=["ollama", "kimi", "kimi-claw", "openai", "custom"],
                        help="AI 提供商")
    parser.add_argument("--model", type=str, default=None, help="模型名称")
    parser.add_argument("--api-key", type=str, default=None, help="API Key（Kimi/OpenAI/custom）")
    parser.add_argument("--base-url", type=str, default=None, help="自定义 API 基础 URL 或 Ollama 地址")
    parser.add_argument("--limit", type=int, default=None, help="最多处理条数")
    parser.add_argument("--source", type=str, default=None, help="指定来源目录，如：中国历代")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写回笔记")
    parser.add_argument("--workers", type=int, default=5, help="并发请求数（默认 5）")
    parser.add_argument("--max-retries", type=int, default=3, help="单条失败重试次数（默认 3）")
    parser.add_argument("--sleep", type=float, default=0.3, help="每条请求间隔秒数（默认 0.3）")
    parser.add_argument("--no-resume", action="store_true", help="不读取进度文件，从头开始")

    args = parser.parse_args()

    vault_path = Path(args.vault)
    collections_dir = vault_path / "Collections"

    if not collections_dir.exists():
        print(f"错误: Collections 目录不存在: {collections_dir}")
        sys.exit(1)

    # 构建配置
    config = {"max_retries": args.max_retries}
    if args.model:
        config["model"] = args.model
    if args.base_url:
        config["base_url"] = args.base_url

    if args.provider in ["kimi", "openai", "custom"]:
        api_key = args.api_key or os.environ.get(f"{args.provider.upper()}_API_KEY")
        if not api_key:
            print(f"错误: 使用 {args.provider} 需要提供 --api-key 或设置 {args.provider.upper()}_API_KEY 环境变量")
            sys.exit(1)
        config["api_key"] = api_key

    # 默认模型
    if "model" not in config:
        if args.provider == "ollama":
            config["model"] = "qwen3:0.6b"
        elif args.provider == "kimi":
            config["model"] = "moonshot-v1-8k"
        elif args.provider == "openai":
            config["model"] = "gpt-4o-mini"

    # 查找笔记
    if args.source:
        note_files = list((collections_dir / args.source).glob("*.md"))
    else:
        note_files = list(collections_dir.rglob("*.md"))

    # 加载进度
    completed = set()
    if not args.no_resume:
        completed = load_progress()
        if completed:
            print(f"已加载进度，跳过 {len(completed)} 个已处理笔记")

    # 过滤已处理
    pending_files = [p for p in note_files if p.stem not in completed]

    if args.limit:
        pending_files = pending_files[:args.limit]

    print(f"扫描到 {len(note_files)} 个笔记文件，待处理 {len(pending_files)} 个")
    print(f"使用 provider: {args.provider}, model: {config.get('model')}, workers: {args.workers}")
    print(f"进度文件: {PROGRESS_FILE}\n")

    if not pending_files:
        print("没有需要处理的笔记")
        return

    success_count = 0
    skip_count = 0
    error_count = 0
    failed_notes = []

    def handle_result(idx: int, note_path: Path, result: dict):
        nonlocal success_count, skip_count, error_count
        status = result["status"]
        error_msg = result.get("error", "")

        if status == "success":
            success_count += 1
            completed.add(note_path.stem)
            print(f"[{idx}/{len(pending_files)}] ✓ {note_path.name}", flush=True)
        elif status == "skip":
            skip_count += 1
            completed.add(note_path.stem)  # 跳过的也记录，避免重复检查
            print(f"[{idx}/{len(pending_files)}] ⊘ {note_path.name}: {error_msg}", flush=True)
        elif status == "preview":
            success_count += 1
            print(f"[{idx}/{len(pending_files)}] 👁 {note_path.name} (预览)", flush=True)
        else:
            error_count += 1
            failed_notes.append({"id": note_path.stem, "path": str(note_path), "error": error_msg})
            print(f"[{idx}/{len(pending_files)}] ✗ {note_path.name}: {error_msg}", flush=True)

        # 每 10 条保存一次进度
        if idx % 10 == 0:
            save_progress(completed, failed_notes)

    if args.workers == 1:
        # 单线程顺序处理，避免后台任务中线程池异常
        print("使用单线程顺序处理模式\n", flush=True)
        for idx, note_path in enumerate(pending_files, 1):
            print(f"[{idx}/{len(pending_files)}] 开始处理 {note_path.name}", flush=True)
            result = process_single_note((note_path, args.provider, config, args.dry_run))
            handle_result(idx, note_path, result)
            if idx < len(pending_files):
                time.sleep(args.sleep)
    else:
        # 使用线程池并发处理
        print(f"使用线程池并发处理，workers={args.workers}\n", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_path = {}
            for note_path in pending_files:
                future = executor.submit(process_single_note, (note_path, args.provider, config, args.dry_run))
                future_to_path[future] = note_path
                time.sleep(args.sleep)  # 控制提交速率

            for idx, future in enumerate(as_completed(future_to_path), 1):
                note_path = future_to_path[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {"id": note_path.stem, "status": "error", "error": str(e)}
                handle_result(idx, note_path, result)

    # 最终保存进度
    save_progress(completed, failed_notes)

    print("\n=== 处理完成 ===")
    print(f"成功生成: {success_count}")
    print(f"跳过: {skip_count}")
    print(f"失败: {error_count}")
    print(f"总进度: {len(completed)}/{len(note_files)}")

    if failed_notes:
        print(f"\n失败笔记已记录到: {PROGRESS_FILE}")


if __name__ == "__main__":
    main()
