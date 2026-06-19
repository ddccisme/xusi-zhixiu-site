#!/usr/bin/env python3
"""
构建标签权重数据

用于优化搜索后的标签推荐。
输出 data/tag_weights.json，包含：
- tag_to_idx: 标签到索引的映射
- cooccurrence: 标签共现矩阵（稀疏存储）
- idf: 标签 IDF 值
- total_collections: 总藏品数
- tag_counts: 每个标签出现的藏品数
"""

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_INPUT = PROJECT_ROOT / "data" / "collections.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "tag_weights.json"


def build_weights(input_path: Path, output_path: Path):
    print(f"读取藏品数据: {input_path}")
    data = json.loads(input_path.read_text(encoding="utf-8"))
    collections = data if isinstance(data, list) else data.get("collections", [])
    print(f"总藏品数: {len(collections)}")

    # 统计每个标签出现的藏品数
    tag_df = Counter()
    # 标签共现统计
    cooccurrence = defaultdict(lambda: defaultdict(int))
    # 倒排索引：标签 -> 藏品列表
    tag_to_collections = defaultdict(set)

    for idx, item in enumerate(collections):
        tags = list(set(item.get("tags", [])))
        for tag in tags:
            tag_df[tag] += 1
            tag_to_collections[tag].add(idx)

        # 两两共现
        for i in range(len(tags)):
            for j in range(i + 1, len(tags)):
                t1, t2 = tags[i], tags[j]
                cooccurrence[t1][t2] += 1
                cooccurrence[t2][t1] += 1

    total = len(collections)
    # 计算 IDF
    idf = {}
    for tag, df in tag_df.items():
        idf[tag] = round(math.log((total + 1) / (df + 0.5)), 4)

    # 共现矩阵稀疏存储
    cooc_sparse = {}
    for t1, neighbors in cooccurrence.items():
        cooc_sparse[t1] = {t2: count for t2, count in neighbors.items()}

    # 标签索引映射
    sorted_tags = sorted(tag_df.keys())
    tag_to_idx = {tag: idx for idx, tag in enumerate(sorted_tags)}

    result = {
        "total_collections": total,
        "tag_count": len(sorted_tags),
        "tag_to_idx": tag_to_idx,
        "tag_df": dict(tag_df),
        "idf": idf,
        "cooccurrence": cooc_sparse,
        "tag_to_collections": {tag: list(indices) for tag, indices in tag_to_collections.items()},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"标签权重已保存: {output_path}")
    print(f"标签数量: {len(sorted_tags)}")


def main():
    parser = argparse.ArgumentParser(description="构建标签权重数据")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT), help="输入 collections.json 路径")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="输出 tag_weights.json 路径")
    args = parser.parse_args()

    build_weights(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
