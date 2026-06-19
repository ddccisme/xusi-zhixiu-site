"""
叙思织绣知识库工具函数
"""

import re
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import yaml
from slugify import slugify


# 工艺/技术关键词
TECHNIQUE_KEYWORDS = [
    "刺绣", "缂丝", "织锦", "织金", "妆花", "蜡染", "灰缬", "绞缬", "夹缬",
    "印花", "染缬", "提花", "漳绒", "云锦", "苏绣", "苗绣", "蜀绣", "粤绣",
    "湘绣", "乱针绣", "平绣", "打籽绣", "盘金绣", "圈金绣", "钉珠", "蕾丝",
    "抽纱", "挑花", "堆绣", "贴布绣"
]

# 纹样/图案关键词
PATTERN_KEYWORDS = [
    "花卉", "龙凤", "虎头", "蝴蝶", "麒麟", "鱼", "鸟", "鹤", "鹿", "狮",
    "几何", "云纹", "如意云纹", "缠枝", "莲纹", "牡丹", "梅花", "桃花",
    "菊花", "荷花", "石榴", "葡萄", "松鼠", "喜鹊", "蝙蝠", "佛手",
    "山水", "人物", "故事", "八仙", "八宝", "暗八仙", "海水江崖", "十二章纹",
    "团窠", "联珠", "对兽", "团龙", "团凤", "云龙", "穿花龙"
]

# 题材/主题关键词
THEME_KEYWORDS = [
    "吉祥", "婚礼", "婚庆", "节庆", "祭祀", "宗教", "佛教", "道教",
    "官服", "朝服", "礼服", "日常", "民俗", "戏曲", "儿童", "寿诞",
    "祝寿", "商贸", "外销", "宫廷", "文人", "雅集"
]

# 材质关键词
MATERIAL_KEYWORDS = [
    "丝", "绸", "缎", "锦", "绢", "绫", "罗", "绮", "绵", "棉",
    "麻", "毛", "皮革", "聚酯纤维", "尼龙", "金属线", "银线", "金线",
    "棉线", "丝线", "羊毛", "羊绒", "驼绒", "羽毛"
]

# 色彩关键词
COLOR_KEYWORDS = [
    "红", "黄", "蓝", "绿", "白", "黑", "紫", "青", "粉", "橙",
    "褐", "棕", "灰", "金", "银", "多彩", "多色", "单色", "素色",
    "大红", "玫红", "宝蓝", "藏青", "石青", "月白", "米白", "鹅黄"
]


def now_str() -> str:
    """返回当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_slug(name: str, id_str: str = "") -> str:
    """生成 URL 友好的 slug"""
    base = slugify(name, lowercase=True, separator="-")
    if id_str:
        return f"{id_str}-{base}"
    return base


def parse_markdown_table(text: str, header: str = "## 基本信息") -> Dict[str, str]:
    """
    从 Markdown 文本中解析指定标题下的表格
    返回 {属性: 内容} 字典
    """
    result = {}
    if header not in text:
        return result

    section = text.split(header, 1)[1]
    # 取到下一个 ## 标题之前
    next_header = re.search(r'\n## ', section)
    if next_header:
        section = section[:next_header.start()]

    # 匹配表格行 | a | b |
    rows = re.findall(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', section, re.MULTILINE)
    for key, value in rows:
        key = key.strip().replace("**", "").strip()
        value = value.strip().replace("**", "").strip()
        if key and value and key != "属性" and key != "内容":
            result[key] = value
    return result


def extract_description(text: str) -> str:
    """提取 ## 描述 到下一个 ## 之间的内容"""
    if "## 描述" not in text:
        return ""
    section = text.split("## 描述", 1)[1]
    next_header = re.search(r'\n## ', section)
    if next_header:
        section = section[:next_header.start()]
    return section.strip()


def extract_source_info(text: str) -> Dict[str, str]:
    """提取 ## 数据来源 中的信息"""
    result = {}
    if "## 数据来源" not in text:
        return result
    section = text.split("## 数据来源", 1)[1]

    # 匹配 - **key**: value
    items = re.findall(r'-\s*\*\*(.+?)\*\*:\s*(.+)', section)
    for key, value in items:
        result[key.strip()] = value.strip()
    return result


def extract_image_links(text: str) -> List[Dict[str, str]]:
    """提取 Markdown 中的图片链接"""
    images = []
    pattern = r'!\[(.*?)\]\((.*?)\)'
    matches = re.findall(pattern, text)
    for alt, path in matches:
        images.append({
            "alt": alt.strip(),
            "path": path.strip(),
            "is_main": True
        })
    return images


def extract_tags_from_text(text: str) -> Dict[str, List[str]]:
    """
    从文本中提取候选标签
    返回 {"technique": [], "pattern": [], "theme": [], "material": [], "color": []}
    """
    result = {
        "technique": [],
        "pattern": [],
        "theme": [],
        "material": [],
        "color": []
    }

    for kw in TECHNIQUE_KEYWORDS:
        if kw in text and kw not in result["technique"]:
            result["technique"].append(kw)

    for kw in PATTERN_KEYWORDS:
        if kw in text and kw not in result["pattern"]:
            result["pattern"].append(kw)

    for kw in THEME_KEYWORDS:
        if kw in text and kw not in result["theme"]:
            result["theme"].append(kw)

    for kw in MATERIAL_KEYWORDS:
        if kw in text and kw not in result["material"]:
            result["material"].append(kw)

    for kw in COLOR_KEYWORDS:
        if kw in text and kw not in result["color"]:
            result["color"].append(kw)

    return result


def normalize_list(value: Any) -> List[str]:
    """将字符串或列表统一为字符串列表"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value.strip()] if value.strip() else []
    return []


def clean_text(text: str) -> str:
    """清理文本中的多余空白"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def get_image_dimensions(image_path: Path) -> Optional[Tuple[int, int]]:
    """获取图片尺寸"""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return None


def load_yaml_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """加载 YAML frontmatter，返回 (metadata, content)"""
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        metadata = {}

    content = parts[2].strip()
    return metadata, content


def save_yaml_frontmatter(metadata: Dict[str, Any], content: str) -> str:
    """保存 YAML frontmatter"""
    yaml_text = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_text}---\n\n{content}\n"
