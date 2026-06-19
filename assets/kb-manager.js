/**
 * 叙思织绣知识库管理页面交互脚本
 */

// ==================== 状态管理 ====================
const state = {
  view: 'drafts', // 'drafts' | 'collections'
  drafts: [],
  collections: [],
  collectionTotal: 0,
  currentPage: 1,
  pageSize: 24,
  options: null,
  currentEdit: null, // 当前编辑的 draft 或 collection
  tempDir: null,
  filters: {
    q: '',
    source: '',
    category: '',
    status: ''
  }
};

// ==================== 工具函数 ====================
function $(selector) {
  return document.querySelector(selector);
}

function $$ (selector) {
  return document.querySelectorAll(selector);
}

function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function showLoading(show = true) {
  $('#loadingOverlay').classList.toggle('active', show);
}

function showStatus(message, type = 'info') {
  const bar = $('#statusBar');
  bar.textContent = message;
  bar.className = 'status-bar active ' + (type === 'error' ? 'error' : type === 'success' ? 'success' : '');
  setTimeout(() => bar.classList.remove('active'), 5000);
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  return dateStr;
}

function getMainImage(item) {
  // 列表接口返回 main_image，详情接口返回 metadata.images
  if (item.main_image) return item.main_image;
  const images = item.images || (item.metadata && item.metadata.images) || [];
  if (!images.length) return null;
  return images.find(img => img.is_main) || images[0];
}

function imageUrl(path) {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return `./kb/${path}`;
}

// ==================== API 调用 ====================
async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(path, body, isJson = true) {
  const opts = { method: 'POST' };
  if (isJson) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  } else {
    opts.body = body;
  }
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ==================== 初始化 ====================
async function init() {
  bindEvents();
  try {
    state.options = await apiGet('/admin/options');
    populateFilters();
    await loadCollections();
  } catch (e) {
    console.error('初始化失败', e);
    showStatus('初始化失败：' + e.message, 'error');
  }
}

function populateFilters() {
  const sourceSelect = $('#filterSource');
  const categorySelect = $('#filterCategory');
  if (!state.options) return;

  sourceSelect.innerHTML = '<option value="">全部来源</option>' +
    state.options.sources.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');

  // 分类选项使用第一个来源的分类列表（当前各来源分类已统一）
  const firstSource = state.options.sources[0] || '';
  const categories = state.options.categories[firstSource] || [];
  categorySelect.innerHTML = '<option value="">全部分类</option>' +
    categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
}

function bindEvents() {
  // 视图切换
  $$('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.view-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.view = tab.dataset.view;
      renderContent();
    });
  });

  // 文件夹导入
  const folderInput = $('#folderInput');
  const importZone = $('#importZone');

  importZone.addEventListener('click', () => folderInput.click());
  folderInput.addEventListener('change', handleFolderSelect);

  importZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    importZone.classList.add('dragover');
  });
  importZone.addEventListener('dragleave', () => importZone.classList.remove('dragover'));
  importZone.addEventListener('drop', (e) => {
    e.preventDefault();
    importZone.classList.remove('dragover');
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      handleDroppedItems(e.dataTransfer.items);
    }
  });

  // 筛选
  $('#btnApplyFilter').addEventListener('click', applyFilters);
  $('#filterKeyword').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') applyFilters();
  });

  // 刷新
  $('#btnRefresh').addEventListener('click', () => {
    if (state.view === 'collections') loadCollections();
    else renderDrafts();
  });

  // 保存草稿
  $('#btnSaveDrafts').addEventListener('click', saveSelectedDrafts);

  // 分页
  $('#btnPrev').addEventListener('click', () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      loadCollections();
    }
  });
  $('#btnNext').addEventListener('click', () => {
    if (state.currentPage * state.pageSize < state.collectionTotal) {
      state.currentPage++;
      loadCollections();
    }
  });

  // 编辑器
  $('#editorClose').addEventListener('click', closeEditor);
  $('#editorOverlay').addEventListener('click', (e) => {
    if (e.target === $('#editorOverlay')) closeEditor();
  });
  $('#btnSave').addEventListener('click', saveCurrentEdit);
  $('#btnArchive').addEventListener('click', archiveCurrent);
  $('#btnGenerateTags').addEventListener('click', generateTagsForCurrent);

  // 重建
  $('#btnRebuildKb').addEventListener('click', rebuildKb);
  $('#btnRebuildVectors').addEventListener('click', rebuildVectors);
}

// ==================== 文件夹导入 ====================
async function handleFolderSelect(e) {
  const files = e.target.files;
  if (!files.length) return;
  await uploadFilesForPreview(files);
}

async function handleDroppedItems(items) {
  const files = [];
  const promises = [];

  for (const item of items) {
    const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
    if (entry && entry.isDirectory) {
      promises.push(traverseDirectory(entry, files));
    } else if (item.getAsFile) {
      files.push(item.getAsFile());
    }
  }

  await Promise.all(promises);
  await uploadFilesForPreview(files);
}

function traverseDirectory(entry, files) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file(file => {
        // 保留相对路径
        Object.defineProperty(file, 'webkitRelativePath', {
          value: entry.fullPath.replace(/^\//, '')
        });
        files.push(file);
        resolve();
      });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      reader.readEntries(async (entries) => {
        await Promise.all(entries.map(e => traverseDirectory(e, files)));
        resolve();
      });
    } else {
      resolve();
    }
  });
}

async function uploadFilesForPreview(files) {
  showLoading(true);
  const formData = new FormData();
  for (const file of files) {
    // 使用相对路径作为文件名，便于后端保存目录结构
    const path = file.webkitRelativePath || file.name;
    formData.append('files', file, path);
  }

  try {
    const result = await fetch(`${API_BASE}/admin/import/preview`, {
      method: 'POST',
      body: formData
    });
    const data = await result.json();
    if (data.error) throw new Error(data.error);

    state.drafts = data.drafts || [];
    state.tempDir = data.temp_dir;
    state.view = 'drafts';

    // 切换视图标签
    $$('.view-tab').forEach(t => t.classList.toggle('active', t.dataset.view === 'drafts'));

    showStatus(`成功解析 ${state.drafts.length} 个藏品草稿`, 'success');
    renderDrafts();
  } catch (e) {
    console.error('导入预览失败', e);
    showStatus('导入预览失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

// ==================== 渲染 ====================
function renderContent() {
  if (state.view === 'drafts') {
    renderDrafts();
  } else {
    // 切换到已入库藏品视图时，若尚未加载则自动加载
    if (!state.collections.length && state.collectionTotal === 0) {
      loadCollections();
    } else {
      renderCollections();
    }
  }
}

function renderDrafts() {
  $('#pageTitle').textContent = '导入草稿';
  $('#btnSaveDrafts').style.display = state.drafts.length ? 'inline-flex' : 'none';
  $('#pagination').style.display = 'none';

  const container = $('#contentArea');
  if (!state.drafts.length) {
    container.innerHTML = '<div class="kb-empty">请选择文件夹开始导入</div>';
    return;
  }

  container.innerHTML = '';
  state.drafts.forEach(draft => {
    const card = createDraftCard(draft);
    container.appendChild(card);
  });
}

function createDraftCard(draft) {
  const mainImg = draft.images && draft.images.length > 0 ? draft.images[0] : null;
  const imgUrl = mainImg ? `./kb/${draft._temp_dir || state.tempDir}/${mainImg.filename}` : '';
  const tags = draft.metadata.tags || [];

  const card = document.createElement('div');
  card.className = 'kb-card';
  card.innerHTML = `
    <div class="kb-card-image ${mainImg ? '' : 'empty'}">
      ${mainImg ? `<img src="${escapeHtml(imgUrl)}" alt="" loading="lazy">` : '无图片'}
    </div>
    <div class="kb-card-body">
      <div class="kb-card-title">${escapeHtml(draft.name || '未命名')}</div>
      <div class="kb-card-meta">${escapeHtml(draft.source || '')} · ${escapeHtml(draft.metadata.category || '未分类')}</div>
      <div class="kb-card-tags">
        ${tags.slice(0, 5).map(t => `<span class="kb-card-tag">${escapeHtml(t)}</span>`).join('')}
      </div>
      ${draft.warnings.length ? `<div class="kb-card-warning">${draft.warnings.map(w => `• ${escapeHtml(w)}`).join('<br>')}</div>` : ''}
    </div>
  `;
  card.addEventListener('click', () => openEditor(draft, true));
  return card;
}

async function loadCollections() {
  showLoading(true);
  try {
    const params = new URLSearchParams();
    params.set('limit', state.pageSize);
    params.set('offset', (state.currentPage - 1) * state.pageSize);
    if (state.filters.q) params.set('q', state.filters.q);
    if (state.filters.source) params.set('source', state.filters.source);
    if (state.filters.category) params.set('category', state.filters.category);
    if (state.filters.status) params.set('status', state.filters.status);

    const data = await apiGet(`/admin/collections?${params.toString()}`);
    state.collections = data.results || [];
    state.collectionTotal = data.total || 0;

    if (state.view === 'collections') renderCollections();
  } catch (e) {
    console.error('加载藏品失败', e);
    showStatus('加载藏品失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

function renderCollections() {
  $('#pageTitle').textContent = '已入库藏品';
  $('#btnSaveDrafts').style.display = 'none';
  $('#pagination').style.display = state.collectionTotal > state.pageSize ? 'flex' : 'none';
  $('#pageInfo').textContent = `${state.currentPage} / ${Math.ceil(state.collectionTotal / state.pageSize)} 页，共 ${state.collectionTotal} 件`;

  const container = $('#contentArea');
  if (!state.collections.length) {
    container.innerHTML = '<div class="kb-empty">暂无藏品</div>';
    return;
  }

  container.innerHTML = '';
  state.collections.forEach(item => {
    const card = createCollectionCard(item);
    container.appendChild(card);
  });
}

function createCollectionCard(item) {
  const mainImg = getMainImage(item);
  const imgUrl = mainImg ? imageUrl(mainImg.path) : '';
  const tags = item.tags || [];
  const statusClass = `badge-${item.status || 'draft'}`;

  const card = document.createElement('div');
  card.className = 'kb-card';
  card.innerHTML = `
    <div class="kb-card-image ${mainImg ? '' : 'empty'}">
      ${mainImg ? `<img src="${escapeHtml(imgUrl)}" alt="" loading="lazy">` : '无图片'}
    </div>
    <div class="kb-card-body">
      <div class="kb-card-title">${escapeHtml(item.name || '未命名')}</div>
      <div class="kb-card-meta">
        ${escapeHtml(item.source || '')} · ${escapeHtml(item.category || '未分类')}
        <span class="badge ${statusClass}" style="margin-left: 6px;">${escapeHtml(item.status || '')}</span>
      </div>
      <div class="kb-card-tags">
        ${tags.slice(0, 5).map(t => `<span class="kb-card-tag">${escapeHtml(t)}</span>`).join('')}
      </div>
    </div>
  `;
  card.addEventListener('click', () => openCollectionEditor(item));
  return card;
}

function applyFilters() {
  state.filters.q = $('#filterKeyword').value.trim();
  state.filters.source = $('#filterSource').value;
  state.filters.category = $('#filterCategory').value;
  state.filters.status = $('#filterStatus').value;
  state.currentPage = 1;

  if (state.view !== 'collections') {
    state.view = 'collections';
    $$('.view-tab').forEach(t => t.classList.toggle('active', t.dataset.view === 'collections'));
  }
  loadCollections();
}


// ==================== 编辑器 ====================
function openEditor(item, isDraft = false) {
  state.currentEdit = { item, isDraft };
  $('#editorOverlay').classList.add('active');
  $('#editorTitle').textContent = isDraft ? '编辑导入草稿' : '编辑藏品';
  $('#btnArchive').style.display = isDraft ? 'none' : 'inline-flex';

  const metadata = isDraft ? item.metadata : item.metadata;
  const sections = isDraft ? item.sections : item.sections;
  const images = isDraft ? item.images : (metadata.images || []);

  const form = $('#editorForm');
  form.innerHTML = buildEditorHtml(metadata, sections, images, isDraft);

  // 来源变化时更新分类选项
  const sourceSelect = form.querySelector('#editSource');
  sourceSelect.addEventListener('change', updateCategoryOptions);

  bindTagInputs();
  bindImageUpload();
}

function openCollectionEditor(item) {
  // 需要获取完整详情（含 sections）
  showLoading(true);
  apiGet(`/admin/collections/${item.id}?source=${encodeURIComponent(item.source || '')}`)
    .then(detail => {
      showLoading(false);
      openEditor(detail, false);
    })
    .catch(e => {
      showLoading(false);
      showStatus('加载详情失败：' + e.message, 'error');
    });
}

function closeEditor() {
  $('#editorOverlay').classList.remove('active');
  state.currentEdit = null;
}

function updateCategoryOptions() {
  const source = $('#editSource').value;
  const categorySelect = $('#editCategory');
  const categories = state.options.categories[source] || [];
  categorySelect.innerHTML = '<option value="">请选择</option>' +
    categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
}

function buildEditorHtml(metadata, sections, images, isDraft) {
  const source = metadata.source || '其他';
  const categories = state.options.categories[source] || [];

  return `
    <div class="editor-section">
      <h3>基础信息</h3>
      <div class="editor-grid">
        <div class="form-group">
          <label>ID</label>
          <input type="text" class="form-control" id="editId" value="${escapeHtml(metadata.id || '')}" ${isDraft ? '' : 'readonly'}>
        </div>
        <div class="form-group">
          <label>名称 *</label>
          <input type="text" class="form-control" id="editName" value="${escapeHtml(metadata.name || '')}">
        </div>
        <div class="form-group">
          <label>Slug</label>
          <input type="text" class="form-control" id="editSlug" value="${escapeHtml(metadata.slug || '')}">
        </div>
        <div class="form-group">
          <label>藏品大类</label>
          <select class="form-control" id="editCollectionType">
            ${state.options.collection_types.map(t => `<option value="${escapeHtml(t)}" ${metadata.collection_type === t ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>来源 *</label>
          <select class="form-control" id="editSource">
            ${state.options.sources.map(s => `<option value="${escapeHtml(s)}" ${source === s ? 'selected' : ''}>${escapeHtml(s)}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>分类 *</label>
          <select class="form-control" id="editCategory">
            <option value="">请选择</option>
            ${categories.map(c => `<option value="${escapeHtml(c)}" ${metadata.category === c ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>状态</label>
          <select class="form-control" id="editStatus">
            ${state.options.status_options.map(s => `<option value="${escapeHtml(s)}" ${metadata.status === s ? 'selected' : ''}>${escapeHtml(s)}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>子分类</label>
          <input type="text" class="form-control" id="editSubCategory" value="${escapeHtml(metadata.sub_category || '')}">
        </div>
      </div>
    </div>

    <div class="editor-section">
      <h3>元数据</h3>
      <div class="editor-grid">
        <div class="form-group">
          <label>质地</label>
          <input type="text" class="form-control" id="editMaterial" value="${escapeHtml(metadata.material || '')}">
        </div>
        <div class="form-group">
          <label>年代</label>
          <input type="text" class="form-control" id="editEra" value="${escapeHtml(metadata.era || '')}">
        </div>
        <div class="form-group">
          <label>朝代</label>
          <input type="text" class="form-control" id="editDynasty" value="${escapeHtml(metadata.dynasty || '')}">
        </div>
        <div class="form-group">
          <label>尺寸</label>
          <input type="text" class="form-control" id="editSize" value="${escapeHtml(metadata.size || '')}">
        </div>
        <div class="form-group">
          <label>数量</label>
          <input type="text" class="form-control" id="editQuantity" value="${escapeHtml(metadata.quantity || '')}">
        </div>
        <div class="form-group">
          <label>收藏单位</label>
          <input type="text" class="form-control" id="editCollectionUnit" value="${escapeHtml(metadata.collection_unit || '')}">
        </div>
        <div class="form-group">
          <label>作者</label>
          <input type="text" class="form-control" id="editAuthor" value="${escapeHtml(metadata.author || '')}">
        </div>
        <div class="form-group">
          <label>级别</label>
          <input type="text" class="form-control" id="editLevel" value="${escapeHtml(metadata.level || '')}">
        </div>
        <div class="form-group">
          <label>来源地</label>
          <input type="text" class="form-control" id="editOrigin" value="${escapeHtml(metadata.origin || '')}">
        </div>
        <div class="form-group form-control-full">
          <label>原始链接</label>
          <input type="text" class="form-control" id="editSourceUrl" value="${escapeHtml(metadata.source_url || '')}">
        </div>
        <div class="form-group">
          <label>来源网站</label>
          <input type="text" class="form-control" id="editSourceSite" value="${escapeHtml(metadata.source_site || '')}">
        </div>
        <div class="form-group">
          <label>采集时间</label>
          <input type="text" class="form-control" id="editCrawledAt" value="${escapeHtml(metadata.crawled_at || '')}">
        </div>
      </div>
    </div>

    <div class="editor-section">
      <h3>标签</h3>
      <div class="form-group">
        <label>工艺</label>
        <div class="tag-input-area" data-field="technique">
          ${(metadata.technique || []).map(t => tagChipHtml(t)).join('')}
          <input type="text" class="tag-input" placeholder="输入后回车">
        </div>
      </div>
      <div class="form-group">
        <label>纹样</label>
        <div class="tag-input-area" data-field="pattern">
          ${(metadata.pattern || []).map(t => tagChipHtml(t)).join('')}
          <input type="text" class="tag-input" placeholder="输入后回车">
        </div>
      </div>
      <div class="form-group">
        <label>题材</label>
        <div class="tag-input-area" data-field="theme">
          ${(metadata.theme || []).map(t => tagChipHtml(t)).join('')}
          <input type="text" class="tag-input" placeholder="输入后回车">
        </div>
      </div>
      <div class="form-group">
        <label>色彩</label>
        <div class="tag-input-area" data-field="color">
          ${(metadata.color || []).map(t => tagChipHtml(t)).join('')}
          <input type="text" class="tag-input" placeholder="输入后回车">
        </div>
      </div>
      <div class="form-group">
        <label>通用标签</label>
        <div class="tag-input-area" data-field="tags">
          ${(metadata.tags || []).map(t => tagChipHtml(t)).join('')}
          <input type="text" class="tag-input" placeholder="输入后回车">
        </div>
      </div>
    </div>

    <div class="editor-section">
      <h3>图片</h3>
      <div class="image-list" id="imageList">
        ${(images || []).map((img, idx) => imageItemHtml(img, idx, isDraft)).join('')}
      </div>
      <div class="upload-image-btn" id="uploadImageBtn">
        + 上传新图片
      </div>
      <input type="file" id="imageUploadInput" accept="image/*" style="display: none;">
    </div>

    <div class="editor-section">
      <h3>内容</h3>
      <div class="form-group">
        <label>描述</label>
        <textarea class="form-control" id="editDescription">${escapeHtml(sections && sections['描述'] ? sections['描述'] : metadata.description || '')}</textarea>
      </div>
      <div class="form-group">
        <label>艺术评鉴</label>
        <textarea class="form-control" id="editAppreciation">${escapeHtml(sections && sections['艺术评鉴'] ? sections['艺术评鉴'] : metadata.appreciation || '')}</textarea>
      </div>
    </div>
  `;
}

function tagChipHtml(text) {
  return `<span class="tag-chip">${escapeHtml(text)}<button type="button" onclick="this.parentElement.remove()">×</button></span>`;
}

function imageItemHtml(img, idx, isDraft) {
  const path = img.path
    ? imageUrl(img.path)
    : (isDraft && state.tempDir ? `./kb/${state.tempDir}/${img.filename}` : '');
  const filename = img.filename || '';
  return `
    <div class="image-item" data-index="${idx}" data-filename="${escapeHtml(filename)}">
      <img src="${escapeHtml(path)}" alt="${escapeHtml(img.alt || '')}" data-path="${escapeHtml(img.path || '')}" data-filename="${escapeHtml(filename)}">
      <div class="image-item-info">
        <input type="text" class="form-control image-alt" value="${escapeHtml(img.alt || '')}" placeholder="替代文本">
        <label style="font-size: 0.8rem; color: var(--color-text-muted);">
          <input type="radio" name="mainImage" value="${idx}" ${img.is_main ? 'checked' : ''}> 设为主图
        </label>
      </div>
      <div class="image-item-actions">
        <button class="btn btn-danger btn-sm" onclick="this.closest('.image-item').remove()">删除</button>
      </div>
    </div>
  `;
}

function bindTagInputs() {
  $$('.tag-input-area').forEach(area => {
    const input = area.querySelector('.tag-input');
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const value = input.value.trim();
        if (value) {
          const chip = document.createElement('span');
          chip.className = 'tag-chip';
          chip.innerHTML = `${escapeHtml(value)}<button type="button" onclick="this.parentElement.remove()">×</button>`;
          area.insertBefore(chip, input);
          input.value = '';
        }
      }
    });
  });
}

function bindImageUpload() {
  $('#uploadImageBtn').addEventListener('click', () => $('#imageUploadInput').click());
  $('#imageUploadInput').addEventListener('change', handleImageUpload);
}

async function handleImageUpload(e) {
  const file = e.target.files[0];
  if (!file) return;

  const metadata = collectMetadataFromForm();
  if (!metadata.source) {
    showStatus('请先选择来源', 'error');
    return;
  }

  showLoading(true);
  const formData = new FormData();
  formData.append('file', file);
  formData.append('source', metadata.source);
  if (metadata.id) formData.append('id', metadata.id);
  if (metadata.name) formData.append('name', metadata.name);
  formData.append('role', '图');

  try {
    const result = await fetch(`${API_BASE}/admin/images/upload`, {
      method: 'POST',
      body: formData
    });
    const data = await result.json();
    if (data.error) throw new Error(data.error);

    // 添加到图片列表
    const imageList = $('#imageList');
    const idx = imageList.children.length;
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = imageItemHtml(data, idx, false);
    imageList.appendChild(tempDiv.firstElementChild);

    showStatus('图片上传成功', 'success');
  } catch (err) {
    showStatus('图片上传失败：' + err.message, 'error');
  } finally {
    showLoading(false);
    $('#imageUploadInput').value = '';
  }
}

function collectMetadataFromForm() {
  const metadata = {
    id: $('#editId').value.trim(),
    name: $('#editName').value.trim(),
    slug: $('#editSlug').value.trim(),
    collection_type: $('#editCollectionType').value,
    source: $('#editSource').value,
    category: $('#editCategory').value,
    sub_category: $('#editSubCategory').value.trim(),
    status: $('#editStatus').value,
    technique: collectTags('technique'),
    pattern: collectTags('pattern'),
    theme: collectTags('theme'),
    material: $('#editMaterial').value.trim(),
    color: collectTags('color'),
    era: $('#editEra').value.trim(),
    dynasty: $('#editDynasty').value.trim(),
    size: $('#editSize').value.trim(),
    quantity: $('#editQuantity').value.trim(),
    collection_unit: $('#editCollectionUnit').value.trim(),
    author: $('#editAuthor').value.trim(),
    level: $('#editLevel').value.trim(),
    origin: $('#editOrigin').value.trim(),
    source_url: $('#editSourceUrl').value.trim(),
    source_site: $('#editSourceSite').value.trim(),
    crawled_at: $('#editCrawledAt').value.trim(),
    tags: collectTags('tags'),
    images: collectImages(),
  };
  return metadata;
}

function collectTags(field) {
  const area = document.querySelector(`.tag-input-area[data-field="${field}"]`);
  if (!area) return [];
  return Array.from(area.querySelectorAll('.tag-chip')).map(chip => {
    // 移除删除按钮文本
    return chip.childNodes[0].textContent.trim();
  });
}

function collectImages() {
  const images = [];
  const mainRadio = document.querySelector('input[name="mainImage"]:checked');
  const mainIndex = mainRadio ? parseInt(mainRadio.value) : 0;

  $$('.image-item').forEach((item, idx) => {
    const img = item.querySelector('img');
    const alt = item.querySelector('.image-alt').value.trim();
    const path = img.dataset.path || img.src || '';
    const filename = img.dataset.filename || item.dataset.filename || '';
    // 只保留相对路径
    let cleanPath = path;
    if (cleanPath.includes('/kb/')) {
      cleanPath = cleanPath.split('/kb/')[1];
    }
    images.push({
      path: cleanPath,
      filename: filename,
      alt: alt || img.alt || '',
      is_main: idx === mainIndex
    });
  });
  return images;
}

function collectSectionsFromForm() {
  return {
    '描述': $('#editDescription').value.trim(),
    '艺术评鉴': $('#editAppreciation').value.trim(),
  };
}

// ==================== 保存 ====================
async function saveCurrentEdit() {
  if (!state.currentEdit) return;

  const metadata = collectMetadataFromForm();
  if (!metadata.name || !metadata.source || !metadata.category) {
    showStatus('请填写名称、来源和分类', 'error');
    return;
  }

  showLoading(true);
  try {
    const { item, isDraft } = state.currentEdit;
    const sections = collectSectionsFromForm();

    if (isDraft) {
      // 更新草稿
      item.metadata = metadata;
      item.sections = sections;
      item.name = metadata.name;
      item.source = metadata.source;
      // 同步图片的 alt 和 is_main（保持 filename 不变）
      const formImages = collectImages();
      if (item.images && formImages.length) {
        item.images = item.images.map((img, idx) => ({
          ...img,
          alt: formImages[idx] ? formImages[idx].alt : img.alt,
          is_main: formImages[idx] ? formImages[idx].is_main : (idx === 0)
        }));
      }
      showStatus('草稿已更新，请保存到知识库', 'success');
      renderDrafts();
      closeEditor();
    } else {
      // 保存已入库藏品
      const result = await apiPost(`/admin/collections/${metadata.id}`, { metadata, sections });
      showStatus('藏品已保存', 'success');
      closeEditor();
      await loadCollections();
    }
  } catch (e) {
    console.error('保存失败', e);
    showStatus('保存失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

async function saveSelectedDrafts() {
  if (!state.drafts.length) return;

  // 批量保存所有草稿
  const draftsToSave = state.drafts.map(d => ({
    ...d,
    _temp_dir: state.tempDir
  }));

  showLoading(true);
  try {
    const result = await apiPost('/admin/import/commit', { drafts: draftsToSave });
    if (result.errors && result.errors.length) {
      showStatus(`保存完成：${result.count} 成功，${result.errors.length} 失败`, 'error');
      console.error(result.errors);
    } else {
      showStatus(`成功保存 ${result.count} 个藏品`, 'success');
      state.drafts = [];
      state.tempDir = null;
      renderDrafts();
    }
  } catch (e) {
    console.error('保存失败', e);
    showStatus('保存失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

async function archiveCurrent() {
  if (!state.currentEdit || state.currentEdit.isDraft) return;
  const metadata = collectMetadataFromForm();
  if (!confirm(`确定要归档藏品「${metadata.name}」吗？`)) return;

  showLoading(true);
  try {
    await apiDelete(`/admin/collections/${metadata.id}?source=${encodeURIComponent(metadata.source)}`);
    showStatus('藏品已归档', 'success');
    closeEditor();
    await loadCollections();
  } catch (e) {
    showStatus('归档失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

// ==================== 标签生成 ====================
async function generateTagsForCurrent() {
  const metadata = collectMetadataFromForm();
  const description = $('#editDescription').value.trim();

  showLoading(true);
  try {
    const result = await apiPost('/admin/tags/generate', {
      name: metadata.name,
      description: description,
      material: metadata.material,
      provider: 'ollama'
    });

    // 合并到表单
    fillTagArea('technique', result.technique || []);
    fillTagArea('pattern', result.pattern || []);
    fillTagArea('theme', result.theme || []);
    fillTagArea('color', result.color || []);
    fillTagArea('tags', result.tags || []);

    showStatus('标签生成完成', 'success');
  } catch (e) {
    console.error('标签生成失败', e);
    showStatus('标签生成失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

function fillTagArea(field, tags) {
  const area = document.querySelector(`.tag-input-area[data-field="${field}"]`);
  if (!area || !tags.length) return;

  // 保留已有标签，追加新标签
  const existing = Array.from(area.querySelectorAll('.tag-chip')).map(chip =>
    chip.childNodes[0].textContent.trim()
  );
  const newTags = tags.filter(t => !existing.includes(t));

  const input = area.querySelector('.tag-input');
  newTags.forEach(t => {
    const chip = document.createElement('span');
    chip.className = 'tag-chip';
    chip.innerHTML = `${escapeHtml(t)}<button type="button" onclick="this.parentElement.remove()">×</button>`;
    area.insertBefore(chip, input);
  });
}

// ==================== 构建 ====================
async function rebuildKb() {
  if (!confirm('重建数据库可能需要几分钟，确定继续？')) return;
  showLoading(true);
  try {
    const result = await apiPost('/admin/build?full=true', {});
    if (result.success) {
      showStatus('数据库重建成功', 'success');
      await loadCollections();
    } else {
      throw new Error(result.error || result.stderr || '未知错误');
    }
  } catch (e) {
    showStatus('数据库重建失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

async function rebuildVectors() {
  if (!confirm('重建向量索引可能需要较长时间，确定继续？')) return;
  showLoading(true);
  try {
    const result = await apiPost('/admin/build/vectors', {});
    if (result.success) {
      showStatus('向量索引重建成功', 'success');
    } else {
      throw new Error(result.error || result.stderr || '未知错误');
    }
  } catch (e) {
    showStatus('向量索引重建失败：' + e.message, 'error');
  } finally {
    showLoading(false);
  }
}

// ==================== 启动 ====================
document.addEventListener('DOMContentLoaded', init);
