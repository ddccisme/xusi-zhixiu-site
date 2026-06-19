# 叙思织绣藏品知识库

本知识库是叙思织绣网站的唯一内容源，使用 Obsidian 管理藏品笔记，通过构建脚本同步到 SQLite 数据库与静态 JSON，供网站读取与搜索。

## 目录结构

```
kb/
├── README.md                 # 本文件
├── Templates/                # 新建藏品笔记的模板
│   ├── 文物模板.md
│   ├── 自营藏品模板.md
│   └── 当代创作模板.md
├── Collections/              # 藏品 Markdown 笔记
│   ├── 中国历代/
│   ├── 中国当代/
│   ├── 西方/
│   ├── 民族学/
│   ├── 其他/
│   ├── 自营藏品/
│   └── 当代创作/
└── Attachments/              # 藏品图片附件
    ├── 中国历代/
    ├── 中国当代/
    ├── 西方/
    ├── 民族学/
    ├── 其他/
    ├── 自营藏品/
    └── 当代创作/
```

## 新增藏品流程

1. 根据藏品类型选择对应目录
2. 使用 Obsidian 模板新建笔记（快捷键：Ctrl/Cmd + P → Templater）
3. 填写 YAML frontmatter 与正文
4. 将图片放入对应 `Attachments/{source}/` 目录
5. 在 frontmatter 的 `images` 字段引用图片路径
6. 保存笔记后，运行构建脚本同步到数据库

```bash
cd /Users/andy_dongcheng/Desktop/DC_WORK/WORKSPACE/16_文娱产业项目/00_web
source .venv/bin/activate
python scripts/build_kb.py
```

## 笔记命名规范

```
{唯一ID}_{藏品名称}.md
```

- 从中国丝绸博物馆迁移来的文物，ID 使用原 `itemid`
- 自营藏品与当代创作，ID 使用短英文 slug 或自动生成的 UUID
- 示例：`2969_五彩绸缎圈金绣虎头钱袋.md`、`laoshucantian_老树参天像景.md`

## YAML Frontmatter 字段说明

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `id` | 是 | 唯一标识符 | `"2969"` |
| `name` | 是 | 藏品名称 | `"五彩绸缎圈金绣虎头钱袋"` |
| `slug` | 是 | URL 友好标识 | `"wucai-chouduan-quanjinxiu-hutou-qiandai"` |
| `collection_type` | 是 | 藏品大类 | `文物展示 / 自营产品 / 当代创作` |
| `source` | 是 | 来源分类 | `中国历代 / 中国当代 / 西方 / 民族学 / 其他` |
| `category` | 是 | 类型 | `织物 / 服装 / 工艺品 / 配饰 / 家纺 / 其他` |
| `technique` | 否 | 工艺/技术标签 | `["刺绣", "圈金绣"]` |
| `pattern` | 否 | 纹样/图案标签 | `["虎头", "五彩"]` |
| `theme` | 否 | 题材标签 | `["吉祥", "婚礼"]` |
| `material` | 否 | 质地 | `"丝"` |
| `era` | 否 | 年代 | `"清代"` |
| `dynasty` | 否 | 朝代 | `"清"` |
| `size` | 否 | 尺寸 | `"长：9.5 宽：17"` |
| `color` | 否 | 颜色 | `["多色"]` |
| `quantity` | 否 | 数量 | `"1件"` |
| `collection_unit` | 否 | 收藏单位 | `"中国丝绸博物馆"` |
| `author` | 否 | 作者 | `"未知"` |
| `level` | 否 | 级别 | `"未知"` |
| `origin` | 否 | 来源 | `"未知"` |
| `source_url` | 否 | 原始链接 | `"https://www.chinasilkmuseum.com/..."` |
| `source_site` | 否 | 来源网站 | `"中国丝绸博物馆"` |
| `crawled_at` | 否 | 采集时间 | `"2026-06-13"` |
| `status` | 是 | 状态 | `published / draft / archived` |
| `tags` | 否 | 通用标签 | `["钱袋", "虎头"]` |
| `images` | 否 | 图片列表 | 见下方格式 |
| `created_at` | 是 | 创建时间 | `"2026-06-19"` |
| `updated_at` | 是 | 更新时间 | `"2026-06-19"` |

### 图片字段格式

```yaml
images:
  - path: "Attachments/中国历代/2969_五彩绸缎圈金绣虎头钱袋_主图.jpg"
    alt: "五彩绸缎圈金绣虎头钱袋主图"
    is_main: true
  - path: "Attachments/中国历代/2969_五彩绸缎圈金绣虎头钱袋_细节.jpg"
    alt: "虎头细节"
    is_main: false
```

## Markdown 正文结构

```markdown
# {藏品名称}

## 描述

{藏品描述，包含形制、工艺、纹样、历史背景等}

## 艺术评鉴

{由 AI 基于描述生成，可人工编辑覆盖}

## 数据来源

- **来源网站**: {网站名}
- **原始链接**: {URL}
- **采集时间**: {YYYY-MM-DD}
- **栏目**: {source}
```

## 标签使用规范

- **工艺**：刺绣、缂丝、织锦、蜡染、印花、染缬、妆花、织金、灰缬、绞缬、夹缬
- **纹样**：花卉、龙凤、虎头、蝴蝶、几何、云纹、山水、人物、鸟兽
- **题材**：吉祥、婚礼、节庆、宗教、官服、民俗、日常
- **材质**：丝、棉、麻、毛、聚酯纤维、金属线
- **色彩**：单色、多色、红、蓝、绿、黄、黑、白

新增标签时尽量使用已有词汇，避免同义重复。

## 图片管理规范

1. 所有图片统一放入 `Attachments/{source}/`
2. 命名格式：`{id}_{藏品名称}_主图.jpg`
3. 主图分辨率建议不低于 800×800 像素
4. 支持格式：jpg、png、gif、webp
5. 图片替代文本 `alt` 必须填写，用于可访问性与搜索

## 构建脚本

```bash
# 增量构建（推荐）
python scripts/build_kb.py

# 完整重建
python scripts/build_kb.py --full

# 仅校验笔记格式
python scripts/build_kb.py --validate
```

构建产物：
- `data/collections.sqlite`：结构化数据库
- `data/collections.json`：藏品数据 JSON
- `data/tags.json`：标签索引 JSON

## 常见问题

**Q：修改笔记后如何同步到网站？**
A：保存笔记后运行 `python scripts/build_kb.py` 即可。

**Q：能否直接修改 SQLite 数据库？**
A：不建议。应以 Obsidian 笔记为唯一内容源，数据库由脚本生成。

**Q：图片路径写错会怎样？**
A：构建脚本会记录 warning，该藏品图片字段为空，但不会中断构建。

**Q：如何删除藏品？**
A：将 `status` 改为 `archived`，或删除笔记后运行 `--full` 构建。
