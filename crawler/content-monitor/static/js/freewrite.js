// 已收集的来源列表（跨搜索累积）
let fwSources = [];  // {title, url, domain, content, selected}

// ── 主题输入同步到搜索框 ────────────────────────────────────
function syncTopicToSearch() {
  const topic = document.getElementById('fw-topic').value.trim();
  const searchInput = document.getElementById('fw-search-input');
  if (!searchInput.value || searchInput.dataset.autoFilled === 'true') {
    searchInput.value = topic;
    searchInput.dataset.autoFilled = 'true';
  }
}

document.getElementById('fw-search-input').addEventListener('input', function () {
  this.dataset.autoFilled = 'false';
});

// ── 主题框回车 / "全网搜索"按钮 ─────────────────────────────
function doFwSearch() {
  const topic = document.getElementById('fw-topic').value.trim();
  if (!topic) {
    document.getElementById('fw-search-status').textContent = '请先输入想写的主题。';
    return;
  }
  document.getElementById('fw-search-input').value = topic;
  document.getElementById('fw-search-input').dataset.autoFilled = 'true';
  doFwSearchKeyword();
}

// ── Bing 关键词搜索 ──────────────────────────────────────────
async function doFwSearchKeyword() {
  const query = document.getElementById('fw-search-input').value.trim();
  if (!query) {
    document.getElementById('fw-search-kw-status').textContent = '请输入搜索关键词。';
    return;
  }

  const btn    = document.getElementById('fw-btn-search');
  const status = document.getElementById('fw-search-kw-status');
  btn.disabled = true;
  btn.textContent = '搜索中…';
  status.textContent = `正在 Bing 搜索「${query}」，请稍候…`;

  try {
    const resp = await fetch('/api/fetch_sources', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ query, num: 6 }),
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '搜索失败');

    const newSources = (data.sources || []).map(s => ({ ...s, selected: true }));
    const existingUrls = new Set(fwSources.map(s => s.url));
    newSources.forEach(s => { if (!existingUrls.has(s.url)) fwSources.push(s); });

    renderFwSources();
    updateFwButton();
    status.textContent = newSources.length
      ? `找到 ${newSources.length} 条新来源，已加入列表。`
      : '未找到新的相关内容，换个关键词试试。';
  } catch (e) {
    status.textContent = '搜索失败：' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '搜索';
  }
}

// ── 自定义 URL 行管理 ────────────────────────────────────────
function addFwUrlRow(btn) {
  const list = document.getElementById('fw-url-list');
  const row = document.createElement('div');
  row.className = 'flex gap-1.5 fw-url-row';
  row.innerHTML = `
    <input type="url" placeholder="https://..."
           class="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-[#E17055] fw-url-input transition-all">
    <button onclick="this.closest('.fw-url-row').remove()"
            class="px-2.5 py-1.5 rounded-lg border border-gray-200 text-red-400 hover:border-red-400 text-sm leading-none transition-colors">×</button>`;
  if (btn) {
    btn.textContent = '×';
    btn.className = 'px-2.5 py-1.5 rounded-lg border border-gray-200 text-red-400 hover:border-red-400 text-sm leading-none transition-colors';
    btn.onclick = () => btn.closest('.fw-url-row').remove();
  }
  list.appendChild(row);
}

// ── 抓取自定义链接 ───────────────────────────────────────────
async function doFwFetchUrls() {
  const inputs = document.querySelectorAll('#fw-url-list .fw-url-input');
  const urls = Array.from(inputs).map(i => i.value.trim()).filter(u => u.startsWith('http'));
  if (!urls.length) {
    document.getElementById('fw-url-status').textContent = '请先填入有效的 http(s) 链接。';
    return;
  }

  const btn    = document.getElementById('fw-btn-fetch');
  const status = document.getElementById('fw-url-status');
  btn.disabled = true;
  btn.textContent = `正在抓取 ${urls.length} 个链接…`;
  status.textContent = '';

  try {
    const resp = await fetch('/api/fetch_urls', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ urls }),
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '抓取失败');

    const newSources = (data.sources || []).map(s => ({ ...s, selected: true }));
    const existingUrls = new Set(fwSources.map(s => s.url));
    newSources.forEach(s => { if (!existingUrls.has(s.url)) fwSources.push(s); });

    renderFwSources();
    updateFwButton();
    status.textContent = newSources.length
      ? `成功抓取 ${newSources.length} 个，已加入来源列表。`
      : '抓取完成，但未能获取到有效正文（可能需要登录或被防爬）。';
  } catch (e) {
    status.textContent = '抓取失败：' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '抓取以上链接内容';
  }
}

// ── 渲染来源列表 ─────────────────────────────────────────────
function renderFwSources() {
  const list  = document.getElementById('fw-sources-list');
  const count = document.getElementById('fw-sources-count');
  list.innerHTML = '';

  if (!fwSources.length) {
    list.innerHTML = '<p class="text-xs text-gray-400 text-center py-6">搜索或粘贴链接后，来源会出现在这里</p>';
    count.textContent = '';
    return;
  }

  const selected = fwSources.filter(s => s.selected).length;
  count.textContent = `共 ${fwSources.length} 条，已选 ${selected} 条`;

  fwSources.forEach((src, i) => {
    const row = document.createElement('label');
    row.className = 'flex items-start gap-2.5 p-2.5 rounded-lg border border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors';
    row.innerHTML = `
      <input type="checkbox" class="mt-0.5 shrink-0" style="accent-color:#E17055;" ${src.selected ? 'checked' : ''}>
      <div class="min-w-0 flex-1">
        <div class="text-xs font-semibold text-gray-700 truncate">${escFw(src.title)}</div>
        <div class="text-[10px] text-gray-400 truncate">${escFw(src.domain)} · ${escFw(src.url)}</div>
        <div class="text-[10px] text-gray-500 mt-0.5 line-clamp-2">${escFw((src.content || '').slice(0, 120))}…</div>
      </div>
      <button onclick="removeFwSource(${i})" class="shrink-0 text-gray-300 hover:text-red-400 transition-colors ml-1 mt-0.5">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>`;
    row.querySelector('input').addEventListener('change', (e) => {
      fwSources[i].selected = e.target.checked;
      const sel = fwSources.filter(s => s.selected).length;
      count.textContent = `共 ${fwSources.length} 条，已选 ${sel} 条`;
      updateFwButton();
    });
    list.appendChild(row);
  });
}

function removeFwSource(i) {
  fwSources.splice(i, 1);
  renderFwSources();
  updateFwButton();
}

function clearFwSources() {
  fwSources = [];
  renderFwSources();
  updateFwButton();
}

// ── 生成按钮状态 ─────────────────────────────────────────────
function updateFwButton() {
  const btn  = document.getElementById('fw-btn-generate');
  const hint = document.getElementById('fw-hint');
  const selected = fwSources.filter(s => s.selected);
  if (selected.length > 0) {
    btn.disabled = false;
    hint.textContent = `将融合 ${selected.length} 条来源生成文章`;
  } else {
    btn.disabled = true;
    hint.textContent = '收集至少 1 条来源后可生成';
  }
}

// ── 融合改写 ─────────────────────────────────────────────────
async function doFwGenerate() {
  const topic    = document.getElementById('fw-topic').value.trim();
  const tone     = document.getElementById('fw-tone').value;
  const prompt   = document.getElementById('fw-prompt').value.trim();
  const status   = document.getElementById('fw-generate-status');
  const output   = document.getElementById('fw-output');
  const xhsBtn   = document.getElementById('fw-btn-to-xhs');

  const selected = fwSources.filter(s => s.selected);
  if (!selected.length) {
    alert('请先收集至少 1 条来源。');
    return;
  }

  // 第一条来源作 original，其余作 extra_sources
  const original = selected[0].content
    ? `主题：${topic || selected[0].title}\n\n${selected[0].content}`
    : `主题：${topic || selected[0].title}`;
  const extraSources = selected.slice(1).map(s => ({
    title:   s.title,
    url:     s.url,
    content: s.content,
  }));

  const btn = document.getElementById('fw-btn-generate');
  btn.disabled = true;
  output.value = '';
  xhsBtn.style.display = 'none';
  status.textContent = selected.length > 1
    ? `正在融合 ${selected.length} 个来源撰写，请稍候…`
    : '正在 AI 撰写，请稍候…';

  try {
    const resp = await fetch('/api/rewrite', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        prompt,
        tone,
        original,
        item:          { title: topic || selected[0].title },
        extra_sources: extraSources,
      }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '未知错误');
    output.value = data.text || '';
    status.textContent = `完成，融合了 ${selected.length} 条来源。`;
    xhsBtn.style.display = 'flex';
  } catch (e) {
    status.textContent = '生成失败：' + e.message;
  } finally {
    btn.disabled = false;
    updateFwButton();
  }
}

// ── 进入图文生成器 ───────────────────────────────────────────
async function openFwInEditor() {
  const content = document.getElementById('fw-output').value.trim();
  if (!content) { alert('请先生成文章。'); return; }

  const rawLine = content.split('\n')[0].trim().replace(/^#+\s*/, '').replace(/^【[^】]*】\s*/, '').trim();
  const topic   = document.getElementById('fw-topic').value.trim();
  const base    = rawLine || topic || '情报速递';
  const title   = ('【情报速递】' + base).slice(0, 20);

  const btn    = document.getElementById('fw-btn-to-xhs');
  const status = document.getElementById('fw-generate-status');
  btn.disabled = true;
  status.textContent = '正在跳转到图文生成器…';

  try {
    const resp = await fetch('/api/images_to_xhs', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        image_urls: [],
        title,
        content,
        tag:  '游戏雷达局',
        desc: '#游戏资讯# #游戏新闻# #主机游戏# #游戏# #游戏雷达局#',
      }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '跳转失败');
    window.open('/xhs_full?token=' + data.token, '_blank');
    status.textContent = '已在新标签页打开图文生成器。';
  } catch (e) {
    status.textContent = '跳转失败：' + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ── 工具函数 ─────────────────────────────────────────────────
function escFw(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
