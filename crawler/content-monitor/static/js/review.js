let reviewResults = [];   // 当前搜索结果
let savedArticles = [];   // 跨搜索持久保存的文章
let currentGameName = '';
let currentToken    = '';

// Steam 状态
let steamGames       = [];   // [{appid, name, image}] 搜索结果
let steamSelectedGame = null; // {appid, name, image}
let steamFormatted   = '';   // format_for_ai 输出，融入生成
let steamLoaded      = false;

// ── 工具 ──────────────────────────────────────────────
function escapeHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

const SOURCE_COLORS = {
  gcores:       { bg: '#1a1a2e', text: '#e94560' },
  youxichaguan: { bg: '#1a2e1a', text: '#2E7D32' },
  gamersky:     { bg: '#1a3a1a', text: '#4CAF50' },
  ign:          { bg: '#1a1a3a', text: '#5C6BC0' },
  yxrb:         { bg: '#2e1a1a', text: '#E53935' },
  vgn:          { bg: '#2e1a2e', text: '#9C27B0' },
  bing:         { bg: '#1a2a3a', text: '#0078D4' },
};

// ── 搜索（不清空已收藏）──────────────────────────────
async function searchReviews() {
  const gameName = document.getElementById('game-name-input').value.trim();
  if (!gameName) { alert('请输入游戏名称'); return; }

  currentGameName = gameName;
  currentToken    = '';

  // 同步 Steam 搜索框（如果是空的）
  const steamInput = document.getElementById('steam-search-input');
  if (steamInput && !steamInput.value) steamInput.value = gameName;

  const statusEl = document.getElementById('search-status');
  const listEl   = document.getElementById('results-list');
  const countEl  = document.getElementById('results-count');

  statusEl.textContent = `正在从机核、游戏茶馆、游民星空、IGN中文、游戏日报、游戏动力搜索「${gameName}」，请稍候（约 20-40 秒）…`;
  listEl.innerHTML     = '<p class="text-xs text-gray-400 text-center py-8 animate-pulse">搜索中…</p>';
  countEl.textContent  = '';

  try {
    const resp = await fetch('/api/search_reviews', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ game_name: gameName }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '搜索失败');

    reviewResults = data.results || [];
    renderResultsList();

    statusEl.textContent = reviewResults.length
      ? `找到 ${reviewResults.length} 篇，点击「存入」加入下方收藏池后可继续换关键词搜索。`
      : `未找到「${gameName}」的相关评测，请换个关键词试试。`;
  } catch (e) {
    statusEl.textContent = '搜索失败：' + e.message;
    listEl.innerHTML = '<p class="text-xs text-red-400 text-center py-8">' + escapeHtml(e.message) + '</p>';
  }
}

// ── 存入 / 移除 ────────────────────────────────────────
function addToSaved(idx) {
  const item = reviewResults[idx];
  if (!item) return;
  if (savedArticles.some(s => s.url === item.url)) return;  // 已存在
  savedArticles.push({ ...item });
  renderSavedList();
  renderResultsList();  // 更新"已存入"状态
}

function addAllToSaved() {
  reviewResults.forEach(item => {
    if (!savedArticles.some(s => s.url === item.url)) {
      savedArticles.push({ ...item });
    }
  });
  renderSavedList();
  renderResultsList();
}

function removeFromSaved(idx) {
  savedArticles.splice(idx, 1);
  renderSavedList();
  renderResultsList();
}

function clearSaved() {
  if (!savedArticles.length) return;
  if (!confirm(`确认清空全部 ${savedArticles.length} 篇已收藏文章？`)) return;
  savedArticles = [];
  renderSavedList();
  renderResultsList();
}

// ── 渲染搜索结果（每条有「存入」按钮）─────────────────
function renderResultsList() {
  const listEl  = document.getElementById('results-list');
  const countEl = document.getElementById('results-count');
  listEl.innerHTML = '';

  if (!reviewResults.length) {
    listEl.innerHTML = '<p class="text-xs text-gray-400 text-center py-8">未找到相关评测</p>';
    countEl.textContent = '';
    return;
  }

  const savedUrls = new Set(savedArticles.map(s => s.url));
  countEl.textContent = `共 ${reviewResults.length} 篇`;

  reviewResults.forEach((item, i) => {
    const colors  = SOURCE_COLORS[item.source_id] || { bg: '#1a1a2e', text: '#9999ff' };
    const isSaved = savedUrls.has(item.url);
    const dateHtml = item.date_str
      ? `<span class="text-[9px] text-gray-400 ml-1">${escapeHtml(item.date_str)}</span>` : '';

    const row = document.createElement('div');
    row.className = 'flex items-start gap-3 p-3 rounded-xl border transition-colors '
      + (isSaved ? 'border-[#F39C12]/40 bg-[#FFF9EC]' : 'border-gray-100 hover:bg-gray-50');
    row.innerHTML = `
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 mb-1 flex-wrap">
          <span class="text-[10px] font-bold px-2 py-0.5 rounded-full"
                style="background:${colors.bg};color:${colors.text};">${escapeHtml(item.source_name)}</span>
          <a href="${escapeHtml(item.url)}" target="_blank"
             class="text-[10px] text-gray-400 hover:text-[#F39C12] truncate max-w-[140px]"
             onclick="event.stopPropagation()">${escapeHtml(item.url.replace(/^https?:\/\//,'').slice(0,35))}…</a>
          ${dateHtml}
        </div>
        <div class="text-xs font-semibold text-gray-700 mb-1 line-clamp-1">${escapeHtml(item.title)}</div>
        <div class="text-[10px] text-gray-500 line-clamp-2">${escapeHtml(item.content_preview)}</div>
      </div>
      <button data-idx="${i}"
              class="shrink-0 mt-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-all ${
                isSaved
                  ? 'bg-[#F39C12]/15 text-[#F39C12] cursor-default'
                  : 'border border-[#F39C12] text-[#F39C12] hover:bg-[#F39C12] hover:text-white'
              }"
              ${isSaved ? 'disabled' : ''}>
        ${isSaved ? '✓ 已存入' : '+ 存入'}
      </button>`;
    if (!isSaved) {
      row.querySelector('button').addEventListener('click', () => addToSaved(i));
    }
    listEl.appendChild(row);
  });
}

// ── 渲染已收藏面板 ─────────────────────────────────────
function renderSavedList() {
  const panel   = document.getElementById('saved-panel');
  const listEl  = document.getElementById('saved-list');
  const countEl = document.getElementById('saved-count');
  const btn      = document.getElementById('btn-generate');
  const deepBtn  = document.getElementById('btn-deep-review');
  const toXhsBtn = document.getElementById('btn-to-xhs');

  if (!savedArticles.length) {
    panel.classList.add('hidden');
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="wand-2" class="w-3.5 h-3.5"></i> 生成评测';
    if (typeof lucide !== 'undefined') lucide.createIcons({ el: btn });
    // 深度按钮：无来源时仅 steam 已加载时才允许
    if (deepBtn) deepBtn.disabled = !steamLoaded;
    return;
  }

  panel.classList.remove('hidden');
  countEl.textContent = `${savedArticles.length} 篇`;
  btn.disabled = false;
  btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="m19 7-1.4 1.4"/><path d="M11.6 7 10.2 8.4"/><path d="m10.2 15.6 1.4-1.4"/><path d="m17 16 1.4-1.4"/><path d="m12 12-5 5"/><path d="m14.5 9.5-5 5"/></svg> 生成评测（${savedArticles.length} 篇）`;
  if (deepBtn) deepBtn.disabled = false;

  listEl.innerHTML = '';
  savedArticles.forEach((item, i) => {
    const colors = SOURCE_COLORS[item.source_id] || { bg: '#1a1a2e', text: '#9999ff' };
    const row = document.createElement('div');
    row.className = 'flex items-center gap-2 py-1.5 px-2 rounded-lg bg-white border border-gray-100';
    row.innerHTML = `
      <span class="text-[9px] font-bold px-1.5 py-0.5 rounded-full shrink-0"
            style="background:${colors.bg};color:${colors.text};">${escapeHtml(item.source_name)}</span>
      <span class="text-[11px] text-gray-700 flex-1 truncate" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</span>
      <button class="shrink-0 w-4 h-4 rounded-full bg-gray-200 hover:bg-red-100 hover:text-red-500 text-gray-500 text-[10px] flex items-center justify-center transition-colors leading-none"
              data-ridx="${i}">×</button>`;
    row.querySelector('button').addEventListener('click', () => removeFromSaved(i));
    listEl.appendChild(row);
  });
}

// ── 生成评测（使用已收藏）──────────────────────────────
async function generateReview() {
  if (!savedArticles.length) { alert('请先将文章存入收藏池。'); return; }

  const userOpinion = document.getElementById('user-opinion').value.trim();
  const statusEl    = document.getElementById('generate-status');
  const outputEl    = document.getElementById('output-article');
  const btn         = document.getElementById('btn-generate');
  const toXhsBtn    = document.getElementById('btn-to-xhs');

  btn.disabled = true;
  statusEl.textContent = `正在融合 ${savedArticles.length} 篇来源生成评测，请稍候（约 20-40 秒）…`;
  outputEl.value = '';
  toXhsBtn.classList.add('hidden');
  toXhsBtn.classList.remove('flex');

  // 附加 Steam 评论源（如果已加载且勾选）
  const steamIncludeEl = document.getElementById('steam-include');
  const includeSteam = steamLoaded && steamFormatted
    && steamIncludeEl && steamIncludeEl.checked;
  const allSources = savedArticles.map(s => ({
    source_name: s.source_name,
    title:       s.title,
    url:         s.url,
    content:     s.content,
  }));
  if (includeSteam) {
    allSources.push({
      source_name: 'Steam玩家评论',
      title:       `${steamSelectedGame?.name || ''} - Steam玩家评论`,
      url:         `https://store.steampowered.com/app/${steamSelectedGame?.appid}/reviews/`,
      content:     steamFormatted,
    });
    statusEl.textContent = `正在融合 ${savedArticles.length} 篇媒体来源 + Steam玩家评论生成评测，请稍候…`;
  }

  try {
    const resp = await fetch('/api/generate_review', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        game_name:    currentGameName,
        sources:      allSources,
        user_opinion: userOpinion,
      }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '生成失败');

    outputEl.value = data.article || '';
    currentToken   = data.token  || '';
    statusEl.textContent = `评测已生成（融合了 ${savedArticles.length} 篇来源），可直接编辑后点击「进入图文生成器」。`;
    toXhsBtn.classList.remove('hidden');
    toXhsBtn.classList.add('flex');
  } catch (e) {
    statusEl.textContent = '生成失败：' + e.message;
  } finally {
    btn.disabled = false;
    renderSavedList();  // 恢复按钮文字
  }
}

// ── 深度评测长文 ──────────────────────────────────────
async function generateDeepReview() {
  const userOpinion = document.getElementById('user-opinion').value.trim();
  const statusEl    = document.getElementById('generate-status');
  const outputEl    = document.getElementById('output-article');
  const btn         = document.getElementById('btn-deep-review');
  const toXhsBtn    = document.getElementById('btn-to-xhs');

  if (!steamLoaded && !savedArticles.length) {
    alert('请先加载 Steam 评论，或收藏至少一篇媒体文章。');
    return;
  }

  const appid    = steamSelectedGame?.appid || '';
  const gameName = steamSelectedGame?.name  || currentGameName || '';
  if (!gameName) { alert('请先搜索并选择游戏。'); return; }

  btn.disabled = true;
  outputEl.value = '';
  toXhsBtn.classList.add('hidden');
  toXhsBtn.classList.remove('flex');

  const sourceCount = savedArticles.length;
  statusEl.textContent = appid
    ? `正在批量抓取全量 Steam 评论（最多5000条）并逐批送入 AI 分析，预计 60-120 秒…`
    : `正在融合 ${sourceCount} 篇媒体来源生成深度长文，请稍候…`;

  const mediaSources = savedArticles.map(s => ({
    source_name: s.source_name,
    title:       s.title,
    url:         s.url,
    content:     s.content,
  }));

  try {
    const resp = await fetch('/api/generate_deep_review', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        appid,
        game_name:    gameName,
        sources:      mediaSources,
        user_opinion: userOpinion,
      }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '生成失败');

    outputEl.value = data.article || '';
    currentToken   = data.token   || '';
    const sc = data.sample_count || 0;
    const bc = data.batch_count  || 0;
    statusEl.textContent = `深度长文已生成（Steam ${sc} 条评论 / ${bc} 批全量分析 + 媒体 ${sourceCount} 篇）。可编辑后进入图文生成器。`;
    toXhsBtn.classList.remove('hidden');
    toXhsBtn.classList.add('flex');
  } catch (e) {
    statusEl.textContent = '生成失败：' + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ── 进入图文生成器 ────────────────────────────────────
async function openXhsGenerator() {
  const article = document.getElementById('output-article').value.trim();
  if (!article) { alert('请先生成评测文章。'); return; }

  const statusEl = document.getElementById('generate-status');
  statusEl.textContent = '正在跳转到图文生成器…';

  try {
    const resp = await fetch('/api/cards_to_xhs', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        image_b64s: [],
        title:      `【游戏评测】${currentGameName}`.slice(0, 20),
        content:    article,
        tag:        '游戏雷达局',
      }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '跳转失败');
    window.open('/xhs_full?token=' + data.token, '_blank');
    statusEl.textContent = '已在新标签页打开小红书生成器。';
  } catch (e) {
    statusEl.textContent = '跳转失败：' + e.message;
  }
}

// ══════════════════════════════════════════════
// Steam 玩家评论
// ══════════════════════════════════════════════

function toggleSteamPanel() {
  const panel   = document.getElementById('steam-panel');
  const chevron = document.getElementById('steam-chevron');
  const isHidden = panel.classList.toggle('hidden');
  chevron.style.transform = isHidden ? '' : 'rotate(180deg)';
  // 展开时自动同步游戏名
  if (!isHidden) {
    const input = document.getElementById('steam-search-input');
    if (!input.value && currentGameName) input.value = currentGameName;
  }
}

async function searchSteamGame() {
  const query = document.getElementById('steam-search-input').value.trim();
  if (!query) return;

  const btn      = document.getElementById('btn-steam-search');
  const listEl   = document.getElementById('steam-games-list');
  const statusEl = document.getElementById('steam-status');
  btn.textContent = '搜索中…';
  btn.disabled = true;
  listEl.classList.add('hidden');
  listEl.innerHTML = '';
  statusEl.textContent = '';

  try {
    const resp = await fetch('/api/steam_search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game_name: query }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message);

    steamGames = data.games || [];
    if (!steamGames.length) {
      statusEl.textContent = '未找到相关游戏，请尝试英文名或更短的关键词。';
      return;
    }
    renderSteamGamesList();
  } catch (e) {
    statusEl.textContent = '搜索失败：' + e.message;
  } finally {
    btn.textContent = '查找';
    btn.disabled = false;
  }
}

function renderSteamGamesList() {
  const listEl = document.getElementById('steam-games-list');
  listEl.innerHTML = '';
  listEl.classList.remove('hidden');

  steamGames.forEach(g => {
    const row = document.createElement('button');
    row.className = 'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left hover:bg-gray-100 transition-colors';
    row.innerHTML = `
      ${g.image ? `<img src="${escapeHtml(g.image)}" class="w-10 h-5 rounded object-cover shrink-0" alt="">` : ''}
      <span class="text-xs text-gray-700 truncate flex-1">${escapeHtml(g.name)}</span>
      <span class="text-[9px] text-gray-400 shrink-0">App ${escapeHtml(g.appid)}</span>`;
    row.addEventListener('click', () => selectSteamGame(g));
    listEl.appendChild(row);
  });
}

function selectSteamGame(game) {
  steamSelectedGame = game;
  steamLoaded = false;
  steamFormatted = '';

  // 隐藏游戏列表，显示摘要区
  document.getElementById('steam-games-list').classList.add('hidden');
  const summary = document.getElementById('steam-summary');
  summary.classList.remove('hidden');
  document.getElementById('steam-game-img').src = game.image || '';
  document.getElementById('steam-game-title').textContent = game.name;
  document.getElementById('steam-score-line').textContent = '点击「加载玩家评论」获取评价数据';
  document.getElementById('steam-ratio-bar').style.width = '0%';
  document.getElementById('steam-ratio-text').textContent = '';

  // 清空旧评论预览
  document.getElementById('steam-reviews-preview').classList.add('hidden');
  document.getElementById('steam-reviews-preview').innerHTML = '';
  document.getElementById('steam-include-row').classList.add('hidden');
  document.getElementById('steam-include-row').classList.remove('flex');

  // 显示加载按钮
  document.getElementById('btn-load-reviews').classList.remove('hidden');
  document.getElementById('steam-badge').classList.add('hidden');
  document.getElementById('steam-status').textContent = `已选：${game.name}`;
}

async function loadSteamReviews() {
  if (!steamSelectedGame) return;

  const btn      = document.getElementById('btn-load-reviews');
  const statusEl = document.getElementById('steam-status');
  btn.disabled   = true;
  btn.textContent = '分析中…';
  statusEl.textContent = '正在抓取评论并进行深度分析（约 15~30 秒）…';

  try {
    const resp = await fetch('/api/steam_reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ appid: steamSelectedGame.appid, name: steamSelectedGame.name }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message);

    const s = data.summary || {};
    // 优先用 AI 分析结果作为融入生成的来源，fallback 到 formatted
    steamFormatted = data.analysis || data.formatted || '';
    steamLoaded = true;

    // 更新摘要
    document.getElementById('steam-score-line').textContent =
      `${s.score_desc || ''} · ${s.total?.toLocaleString() || 0} 条评论`;
    const ratio = s.positive_ratio || 0;
    document.getElementById('steam-ratio-bar').style.width = ratio + '%';
    document.getElementById('steam-ratio-bar').style.background = ratio >= 70 ? '#1a9c3e' : ratio >= 40 ? '#f39c12' : '#e74c3c';
    document.getElementById('steam-ratio-text').textContent = `好评率 ${ratio}%`;

    // 渲染评论预览
    renderSteamReviews(data.reviews || []);

    // 展示 AI 口碑分析
    const analysisText = data.analysis || '';
    if (analysisText) {
      document.getElementById('steam-analysis').textContent = analysisText;
      document.getElementById('steam-analysis-wrap').classList.remove('hidden');
    }

    // 显示融入选项
    const incRow = document.getElementById('steam-include-row');
    incRow.classList.remove('hidden');
    incRow.classList.add('flex');

    // badge
    const badge = document.getElementById('steam-badge');
    badge.textContent = `${ratio}% 好评`;
    badge.classList.remove('hidden');

    btn.classList.add('hidden');
    const sampleCount = data.reviews?.length || 0;
    statusEl.textContent = `已分析 ${sampleCount} 条评论，口碑分析已就绪。`;
    // 有 steam 数据后激活深度按钮
    const deepBtn = document.getElementById('btn-deep-review');
    if (deepBtn) deepBtn.disabled = false;
  } catch (e) {
    statusEl.textContent = '加载失败：' + e.message;
    btn.disabled = false;
    btn.textContent = '加载玩家评论';
  }
}

function renderSteamReviews(reviews) {
  const listEl = document.getElementById('steam-reviews-preview');
  listEl.innerHTML = '';
  listEl.classList.remove('hidden');

  if (!reviews.length) {
    listEl.innerHTML = '<p class="text-[10px] text-gray-400 py-1">暂无评论数据</p>';
    return;
  }

  reviews.slice(0, 12).forEach(r => {
    const div = document.createElement('div');
    div.className = 'flex gap-2 p-2 rounded-lg text-[10px] '
      + (r.voted_up ? 'bg-green-50 border border-green-100' : 'bg-red-50 border border-red-100');
    div.innerHTML = `
      <span class="shrink-0 font-bold ${r.voted_up ? 'text-green-600' : 'text-red-500'}">${r.voted_up ? '好评' : '差评'}</span>
      <span class="text-gray-600 line-clamp-2 flex-1">${escapeHtml(r.text)}</span>
      ${r.playtime_h > 0 ? `<span class="shrink-0 text-gray-400">${r.playtime_h}h</span>` : ''}`;
    listEl.appendChild(div);
  });
}

function clearSteamSelection() {
  steamSelectedGame = null;
  steamLoaded = false;
  steamFormatted = '';
  document.getElementById('steam-summary').classList.add('hidden');
  document.getElementById('steam-reviews-preview').classList.add('hidden');
  document.getElementById('steam-analysis-wrap').classList.add('hidden');
  document.getElementById('steam-analysis').textContent = '';
  document.getElementById('steam-include-row').classList.add('hidden');
  document.getElementById('steam-include-row').classList.remove('flex');
  document.getElementById('btn-load-reviews').classList.add('hidden');
  document.getElementById('steam-badge').classList.add('hidden');
  document.getElementById('steam-status').textContent = '';
  document.getElementById('steam-games-list').classList.remove('hidden');
}

// ── 手动填入链接，爬取后直接存入收藏池 ──────────────────
async function fetchManualUrls() {
  const raw = (document.getElementById('manual-urls').value || '').trim();
  if (!raw) { document.getElementById('url-fetch-status').textContent = '请先填入链接。'; return; }

  const urls = raw.split('\n').map(s => s.trim()).filter(s => s.startsWith('http'));
  if (!urls.length) { document.getElementById('url-fetch-status').textContent = '未识别到有效链接（需以 http 开头）。'; return; }

  const btn      = document.getElementById('btn-fetch-urls');
  const statusEl = document.getElementById('url-fetch-status');
  btn.disabled   = true;
  btn.innerHTML  = '<i data-lucide="loader" class="w-3 h-3 animate-spin"></i> 爬取中…';
  if (typeof lucide !== 'undefined') lucide.createIcons({ el: btn });
  statusEl.textContent = `正在爬取 ${urls.length} 个链接，请稍候…`;

  try {
    const resp = await fetch('/api/fetch_urls', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ urls }),
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '爬取失败');

    const sources = data.sources || [];
    if (!sources.length) {
      statusEl.textContent = '未能从这些链接提取到有效内容，请确认链接可访问。';
      return;
    }

    // 游戏名若为空则用第一个来源的 title 推断
    if (!currentGameName) {
      currentGameName = document.getElementById('game-name-input').value.trim() || '';
    }

    let added = 0;
    const existingUrls = new Set(savedArticles.map(s => s.url));
    sources.forEach(src => {
      if (existingUrls.has(src.url)) return;
      savedArticles.push({
        source_name:     src.domain || new URL(src.url).hostname,
        source_id:       'manual',
        title:           src.title || src.url,
        url:             src.url,
        content:         src.content || '',
        content_preview: (src.content || '').slice(0, 120),
        date_str:        '',
      });
      added++;
    });

    renderSavedList();
    statusEl.textContent = added > 0
      ? `成功爬取并存入 ${added} 篇，共 ${sources.length} 个链接有效内容。`
      : `链接已存在于收藏池，无新增。`;

    // 清空输入框
    if (added > 0) document.getElementById('manual-urls').value = '';
  } catch (e) {
    statusEl.textContent = '爬取失败：' + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i data-lucide="download" class="w-3 h-3"></i> 爬取并存入';
    if (typeof lucide !== 'undefined') lucide.createIcons({ el: btn });
  }
}
