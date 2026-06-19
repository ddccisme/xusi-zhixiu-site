# Agent 开发指南

本文档记录本项目的开发约定、关键实现细节与常见踩坑点，供后续维护与 AI 协作时参考。

## 项目概况

- **项目**：叙思织绣独立站
- **技术栈**：FastAPI + Uvicorn 后端，vanilla HTML/CSS/JS 前端，Obsidian Markdown 知识库 `kb/`
- **本地服务**：`http://127.0.0.1:8080`，入口脚本 `scripts/search_server.py`
- **虚拟环境**：`.venv/`，Python 3.11
- **内容唯一来源**：`kb/` 目录下的 Markdown 文件

## 关键约定

### 1. 静态文件与缓存

- 静态文件通过 `__static__/` 沙箱目录 + symlink 暴露。
- `search_server.py` 已配置 `NoCacheMiddleware`，对 `.html`、`.js`、`.css` 返回 `Cache-Control: no-cache, no-store, must-revalidate`。
- 开发调试时若浏览器仍缓存，可在 URL 后加随机参数（如 `?_t=123`），或清空浏览器缓存。

### 2. 图片路径

- 知识库图片统一存放在 `kb/Attachments/{source}/`。
- 图片文件名约定：`{id}_{name}_{角色}.{ext}`，例如 `1815_绞缬绢衣_主图.jpg`。
- 前端引用时使用相对路径 `./kb/{relative_path}`。

### 3. XSS 防护

- 所有动态插入的 HTML 必须通过 `escapeHtml` 或 `textContent` 处理，禁止直接拼接不可信内容到 `innerHTML`。

### 4. 项目文档结构

项目文档统一存放在 `docs/` 目录，根目录只保留入口说明：

```
00_web/
├── README.md                   # 项目说明与快速开始
├── AGENTS.md                   # 本文件：AI/Agent 开发指南
├── docs/
│   ├── PRD.md                  # 产品需求文档
│   ├── USER_STORIES.md         # 用户故事与验收标准
│   ├── implementation_plan.md  # 详细实施计划与里程碑
│   ├── PROJECT_STATUS.md       # 项目当前状态
│   ├── PROJECT_ISSUES.md       # 项目问题与风险
│   └── 中国丝绸博物馆藏品分类整理.md
```

- 新增或调整文档位置时，需同步更新 `README.md` 的项目结构树以及各文档内部的交叉引用路径。

## 开发调试

### 启动本地服务

```bash
cd /Users/andy_dongcheng/Desktop/DC_WORK/WORKSPACE/16_文娱产业项目/00_web
source .venv/bin/activate
python scripts/search_server.py
```

服务默认监听 `http://127.0.0.1:8080`。

### 强制刷新浏览器缓存

虽然服务端已禁用 HTML/JS/CSS 缓存，但浏览器（尤其 Safari）可能仍 aggressively cache。调试时建议：

1. 使用 `Cmd + Shift + R`（Safari/Chrome）强制刷新。
2. 或在 URL 后加随机参数：`http://127.0.0.1:8080/detail.html?id=1815&_t=123`。
3. 必要时清空浏览器缓存：`Safari → 开发 → 清空缓存` 或 `Chrome DevTools → Network → Disable cache`。

### 前端改动验证流程

1. 修改 `detail.html`、`assets/*.js`、`assets/*.css`。
2. 确认 `search_server.py` 正在运行（静态文件由它提供）。
3. 浏览器强制刷新后验证。
4. 对于复杂交互（如放大镜），可用 Chrome DevTools Protocol 自动化截图验证。

## 藏品详情页（detail.html）放大镜实现

### 交互设计

- 桌面端（宽度 > 768px）：左侧缩略图、中间主图、右侧详情区域。
- 鼠标悬停中间主图时：
  - 主图上显示一个半透明白色 lens 方框（`.detail-zoom-lens`）。
  - 右侧详情区域被放大局部图覆盖（`.detail-zoom-overlay`）。
- 移动端（宽度 ≤ 768px）：不启用放大镜，详情区域正常显示。

### 关键 DOM 结构

```html
<section class="detail-hero">
  <div class="detail-gallery">
    <div class="detail-thumbnails">...</div>
    <div class="detail-gallery-main">
      <div class="detail-main-image" id="mainImageWrap">
        <img id="mainImage" />
        <div class="detail-zoom-lens" id="zoomLens"></div>
      </div>
    </div>
  </div>
  <div class="detail-summary-wrap">
    <div class="detail-zoom-overlay" id="zoomOverlay">
      <img id="zoomImage" />
    </div>
    <div class="detail-summary">...</div>
  </div>
</section>
```

### 核心实现要点

1. **初始化时机**  
   `initImageGallery()` 必须在 `hero` 已加入 DOM 之后调用，否则 `document.querySelector('.detail-summary-wrap')` 会返回 `null`，导致放大镜事件根本无法绑定。

2. **放大图 URL 编码**  
   `mainImage.src` 已被浏览器解析为编码后的绝对 URL，**不要**再次 `encodeURI`，否则会出现双重编码（`%` → `%25`），导致图片加载失败。

3. **放大倍数与偏移**  
   - 放大倍数 = `overlay 尺寸 / lens 尺寸`。
   - 使用 `<img>` 元素而非 `background-image`，通过 `width`、`height`、`transform: translate(x, y)` 显示对应局部。

4. **响应式**  
   CSS 媒体查询在 `max-width: 768px` 下将 `.detail-zoom-overlay` 设为 `display: none !important;`，移动端不启用放大镜。

### 已修复的坑

| 时间 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-06-20 | 放大镜不显示 | `initImageGallery` 在 `hero` 加入 DOM 前调用，`summaryWrap` 查询为 `null` | 将初始化移到 `container.appendChild(hero)` 之后 |
| 2026-06-20 | 放大图无法加载 | 对 `mainImage.src` 重复 `encodeURI` 导致双重编码 | 区分相对路径与已编码的绝对路径，仅对相对路径编码 |
| 2026-06-20 | 控制台 `null` 报错 | `detail.html` 缺少 `#mobileMenu`、筛选 DOM，`assets/main.js` 未做空判断 | 在 `main.js` 中添加 DOM 存在性检查 |

## 验证方法

### 放大镜功能验证

1. 启动服务：`python scripts/search_server.py`
2. 访问：`http://127.0.0.1:8080/detail.html?id=1815`
3. 确保浏览器窗口宽度 > 768px。
4. 鼠标悬停中间主图，右侧详情区域应被放大局部图覆盖。

### 自动化截图验证（开发调试用）

可使用 Chrome DevTools Protocol 模拟鼠标事件并截图：

```bash
# 示例：启动 Chrome 远程调试并执行测试脚本
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9333 \
  --window-size=1400,900 \
  "http://127.0.0.1:8080/detail.html?id=1815"
```

然后通过 CDP 发送 `mouseenter` / `mousemove` 事件并调用 `Page.captureScreenshot` 截图验证。

## 最近变更记录

| 时间 | 变更 | 提交 |
|------|------|------|
| 2026-06-20 | 修复 detail.html 放大镜不显示问题：调整 `initImageGallery` 调用时机、修复图片 URL 双重编码 | `16bf079` |
| 2026-06-20 | 修复 `assets/main.js` 在 detail.html 上因缺少 `#mobileMenu` 与筛选 DOM 导致的 `null` 报错 | `c278d01` |
| 2026-06-20 | 将项目文档（`PRD.md`、`USER_STORIES.md`、`implementation_plan.md`、`PROJECT_STATUS.md`、`PROJECT_ISSUES.md`、`中国丝绸博物馆藏品分类整理.md`）统一迁移到 `docs/` 目录 | `4480380`、`d79a465` |
| 2026-06-20 | 新增本 `AGENTS.md` 文件，记录开发约定与放大镜实现细节 | `792eb2a` |
