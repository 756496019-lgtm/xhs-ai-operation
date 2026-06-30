let items = [];

// 当前找到的参考来源（含 selected 字段）
let extraSources = [];

// 当前提取的游戏截图（含 selected 字段）
let allImages = [];

// Reddit 直发图片（showPublishPanel / publishDirectly 使用）
let _redditPublishImages = [];

// 改写模式：'text'（文字改写）或 'video'（视频脚本）
const rewriteMode = sessionStorage.getItem('rewriteMode') || 'text';

const VIDEO_SCRIPT_PROMPT = `你是「游戏雷达局」的视频脚本撰写官。
请将以下游戏资讯改写为适合短视频（小红书/抖音）的口播脚本。
要求：
1. 开头用一句引人注目的口头禅切入，风格由你自由发挥，要有记忆点，比如感叹类、疑问类、夸张类都可以
2. 中间：完整覆盖原文所有信息点，包括信息来源（如爆料者、媒体名称）、具体数据和未经证实的内容也要如实交代；用口语化表达，每句话不超过25字
3. 结尾固定以「游戏雷达局，情报已送达——」收尾
4. 只输出脚本正文，不要标题，不要任何 Markdown 符号（#、**、- 等），不要额外说明`;

function applyMode(mode) {
  const badge = document.getElementById('mode-badge');
  const promptEl = document.getElementById('input-prompt');
  const btnGraphic = document.getElementById('btn-to-graphic-from-rewrite');
  const btnVideo = document.getElementById('btn-to-video-from-rewrite');
  const btnScript = document.getElementById('btn-to-script-preview');
  if (mode === 'video') {
    if (badge) { badge.textContent = '视频脚本模式'; badge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-[#F0EDFF] text-[#6C5CE7] font-semibold'; }
    if (promptEl) promptEl.value = VIDEO_SCRIPT_PROMPT;
    // 改写完成后只显示"生成视频脚本"按钮
    if (btnGraphic) btnGraphic.classList.add('hidden');
    if (btnVideo) btnVideo.classList.add('hidden');
    if (btnScript) { btnScript.classList.remove('hidden'); btnScript.classList.add('flex'); }
  } else {
    if (badge) { badge.textContent = '文字改写模式'; badge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-[#E8FFF5] text-[#00B894] font-semibold'; }
    // 保持 textarea 原有默认值（HTML 中已有）
    if (btnGraphic) btnGraphic.classList.remove('hidden');
    if (btnVideo) btnVideo.classList.remove('hidden');
    if (btnScript) { btnScript.classList.add('hidden'); btnScript.classList.remove('flex'); }
  }
}

function initFromSession() {
  try {
    const raw = sessionStorage.getItem('rewriteItems');
    if (raw) items = JSON.parse(raw) || [];
  } catch (e) {
    console.warn('无法读取 rewriteItems:', e);
  }
  applyMode(rewriteMode);
}

function refreshItemSelect() {
  const sel = document.getElementById('item-select');
  sel.innerHTML = '';
  items.forEach((item, idx) => {
    const opt = document.createElement('option');
    opt.value = idx;
    opt.textContent = (item.source || '') + ' - ' + (item.title || '').slice(0, 40);
    sel.appendChild(opt);
  });
  if (items.length) {
    sel.value = '0';
    loadItem(0);
  }
}

function loadItem(index) {
  const item = items[index];
  if (!item) return;
  const content = (item.content || item.summary || '') || '';
  const text = [
    '【来源】' + (item.source || ''),
    item.subreddit ? ('r/' + item.subreddit) : '',
    '【标题】' + (item.title || ''),
    item.url ? ('【链接】' + item.url) : '',
    '',
    content.replace(/<[^>]+>/g, '')
  ].join('\n').trim();
  document.getElementById('input-original').value = text;

  // "更多来源"按钮对所有来源可见；"查找游戏截图"仅游民星空可见
  const isGamersky = (item.source || '') === 'gamersky';
  const findImgBtn = document.getElementById('btn-find-images');
  if (isGamersky) {
    findImgBtn.classList.remove('hidden');
    findImgBtn.classList.add('flex');
  } else {
    findImgBtn.classList.add('hidden');
    findImgBtn.classList.remove('flex');
    document.getElementById('images-panel').classList.add('hidden');
    allImages = [];
  }

  // Reddit 条目 → 跳转到专属编辑页
  const isReddit = (item.source || '') === 'reddit';
  if (isReddit) {
    window.location.href = '/reddit_edit';
    return;
  }
  document.getElementById('reddit-publish-panel').classList.add('hidden');
}

document.getElementById('item-select').addEventListener('change', (e) => {
  const idx = parseInt(e.target.value, 10);
  loadItem(idx);
});

// ==================== 多来源面板 ====================

document.getElementById('btn-find-sources').addEventListener('click', () => {
  const panel = document.getElementById('sources-panel');
  panel.classList.toggle('hidden');
  // 预填搜索框：当前条目标题作为默认关键词
  const sel = document.getElementById('item-select');
  const idx = parseInt(sel.value || '0', 10);
  const item = items[idx];
  const searchInput = document.getElementById('sources-search-input');
  if (item && item.title && !searchInput.value) {
    searchInput.value = item.title;
  }
});

// Bing 搜索 - 回车触发
document.getElementById('sources-search-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') doSearchSources();
});

async function doSearchSources() {
  const query = document.getElementById('sources-search-input').value.trim();
  if (!query) return;

  const btn    = document.getElementById('btn-search-sources');
  const status = document.getElementById('sources-status');
  btn.disabled = true;
  btn.textContent = '搜索中…';
  status.textContent = `正在 Bing 搜索「${query}」，请稍候…`;

  try {
    const resp = await fetch('/api/fetch_sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, num: 5 })
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '搜索失败');

    const newSources = (data.sources || []).map(s => ({ ...s, selected: true }));
    const existingUrls = new Set(extraSources.map(s => s.url));
    newSources.forEach(s => { if (!existingUrls.has(s.url)) extraSources.push(s); });
    renderSourcesList();
    status.textContent = newSources.length
      ? `搜索到 ${newSources.length} 条新来源，已添加到列表。`
      : '未找到新的相关来源。';
  } catch (e) {
    status.textContent = '搜索失败：' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '搜索';
  }
}

// 自定义链接管理
function addUrlRow(btn) {
  const list = document.getElementById('custom-urls-list');
  const row = document.createElement('div');
  row.className = 'flex gap-1.5 url-row';
  row.innerHTML = `
    <input type="url" placeholder="https://..."
           class="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-[#0984E3] url-input transition-all">
    <button onclick="this.closest('.url-row').remove()"
            class="px-2.5 py-1.5 rounded-lg border border-gray-200 text-red-400 hover:border-red-400 text-sm leading-none transition-colors">×</button>`;
  // 把当前行的 + 按钮换成 × 按钮
  if (btn) {
    btn.textContent = '×';
    btn.className = 'px-2.5 py-1.5 rounded-lg border border-gray-200 text-red-400 hover:border-red-400 text-sm leading-none transition-colors';
    btn.onclick = () => btn.closest('.url-row').remove();
  }
  list.appendChild(row);
}

async function doFetchUrls() {
  const inputs = document.querySelectorAll('#custom-urls-list .url-input');
  const urls = Array.from(inputs).map(i => i.value.trim()).filter(u => u.startsWith('http'));
  if (!urls.length) {
    document.getElementById('sources-status').textContent = '请先填入有效的 http(s) 链接。';
    return;
  }

  const btn    = document.getElementById('btn-fetch-urls');
  const status = document.getElementById('sources-status');
  btn.disabled = true;
  btn.textContent = `正在抓取 ${urls.length} 个链接…`;
  status.textContent = '';

  try {
    const resp = await fetch('/api/fetch_urls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls })
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '抓取失败');

    const newSources = (data.sources || []).map(s => ({ ...s, selected: true }));
    const existingUrls = new Set(extraSources.map(s => s.url));
    newSources.forEach(s => { if (!existingUrls.has(s.url)) extraSources.push(s); });
    renderSourcesList();
    status.textContent = newSources.length
      ? `成功抓取 ${newSources.length} 个链接内容，已添加到来源列表。`
      : '抓取完成，但未能获取到有效正文内容（可能需要登录或被防爬）。';
  } catch (e) {
    status.textContent = '抓取失败：' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '抓取以上链接内容';
  }
}

function renderSourcesList() {
  const list = document.getElementById('sources-list');
  const count = document.getElementById('sources-count');
  list.innerHTML = '';

  if (!extraSources.length) {
    list.innerHTML = '<p class="text-xs text-gray-400 py-1">暂无找到相关来源</p>';
    count.textContent = '';
    return;
  }

  const selected = extraSources.filter(s => s.selected).length;
  count.textContent = `找到 ${extraSources.length} 个，已选 ${selected} 个`;

  extraSources.forEach((src, i) => {
    const row = document.createElement('label');
    row.className = 'flex items-start gap-2.5 p-2.5 rounded-lg border border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors';
    row.innerHTML = `
      <input type="checkbox" class="mt-0.5 accent-[#6C5CE7] shrink-0" ${src.selected ? 'checked' : ''} data-si="${i}">
      <div class="min-w-0">
        <div class="text-xs font-semibold text-gray-700 truncate">${escapeHtml(src.title)}</div>
        <div class="text-[10px] text-gray-400 truncate">${escapeHtml(src.domain)} · ${escapeHtml(src.url)}</div>
        <div class="text-[10px] text-gray-500 mt-1 line-clamp-2">${escapeHtml((src.content || '').slice(0, 120))}…</div>
      </div>`;
    row.querySelector('input').addEventListener('change', (e) => {
      extraSources[i].selected = e.target.checked;
      const sel2 = extraSources.filter(s => s.selected).length;
      count.textContent = `找到 ${extraSources.length} 个，已选 ${sel2} 个`;
    });
    list.appendChild(row);
  });
}

function escapeHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ==================== 生成改写 ====================

document.getElementById('btn-run-rewrite').addEventListener('click', async () => {
  const status = document.getElementById('rewrite-status');
  const output = document.getElementById('output-rewrite');
  const original = document.getElementById('input-original').value.trim();
  const prompt = document.getElementById('input-prompt').value.trim();
  const tone = document.getElementById('tone').value;
  const sel = document.getElementById('item-select');
  const idx = sel && sel.value ? parseInt(sel.value, 10) : 0;
  const item = items[idx] || null;
  if (!original) {
    alert('原文为空，请先选择一条内容。');
    return;
  }

  const selectedSources = extraSources.filter(s => s.selected);
  const hasMultiSource = selectedSources.length > 0;

  status.textContent = hasMultiSource
    ? `正在融合 ${selectedSources.length} 个来源进行改写，请稍候…`
    : '正在调用 AI 改写，请稍候...';
  output.value = '';

  try {
    const resp = await fetch('/api/rewrite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        tone,
        original,
        mode: rewriteMode,
        item,
        extra_sources: selectedSources.map(s => ({
          title:   s.title,
          url:     s.url,
          content: s.content,
        })),
      })
    });
    const data = await resp.json();
    if (data.status !== 'ok') {
      status.textContent = '出错：' + (data.message || '未知错误');
      return;
    }
    output.value = data.text || '';
    status.textContent = hasMultiSource
      ? `多源改写完成（融合了 ${selectedSources.length} 个来源）。`
      : '已完成改写。';

    // 显示分拆出口按钮
    const actions = document.getElementById('output-actions');
    if (actions) actions.classList.remove('hidden');
  } catch (e) {
    status.textContent = '请求失败：' + e;
  }
});

// ==================== 事实核查 ====================

// 记录核查通过后待执行的动作（'graphic' | 'video' | null）
let _pendingAction = null;

async function runFactCheck(pendingAction) {
  const text = document.getElementById('output-rewrite').value.trim();
  if (!text) { alert('请先生成改写结果。'); return; }

  _pendingAction = pendingAction || null;

  // 打开 modal，重置状态
  const modal = document.getElementById('fact-check-modal');
  document.getElementById('fc-loading').classList.remove('hidden');
  document.getElementById('fc-result').classList.add('hidden');
  document.getElementById('fc-footer').classList.add('hidden');
  document.getElementById('fc-badge').classList.add('hidden');
  modal.classList.remove('hidden');
  if (window.lucide) lucide.createIcons();

  try {
    const resp = await fetch('/api/fact_check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '核查失败');

    renderFactCheckResult(data);
  } catch (e) {
    document.getElementById('fc-loading').classList.add('hidden');
    const resultEl = document.getElementById('fc-result');
    resultEl.innerHTML = `<div class="text-sm text-red-500 py-4 text-center">核查请求失败：${e.message}</div>`;
    resultEl.classList.remove('hidden');
    document.getElementById('fc-footer').classList.remove('hidden');
    document.getElementById('fc-summary').textContent = '';
    document.getElementById('fc-confirm-btn').onclick = closeFactCheck;
  }
}

function renderFactCheckResult(data) {
  document.getElementById('fc-loading').classList.add('hidden');

  const badge = document.getElementById('fc-badge');
  badge.classList.remove('hidden');
  const issues = data.issues || [];
  const passed = data.passed !== false && issues.length === 0;

  if (passed) {
    badge.textContent = '✓ 通过';
    badge.className = 'text-[10px] px-2 py-0.5 rounded-full font-semibold bg-[#E8FFF5] text-[#00B894]';
  } else {
    badge.textContent = `⚠ ${issues.length} 处待核实`;
    badge.className = 'text-[10px] px-2 py-0.5 rounded-full font-semibold bg-[#FFF0DD] text-[#E17055]';
  }

  const resultEl = document.getElementById('fc-result');
  if (passed) {
    resultEl.innerHTML = `
      <div class="flex flex-col items-center gap-3 py-6">
        <div class="w-12 h-12 rounded-full bg-[#E8FFF5] flex items-center justify-center text-2xl">✓</div>
        <p class="text-sm font-semibold text-[#00B894]">事实核查通过</p>
        <p class="text-xs text-gray-400 text-center">${escHtmlFc(data.summary || '文案中未发现明显事实性问题，可以放心使用。')}</p>
      </div>`;
  } else {
    let html = `<p class="text-xs text-gray-500 mb-3">${escHtmlFc(data.summary || '')}</p>`;
    issues.forEach((issue, i) => {
      html += `
        <div class="rounded-xl border border-[#FDCB6E]/60 bg-[#FFFAF2] p-3.5 space-y-1.5">
          <div class="flex items-start gap-2">
            <span class="mt-0.5 text-[10px] font-bold text-[#E17055] bg-[#FFF0DD] px-1.5 py-0.5 rounded shrink-0">#${i + 1}</span>
            <p class="text-xs font-semibold text-gray-700 leading-relaxed">"${escHtmlFc(issue.claim || '')}"</p>
          </div>
          <div class="flex items-start gap-1.5 pl-6">
            <span class="text-[10px] text-[#E17055] shrink-0 mt-0.5">疑问：</span>
            <p class="text-[11px] text-gray-600">${escHtmlFc(issue.reason || '')}</p>
          </div>
          <div class="flex items-start gap-1.5 pl-6">
            <span class="text-[10px] text-[#6C5CE7] shrink-0 mt-0.5">建议：</span>
            <p class="text-[11px] text-gray-500">${escHtmlFc(issue.suggestion || '')}</p>
          </div>
        </div>`;
    });
    resultEl.innerHTML = html;
  }
  resultEl.classList.remove('hidden');

  // 底部
  const footer = document.getElementById('fc-footer');
  footer.classList.remove('hidden');
  document.getElementById('fc-summary').textContent = passed
    ? '文案可信度良好，建议直接使用。'
    : `发现 ${issues.length} 处待核实内容，建议修改后再发布。`;

  const confirmBtn = document.getElementById('fc-confirm-btn');
  if (passed) {
    confirmBtn.textContent = '确认使用';
    confirmBtn.className = 'px-4 py-1.5 rounded-lg bg-[#00B894] text-white text-xs font-semibold hover:bg-[#00a381] transition-colors';
  } else {
    confirmBtn.textContent = '忽略风险，仍然使用';
    confirmBtn.className = 'px-4 py-1.5 rounded-lg bg-gray-400 text-white text-xs font-semibold hover:bg-gray-500 transition-colors';
  }
  confirmBtn.onclick = () => {
    closeFactCheck();
    if (_pendingAction === 'graphic') goToGraphic();
    else if (_pendingAction === 'video') goToVideo();
  };
}

function closeFactCheck() {
  document.getElementById('fact-check-modal').classList.add('hidden');
  _pendingAction = null;
}

function escHtmlFc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ==================== 分拆出口：图文 / 视频 ====================

// 图文生成（原小红书生成器逻辑）
async function goToGraphic() {
  const sel = document.getElementById('item-select');
  const idx = sel && sel.value ? parseInt(sel.value, 10) : 0;
  const item = items[idx] || null;
  const content = document.getElementById('output-rewrite').value.trim();
  if (!content) { alert('请先生成改写结果。'); return; }

  const rawLine = content.split('\n')[0].trim().replace(/^#+\s*/, '').replace(/^【[^】]*】\s*/, '').trim();
  const baseTitle = rawLine || (item && item.title) || '情报速递';
  const title = ('【情报速递】' + baseTitle).slice(0, 20);

  const selectedImgs = allImages.filter(img => img.selected);
  const btn = document.getElementById('btn-to-graphic-from-rewrite');
  if (btn) btn.disabled = true;

  try {
    const resp = await fetch('/api/images_to_xhs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_urls: selectedImgs.map(img => img.url),
        title,
        content,
        tag: '游戏雷达局',
        desc: '#游戏资讯# #游戏新闻# #主机游戏# #游戏# #游戏雷达局#',
      })
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '跳转失败');
    window.open('/xhs_full?token=' + data.token, '_blank');
  } catch (e) {
    alert('跳转失败：' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// 视频生成
function goToVideo() {
  const sel = document.getElementById('item-select');
  const idx = sel && sel.value ? parseInt(sel.value, 10) : 0;
  const item = items[idx] || null;
  const script = document.getElementById('output-rewrite').value.trim();
  if (!script) { alert('请先生成改写结果，再发送到视频生成。'); return; }

  if (rewriteMode === 'video') {
    // 跳转脚本预览配图页
    try {
      sessionStorage.setItem('scriptPreviewData', JSON.stringify({
        items: items,
        script_text: script,
        base_item: item,
      }));
    } catch(e) {}
    window.location.href = '/script_preview';
  } else {
    // 文字改写模式：直接去视频页（兼容旧流程）
    const payload = {
      items: [{ ...(item || {}), content: script, _is_script: true }]
    };
    try { sessionStorage.setItem('videoItems', JSON.stringify(payload)); } catch(e) {}
    window.location.href = '/video';
  }
}

document.getElementById('btn-to-graphic-from-rewrite')?.addEventListener('click', () => runFactCheck('graphic'));
document.getElementById('btn-to-video-from-rewrite')?.addEventListener('click', () => runFactCheck('video'));
document.getElementById('btn-to-script-preview')?.addEventListener('click', () => runFactCheck('video'));

// 保留旧 btn-open-xhs-generator 兼容（如 HTML 里还有引用）
document.getElementById('btn-open-xhs-generator')?.addEventListener('click', goToGraphic);

// ==================== 一键发布小红书 ====================

let attachedFiles = [];

document.getElementById('xhs-images')?.addEventListener('change', function() {
  const files = Array.from(this.files || []);
  if (!files.length) return;
  // 追加新文件，最多 9 张
  attachedFiles = attachedFiles.concat(files).slice(0, 9);
  renderImagePreviews();
  this.value = '';
});

function renderImagePreviews() {
  const container = document.getElementById('xhs-image-previews');
  const countEl = document.getElementById('xhs-image-count');
  container.innerHTML = '';
  countEl.textContent = attachedFiles.length ? `已选 ${attachedFiles.length} 张图片` : '';
  attachedFiles.forEach((file, i) => {
    const url = URL.createObjectURL(file);
    const wrap = document.createElement('div');
    wrap.className = 'relative group';
    wrap.innerHTML = `
      <img src="${url}" class="w-12 h-12 rounded-lg object-cover border border-gray-200">
      <button class="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" data-idx="${i}">&times;</button>
    `;
    wrap.querySelector('button').addEventListener('click', () => {
      attachedFiles.splice(i, 1);
      renderImagePreviews();
    });
    container.appendChild(wrap);
  });
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

document.getElementById('btn-xhs-publish')?.addEventListener('click', async () => {
  const statusEl = document.getElementById('xhs-publish-status');
  const desc = document.getElementById('output-rewrite').value.trim();

  if (!desc) {
    alert('请先生成改写结果。');
    return;
  }
  if (!attachedFiles.length) {
    alert('小红书要求至少上传一张图片，请先点击「附加图片」添加。');
    return;
  }

  const rawLineP = desc.split('\n')[0].trim().replace(/^#+\s*/, '').replace(/^【[^】]*】\s*/, '').trim();
  const baseTitle = rawLineP || '情报速递';
  const title = ('【情报速递】' + baseTitle).slice(0, 20);

  const cookie = window.prompt('请粘贴当前有效的小红书 Cookie：');
  if (!cookie) return;

  try {
    // Step 1: 将图片转为 base64
    statusEl.textContent = '正在处理图片...';
    const images = [];
    for (const file of attachedFiles) {
      images.push(await fileToBase64(file));
    }

    // Step 2: 上传图片到服务器
    statusEl.textContent = `正在上传 ${images.length} 张图片...`;
    const uploadResp = await fetch('/api/upload_images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ images })
    });
    const uploadData = await uploadResp.json();
    if (uploadData.status !== 'ok') {
      statusEl.textContent = '上传失败：' + (uploadData.message || '');
      return;
    }

    // Step 3: 发布
    statusEl.textContent = '正在发布到小红书...';
    const publishResp = await fetch('/xhs_api_publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, desc, cookie, image_token: uploadData.token })
    });
    const publishData = await publishResp.json();
    if (publishData.status !== 'ok') {
      statusEl.innerHTML = `<span class="text-red-500 font-semibold">发布失败：${publishData.message || ''}</span>`;
      alert('发布失败：' + (publishData.message || '未知错误'));
      return;
    }
    statusEl.innerHTML = '<span class="text-green-600 font-semibold">发布成功！</span>';
    if (publishData.url) {
      window.open(publishData.url, '_blank');
      statusEl.innerHTML += ` <a href="${publishData.url}" target="_blank" class="text-blue-500 underline">查看笔记</a>`;
    }
    alert('发布成功！笔记已发布到小红书。' + (publishData.url ? '\n链接：' + publishData.url : ''));
  } catch (e) {
    statusEl.innerHTML = `<span class="text-red-500 font-semibold">发布出错：${e}</span>`;
    alert('发布出错：' + e);
  }
});

// ==================== 游戏截图搜索 ====================

document.getElementById('btn-find-images').addEventListener('click', async () => {
  const sel  = document.getElementById('item-select');
  const idx  = parseInt(sel.value || '0', 10);
  const item = items[idx];
  if (!item || item.source !== 'gamersky') return;

  const btn    = document.getElementById('btn-find-images');
  const status = document.getElementById('images-status');
  const panel  = document.getElementById('images-panel');

  // 收集页面 URL：原文 URL + 已找到的来源 URL
  const urls = [item.url].filter(Boolean)
    .concat(extraSources.map(s => s.url).filter(Boolean));

  btn.disabled = true;
  btn.innerHTML = '<svg class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 搜索中...';
  panel.classList.remove('hidden');
  status.textContent = '正在从文章页面提取游戏截图，请稍候…';
  document.getElementById('images-grid').innerHTML = '';
  document.getElementById('images-count').textContent = '';

  try {
    const resp = await fetch('/api/fetch_images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls })
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}，请重启后端服务后重试`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '提取失败');

    allImages = (data.images || []).map(img => ({ ...img, selected: false }));
    renderImagesGrid();
    status.textContent = allImages.length
      ? '点击图片可选中/取消，勾选后点击「插入图文生成器」。'
      : '未找到相关截图，可先「查找更多来源」后再试。';
  } catch (e) {
    status.textContent = '查找失败：' + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i data-lucide="image" class="w-3 h-3"></i> 查找游戏截图';
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }
});

function renderImagesGrid() {
  const grid      = document.getElementById('images-grid');
  const countEl   = document.getElementById('images-count');
  const insertBtn = document.getElementById('btn-insert-images');
  grid.innerHTML  = '';

  if (!allImages.length) {
    grid.innerHTML = '<p class="col-span-4 text-xs text-gray-400 py-1">暂无截图</p>';
    countEl.textContent = '';
    insertBtn.classList.add('hidden');
    insertBtn.classList.remove('flex');
    return;
  }

  const selectedCount = allImages.filter(img => img.selected).length;
  countEl.textContent = `共 ${allImages.length} 张，已选 ${selectedCount} 张`;

  if (selectedCount > 0) {
    insertBtn.classList.remove('hidden');
    insertBtn.classList.add('flex');
  } else {
    insertBtn.classList.add('hidden');
    insertBtn.classList.remove('flex');
  }

  allImages.forEach((img, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'relative group cursor-pointer';
    const borderClass = img.selected ? 'border-[#0984E3]' : 'border-gray-200';
    const checkBg     = img.selected ? 'bg-[#0984E3] border-[#0984E3] text-white' : 'bg-white/80 border-gray-300 text-transparent';
    const proxySrc    = '/api/proxy_image?url=' + encodeURIComponent(img.url);
    wrap.innerHTML = `
      <img src="${proxySrc}" alt="${escapeHtml(img.alt)}"
           class="w-full h-16 object-cover rounded-lg border-2 transition-all ${borderClass}"
           loading="lazy"
           onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
      <div class="w-full h-16 rounded-lg border-2 ${borderClass} bg-gray-100 items-center justify-center text-[9px] text-gray-400 text-center px-1 leading-tight hidden">${escapeHtml(img.alt || '图片')}</div>
      <div class="absolute top-1 right-1">
        <div class="w-4 h-4 rounded-full border-2 flex items-center justify-center text-[9px] font-bold transition-all ${checkBg}">✓</div>
      </div>
      ${img.alt ? `<div class="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-[9px] px-1 py-0.5 rounded-b-lg truncate opacity-0 group-hover:opacity-100 transition-opacity">${escapeHtml(img.alt)}</div>` : ''}`;
    wrap.addEventListener('click', () => {
      allImages[i].selected = !allImages[i].selected;
      renderImagesGrid();
    });
    grid.appendChild(wrap);
  });
}

document.getElementById('btn-insert-images').addEventListener('click', async () => {
  const selectedImgs = allImages.filter(img => img.selected);
  if (!selectedImgs.length) {
    alert('请先点击选择至少一张截图。');
    return;
  }

  const sel     = document.getElementById('item-select');
  const idx     = parseInt(sel.value || '0', 10);
  const item    = items[idx] || {};
  const content = document.getElementById('output-rewrite').value.trim()
               || document.getElementById('input-original').value.trim();
  const rawLine2 = content.split('\n')[0].trim().replace(/^#+\s*/, '').replace(/^【[^】]*】\s*/, '').trim();
  const baseTitle2 = rawLine2 || item.title || '情报速递';
  const title = ('【情报速递】' + baseTitle2).slice(0, 20);

  const status  = document.getElementById('images-status');
  const btn     = document.getElementById('btn-insert-images');
  btn.disabled  = true;
  status.textContent = `正在处理 ${selectedImgs.length} 张图片，请稍候…`;

  try {
    const resp = await fetch('/api/images_to_xhs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_urls: selectedImgs.map(img => img.url),
        title,
        content,
        tag: '游戏雷达局',
        desc: '#游戏资讯# #游戏新闻# #主机游戏# #游戏# #游戏雷达局#',
      })
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '跳转失败');

    window.open('/xhs_full?token=' + data.token, '_blank');
    status.textContent = `已在新标签页打开小红书生成器，${selectedImgs.length} 张截图已自动插入。`;
  } catch (e) {
    status.textContent = '插入失败：' + e.message;
  } finally {
    btn.disabled = false;
  }
});

// Reddit 截图翻译已移至 /reddit_edit 页面

function showPublishPanel(images, title, content) {
  const panel = document.getElementById('reddit-publish-panel');
  panel.classList.remove('hidden');

  // 缩略图
  const thumbs = document.getElementById('publish-image-thumbs');
  thumbs.innerHTML = '';
  images.forEach((imgData, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'flex flex-col items-center gap-1 flex-shrink-0';
    const img = document.createElement('img');
    img.src       = imgData;
    img.className = 'rounded-lg border border-gray-700 object-top';
    img.style.cssText = 'height:96px;max-width:72px;object-fit:cover;';
    const label = document.createElement('span');
    label.className   = 'text-[9px] text-gray-400';
    label.textContent = `长图 ${i + 1}`;
    wrap.appendChild(img);
    wrap.appendChild(label);
    thumbs.appendChild(wrap);
  });

  document.getElementById('publish-title').value   = title;
  document.getElementById('publish-content').value = content;
  document.getElementById('publish-status').textContent = '';
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function publishDirectly() {
  const images  = _redditPublishImages;
  const title   = document.getElementById('publish-title').value.trim();
  const content = document.getElementById('publish-content').value.trim();
  const cookie  = document.getElementById('publish-cookie').value.trim();

  if (!images.length)       { alert('请先点击「生成长图」。'); return; }
  if (!cookie)              { alert('请输入小红书 Cookie。'); return; }
  if (!title || !content)   { alert('请填写标题和文案。'); return; }

  const btn    = document.getElementById('btn-publish-direct');
  const status = document.getElementById('publish-status');
  btn.disabled = true;
  status.textContent = '正在发布到小红书，请稍候…';

  try {
    const resp = await fetch('/api/publish_reddit_direct', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ image_b64s: images, title, content, cookie }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '发布失败');

    status.innerHTML = '<span class="text-green-600 font-semibold">发布成功！</span>';
    if (data.url) {
      status.innerHTML += ` <a href="${data.url}" target="_blank" class="text-blue-500 underline text-xs">查看笔记</a>`;
    }
  } catch (e) {
    status.textContent = '发布失败：' + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function openInXhsEditor() {
  const images  = _redditPublishImages;
  const title   = document.getElementById('publish-title').value.trim();
  const content = document.getElementById('publish-content').value.trim();
  const status  = document.getElementById('publish-status');
  status.textContent = '正在跳转到编辑器…';

  try {
    const resp = await fetch('/api/cards_to_xhs', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ image_b64s: images, title, content, tag: '游戏雷达局' }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '跳转失败');
    window.open('/xhs_full?token=' + data.token, '_blank');
    status.textContent = '已在新标签页打开小红书生成器。';
  } catch (e) {
    status.textContent = '跳转失败：' + e.message;
  }
}

initFromSession();
refreshItemSelect();
