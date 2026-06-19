# 叙思织绣独立站

传统织绣文化 × 前沿智能技术的文创电商独立站。

## 项目结构

```
00_web/
├── index.html                  # 主页面
├── search.html                 # 藏品检索页
├── detail.html                 # 藏品详情页（动态）
├── detail-laoshucantian.html   # 藏品详情页示例
├── PRD.md                      # 产品需求文档
├── README.md                   # 项目说明
├── USER_STORIES.md             # 用户故事
├── implementation_plan.md      # 详细实施计划
├── PROJECT_STATUS.md           # 项目当前状态
├── PROJECT_ISSUES.md           # 项目问题与风险
├── assets/                     # 静态资源
│   ├── style.css               # 样式文件
│   ├── main.js                 # 交互脚本
│   ├── images/                 # 页面图片素材
│   └── fonts/                  # PingFang SC 字体
├── kb/                         # Obsidian 藏品知识库
│   ├── README.md               # 知识库使用规范
│   ├── Templates/              # 藏品笔记模板
│   ├── Collections/            # 藏品 Markdown 笔记
│   └── Attachments/            # 藏品图片附件
├── data/                       # 构建产物
│   ├── collections.sqlite      # SQLite 数据库
│   ├── collections.json        # 藏品数据 JSON
│   ├── tags.json               # 标签索引 JSON
│   ├── text.index              # 文本语义索引（FAISS）
│   ├── text.index.mapping.json # 文本索引映射
│   └── image_hashes.json       # 图片感知哈希索引
├── scripts/                    # 构建与迁移脚本
│   ├── build_kb.py             # 知识库 → SQLite + JSON
│   ├── migrate_silkmuseum.py   # 中国丝绸博物馆数据迁移
│   ├── ai_appreciation.py      # AI 艺术评鉴生成
│   ├── build_vectors.py        # 文本/图片向量索引构建
│   ├── search_server.py        # 本地搜索服务
│   └── utils.py                # 工具函数
```

## 页面内容

1. **首页 Hero**：全屏刺绣纹样背景、品牌 Logo、导航、核心数据指标
2. **自营产品**：自营藏品、当代创作、文创品牌卡片与筛选
3. **文物展示**：参考中国丝绸博物馆藏品分类，按来源/类型/年代多维检索
4. **藏品检索**：语义搜索、名称搜索、标签筛选、以图搜图；搜索后标签云自动切换为结果相关的「推荐标签」
5. **藏品详情**：动态加载藏品信息，标签区默认折叠，点击展开后可直接按标签继续筛选
5. **合作大师**：云锦 / 苏绣 / 苗绣等非遗传承人展示
6. **新中式品牌**：跨界联名、设计大赛、潮牌合作案例
7. **展览活动**：刺绣游学、大师工作坊、主题展览
8. **合作机构**：国内 / 海外机构信任背书
9. **页脚**：品牌理念、联系咨询、导航链接、社交媒体

## 环境准备

```bash
# 创建虚拟环境并安装依赖
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

> 注意：依赖中固定了 `torch==2.2.2`、`sentence-transformers==2.7.0`、`transformers==4.44.2`、`numpy==1.26.4`，以避免版本冲突。文本 Embedding 使用 Ollama 本地模型生成，无需从 HuggingFace 下载大模型。

## 知识库工作流

本项目使用 Obsidian 管理藏品知识库，笔记为唯一内容源，数据库与 JSON 由脚本生成。

### 新增或编辑藏品

#### 方式一：使用知识库管理页面（推荐）

搜索服务启动后，打开 `http://127.0.0.1:8080/kb-manager.html` 进入管理后台：

1. **导入本地文件夹**：选择包含 `.md` 笔记与图片的文件夹，系统自动识别 frontmatter 与图片对应关系
2. **批量编辑草稿**：在草稿列表中点击卡片，完善名称、来源、分类、描述、标签、图片等信息
3. **生成标签**：点击「生成标签」，系统会基于规则与 AI 自动推荐工艺、纹样、题材、色彩等标签
4. **保存到知识库**：确认无误后批量保存，笔记与图片自动写入 `kb/Collections/{source}/` 与 `kb/Attachments/{source}/`
5. **管理已入库藏品**：切换到「已入库藏品」视图，可按关键词、来源、分类、状态检索并编辑已有笔记
6. **重建索引**：保存后点击「重建数据库」与「重建向量索引」，使改动生效

#### 方式二：在 Obsidian 中直接编辑

1. 在 Obsidian 中打开 `kb/` 目录作为 Vault
2. 使用 `kb/Templates/` 中的模板新建笔记
3. 填写 YAML frontmatter 与 Markdown 正文
4. 将图片放入 `kb/Attachments/{source}/`
5. 保存后运行构建脚本

### 构建数据库

```bash
# 增量构建
python scripts/build_kb.py

# 完整重建
python scripts/build_kb.py --full

# 仅校验格式
python scripts/build_kb.py --validate
```

### 从参考数据迁移

```bash
# 将中国丝绸博物馆展品数据迁移到项目知识库
python scripts/migrate_silkmuseum.py
```

## 向量检索与搜索

### 1. 启动 Ollama

确保 Ollama 已安装并运行，且已拉取 Embedding 模型：

```bash
ollama pull qwen3-embedding:0.6b
```

### 2. 构建向量索引

```bash
python scripts/build_vectors.py
```

文本索引使用 Ollama `qwen3-embedding:0.6b` 生成 1024 维向量；
图片索引使用 perceptual hash（pHash）计算相似度。

### 3. 启动搜索服务

```bash
python scripts/search_server.py
```

服务默认运行在 `http://127.0.0.1:8080`，提供以下接口：

- `GET /api/search/text?q=...` — 语义搜索
- `GET /api/search/name?q=...` — 名称搜索
- `GET /api/search/tags?tags=...` — 标签搜索
- `POST /api/search/image` — 以图搜图（multipart/form-data）
- `GET /api/collections` — 藏品列表
- `GET /api/collections/{id}` — 藏品详情
- `GET /api/tags` — 标签列表

### 4. 打开检索页

浏览器访问：

```
http://127.0.0.1:8080/search.html
```

## AI 艺术评鉴生成

```bash
# 使用本地 Ollama 模型（默认 qwen3:0.6b，质量一般，适合测试）
python scripts/ai_appreciation.py --limit 20

# 使用 Kimi API（推荐，质量更高）
export KIMI_API_KEY=your_key
python scripts/ai_appreciation.py --provider kimi --model moonshot-v1-8k

# 使用 OpenAI API
export OPENAI_API_KEY=your_key
python scripts/ai_appreciation.py --provider openai --model gpt-4o-mini
```

> 提示：qwen3:0.6b 模型生成的评鉴质量有限，建议正式使用前切换至 Kimi / OpenAI 等更强模型。

## 本地预览

### 方式一：仅预览静态页面（无搜索功能）

```bash
python3 -m http.server 8080
```

访问 `http://127.0.0.1:8080`

### 方式二：启动搜索服务（完整功能）

```bash
python scripts/search_server.py
```

访问 `http://127.0.0.1:8080`

## 数据现状

- 藏品笔记：2124 条（中国历代 1518 / 中国当代 446 / 西方 118 / 民族学 31 / 其他 11）
- 藏品图片：2680 张
- 标签：151 个
- 文本向量：2124 条（1024 维）
- 图片感知哈希：2124 条
- 已生成 AI 艺术评鉴：20 条（示例，待全量生成）
- 文本语义索引：2124 条（1024 维，FAISS）
- 图片感知哈希索引：2124 条（pHash）

## 说明

- 页面为静态 HTML/CSS/JS 实现，可直接部署到任意静态服务器
- 藏品图片、字体均已下载到本地，无需联网即可正常显示
- 采用响应式布局，适配桌面端与移动端
- 知识库笔记为唯一内容源，请勿直接修改 SQLite 数据库
- 搜索服务需要本地启动，适合本地开发与演示
- 当前以图搜图基于 pHash 构图/颜色相似度，后续可升级为 CLIP 语义相似度
- 标签推荐当前为客户端基于 Top-K 结果频率聚合，可进一步引入共现/TF-IDF/Embedding 打分

## 相关文档

- `PRD.md` — 产品需求文档
- `USER_STORIES.md` — 用户故事与验收标准
- `implementation_plan.md` — 详细实施计划与里程碑
- `PROJECT_STATUS.md` — 项目当前状态与待办
- `PROJECT_ISSUES.md` — 已知问题、技术债务与风险
