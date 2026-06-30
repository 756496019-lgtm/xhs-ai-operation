let lastRows = [];
let selectionOrderCounter = 0;

// 默认填充今天日期
(function() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  document.getElementById('gamersky-date').value = y + '-' + m + '-' + day;
})();

function switchSource() {
  const val = document.querySelector('input[name="source"]:checked').value;
  document.getElementById('cfg-reddit').classList.toggle('hidden', val !== 'reddit');
  document.getElementById('cfg-news').classList.toggle('hidden', val !== 'news');
  document.getElementById('cfg-deals').classList.toggle('hidden', val !== 'deals');
  document.getElementById('cfg-weibo').classList.toggle('hidden', val !== 'weibo');
  document.getElementById('cfg-bilibili').classList.toggle('hidden', val !== 'bilibili');
  document.getElementById('cfg-taptap').classList.toggle('hidden', val !== 'taptap');
  document.getElementById('cfg-domestic-games').classList.toggle('hidden', val !== 'domestic_games');
  document.getElementById('cfg-twitter').classList.toggle('hidden', val !== 'twitter');
  const names = { reddit: 'Reddit', news: '新闻', deals: '游戏折扣', weibo: '微博超话', bilibili: 'B站动态', taptap: 'TapTap', domestic_games: '国内资讯', twitter: 'Twitter/X' };
  document.getElementById('stat-source').textContent = names[val] || val;
  const mergeBtn = document.getElementById('btn-merge-xhs');
  if (mergeBtn) mergeBtn.classList.toggle('hidden', val !== 'deals');
}
document.querySelectorAll('.source-radio').forEach(r => {
  r.addEventListener('change', switchSource);
});
switchSource();

// ── 热度徽章渲染 ──────────────────────────────────────────────
function trendingBadge(score) {
  if (score == null) return '<span class="text-gray-300 text-[10px]">—</span>';
  if (score >= 70) return `<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-orange-50 text-orange-600 text-[10px] font-bold">🔥 ${score}</span>`;
  if (score >= 40) return `<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-yellow-50 text-yellow-600 text-[10px] font-semibold">⭐ ${score}</span>`;
  return `<span class="text-gray-400 text-[10px]">${score}</span>`;
}

// ── 单行渲染 ─────────────────────────────────────────────────
function renderRow(row, idx, tbody) {
  const tr = document.createElement('tr');
  const isHot = (row.trending_score || 0) >= 70;
  tr.className = 'hover:bg-[#F8F9FC] transition-colors' + (isHot ? ' bg-orange-50/40' : '');
  tr.dataset.rowIndex = idx;

  const contentText = (row.content || '').replace(/<[^>]+>/g, '');
  const shortContent = contentText.length > 60 ? contentText.slice(0, 60) + '…' : contentText;
  const mainTitle = row.title_zh || row.title || '';
  const subTitle = row.title_zh && row.title && row.title_zh !== row.title ? row.title : '';
  const isGamersky = (row.source || '') === 'gamersky';
  const isDeals    = (row.source || '') === 'deals';
  const isReddit   = (row.source || '') === 'reddit';
  const platform   = (row.label || '').toLowerCase();

  const SOURCE_BADGE = {
    gamersky:      'bg-blue-50 text-blue-600',
    news:          'bg-blue-50 text-blue-600',
    deals:         { epic: 'bg-blue-50 text-blue-600', steam: 'bg-sky-50 text-sky-700', nintendo: 'bg-red-50 text-red-600' },
    reddit:        'bg-orange-50 text-orange-600',
    weibo:         'bg-pink-50 text-pink-600',
    bilibili:      'bg-cyan-50 text-cyan-700',
    taptap:        'bg-teal-50 text-teal-600',
    domestic_games:'bg-amber-50 text-amber-700',
    twitter:       'bg-sky-50 text-sky-600',
  };
  const SOURCE_LABEL = {
    gamersky: '游民', news: '新闻', reddit: 'Reddit', weibo: '微博',
    bilibili: 'B站', taptap: 'TapTap', domestic_games: '国内', twitter: 'Twitter',
  };

  let badgeCls, badgeText;
  if (isDeals) {
    const cfg = SOURCE_BADGE.deals[platform] || 'bg-gray-50 text-gray-600';
    badgeCls = cfg;
    badgeText = { epic: 'Epic', steam: 'Steam', nintendo: '任天堂' }[platform] || platform;
  } else {
    badgeCls = SOURCE_BADGE[row.source] || 'bg-gray-50 text-gray-600';
    badgeText = SOURCE_LABEL[row.source] || (row.source || '');
  }
  const sourceBadge = `<span class="px-2 py-0.5 rounded-md ${badgeCls} text-[10px] font-semibold">${escapeHtml(badgeText)}</span>`;

  const priceHtml = isDeals && row.price_current
    ? `<div class="flex items-center gap-1.5 mt-0.5">
        <span class="text-green-600 font-bold text-xs">${escapeHtml(row.price_current)}</span>
        ${row.price_original ? `<span class="text-gray-400 line-through text-[10px]">${escapeHtml(row.price_original)}</span>` : ''}
        ${row.discount ? `<span class="text-orange-500 font-bold text-[10px]">${escapeHtml(row.discount)}</span>` : ''}
       </div>`
    : '';

  // 图文按钮逻辑：按来源区分
  let graphicBtnHtml = '';
  if (isDeals) {
    graphicBtnHtml = `<button class="btn-to-graphic gen-xhs-btn text-[11px] text-white bg-[#FF6B2B] hover:bg-[#e05a1f] font-semibold px-2 py-1 rounded-lg transition-colors whitespace-nowrap" data-index="${idx}">图文</button>`;
  } else if (isReddit) {
    graphicBtnHtml = `<button class="btn-to-graphic reddit-auto-btn text-[11px] text-white bg-[#FF4500] hover:bg-[#c73800] font-semibold px-2 py-1 rounded-lg transition-colors whitespace-nowrap" data-index="${idx}">图文</button>`;
  } else if (isGamersky) {
    graphicBtnHtml = '';
  } else {
    graphicBtnHtml = `<button class="btn-to-graphic text-[11px] text-white bg-[#6C5CE7] hover:bg-[#5a4bd1] font-semibold px-2 py-1 rounded-lg transition-colors whitespace-nowrap" data-index="${idx}">图文</button>`;
  }

  tr.innerHTML = `
    <td class="px-4 py-3">
      <button type="button"
               class="row-select w-6 h-6 rounded-lg border border-gray-300 text-[11px] text-gray-400 flex items-center justify-center hover:border-[#6C5CE7] hover:text-[#6C5CE7] transition-colors"
               data-index="${idx}" data-selected="0"></button>
    </td>
    <td class="px-4 py-3">${sourceBadge}</td>
    <td class="px-4 py-3">
      <a href="${encodeURI(row.url || '#')}" target="_blank" class="text-txt-primary hover:text-accent-purple font-medium transition-colors">
        ${escapeHtml(mainTitle)}
      </a>
      ${subTitle ? `<div class="text-[11px] text-txt-muted truncate mt-0.5 max-w-xs">${escapeHtml(subTitle)}</div>` : ''}
    </td>
    <td class="px-4 py-3 text-txt-secondary text-xs">
      ${shortContent ? escapeHtml(shortContent) : '<span class="text-txt-muted">暂无内容</span>'}
      ${priceHtml}
    </td>
    <td class="px-4 py-3 text-txt-muted text-xs whitespace-nowrap">${escapeHtml(row.time || '')}</td>
    <td class="px-4 py-3 text-xs">
      <span class="px-2 py-0.5 rounded-md bg-purple-50 text-accent-purple text-[10px] font-semibold">${escapeHtml(row.label || '')}${row.subreddit ? ' / r/' + escapeHtml(row.subreddit) : ''}</span>
    </td>
    <td class="px-4 py-3 text-center trending-cell" data-row="${idx}">${trendingBadge(row.trending_score != null ? row.trending_score : null)}</td>
    <td class="px-4 py-3 flex flex-col gap-1">
      ${graphicBtnHtml}
      ${isGamersky ? '' : `<button class="btn-to-video text-[11px] text-[#6C5CE7] hover:text-white hover:bg-[#6C5CE7] font-semibold px-2 py-1 rounded-lg border border-[#6C5CE7] transition-colors whitespace-nowrap" data-index="${idx}">视频</button>`}
    </td>
  `;
  tbody.appendChild(tr);

  // 选择按钮
  const selectBtn = tr.querySelector('.row-select');
  if (selectBtn) {
    selectBtn._rowData = row;
    selectBtn._selectOrder = 0;
    selectBtn.addEventListener('click', () => {
      const selected = selectBtn.getAttribute('data-selected') === '1';
      if (!selected) {
        selectBtn._selectOrder = ++selectionOrderCounter;
        selectBtn.setAttribute('data-selected', '1');
        selectBtn.textContent = String(selectBtn._selectOrder);
        selectBtn.classList.remove('border-gray-300', 'text-gray-400');
        selectBtn.classList.add('bg-[#6C5CE7]', 'text-white', 'border-[#6C5CE7]');
      } else {
        selectBtn._selectOrder = 0;
        selectBtn.setAttribute('data-selected', '0');
        selectBtn.textContent = '';
        selectBtn.classList.remove('bg-[#6C5CE7]', 'text-white', 'border-[#6C5CE7]');
        selectBtn.classList.add('border-gray-300', 'text-gray-400');
      }
    });
  }

  // 视频按钮
  const videoBtn = tr.querySelector('.btn-to-video');
  if (videoBtn) {
    videoBtn.addEventListener('click', () => {
      const r = lastRows[idx] || {};
      // 把 title 一起带过去，确保游戏名和完整内容都传到视频页
      const videoPayload = { items: [r] };
      try { sessionStorage.setItem('videoItems', JSON.stringify(videoPayload)); } catch(e) {}
      window.location.href = '/video';
    });
  }

  // 非deals/reddit/gamersky 的图文按钮 → 改写页
  const graphicBtn = tr.querySelector('.btn-to-graphic:not(.gen-xhs-btn):not(.reddit-auto-btn):not(.open-post-btn)');
  if (graphicBtn) {
    graphicBtn.addEventListener('click', () => {
      const r = lastRows[idx] || {};
      try { sessionStorage.setItem('rewriteItems', JSON.stringify([r])); } catch(e) {}
      window.location.href = '/rewrite';
    });
  }
}

document.getElementById('btn-run').addEventListener('click', async () => {
  const source = document.querySelector('input[name="source"]:checked').value;
  const tbody = document.getElementById('tbody');
  const emptyState = document.getElementById('empty-state');
  const statStatus = document.getElementById('stat-status');
  const statStatusSub = document.getElementById('stat-status-sub');

  statStatus.textContent = '抓取中...';
  statStatusSub.textContent = '请稍候';
  tbody.innerHTML = '';
  selectionOrderCounter = 0;
  if (emptyState) emptyState.classList.add('hidden');

  let payload = { source };
  if (source === 'reddit') {
    const labels = Array.from(document.querySelectorAll('.reddit-label:checked')).map(x => x.value);
    const perLabel = parseInt(document.getElementById('reddit-per-label').value || '20', 10);
    payload.labels = labels;
    payload.per_label = perLabel;
  } else if (source === 'news') {
    const newsSources = Array.from(document.querySelectorAll('.news-source:checked')).map(x => x.value);
    const dateVal = document.getElementById('gamersky-date').value;
    const pages = parseInt(document.getElementById('gamersky-pages').value || '5', 10);
    const sounovaLimit = parseInt(document.getElementById('sounova-limit').value || '20', 10);
    payload.news_sources = newsSources;
    payload.date = dateVal;
    payload.max_pages = pages;
    payload.sounova_limit = sounovaLimit;
  } else if (source === 'deals') {
    const platforms = Array.from(document.querySelectorAll('.deals-platform:checked')).map(x => x.value);
    const limit = parseInt(document.getElementById('deals-limit').value || '20', 10);
    payload.platforms = platforms;
    payload.limit = limit;
  } else if (source === 'weibo') {
    const topics = Array.from(document.querySelectorAll('.weibo-topic:checked')).map(x => x.value);
    const perTopic = parseInt(document.getElementById('weibo-per-topic').value || '20', 10);
    payload.topics = topics;
    payload.per_topic = perTopic;
  } else if (source === 'bilibili') {
    const uidKeys = Array.from(document.querySelectorAll('.bilibili-uid:checked')).map(x => x.value);
    const perUid = parseInt(document.getElementById('bilibili-per-uid').value || '20', 10);
    payload.uid_keys = uidKeys;
    payload.per_uid = perUid;
  } else if (source === 'taptap') {
    const gameKeys = Array.from(document.querySelectorAll('.taptap-game:checked')).map(x => x.value);
    const perGame = parseInt(document.getElementById('taptap-per-game').value || '20', 10);
    payload.game_keys = gameKeys;
    payload.per_game = perGame;
  } else if (source === 'domestic_games') {
    const sources = Array.from(document.querySelectorAll('.domestic-source:checked')).map(x => x.value);
    const perSource = parseInt(document.getElementById('domestic-per-source').value || '20', 10);
    payload.sources = sources;
    payload.per_source = perSource;
  } else if (source === 'twitter') {
    const topics = Array.from(document.querySelectorAll('.twitter-topic:checked')).map(x => x.value);
    const perTopic = parseInt(document.getElementById('twitter-per-topic').value || '20', 10);
    payload.topics = topics;
    payload.per_topic = perTopic;
  }

  // 附带已保存的 Cookie
  payload.cookies = window.getStoredCookies ? window.getStoredCookies() : {};

  try {
    const resp = await fetch('/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (data.status !== 'ok') {
      statStatus.textContent = '出错';
      statStatusSub.textContent = data.message || '未知错误';
      if (emptyState) emptyState.classList.remove('hidden');
      return;
    }
    const rows = data.items || [];
    lastRows = rows;

    document.getElementById('stat-count').textContent = rows.length + ' 条';
    document.getElementById('stat-time').textContent = rows.length ? rows[0].time : '--';
    statStatus.textContent = '完成';
    statStatusSub.textContent = '抓取成功';

    if (!rows.length) {
      if (emptyState) emptyState.classList.remove('hidden');
      return;
    }

    rows.forEach((row, idx) => renderRow(row, idx, tbody));

    attachScreenshotHandlers();
    attachGenXhsHandlers();
    attachRedditAutoHandlers();

    // 自动触发规则打分（不消耗 API）
    scoreTrending(rows);

  } catch (e) {
    statStatus.textContent = '失败';
    statStatusSub.textContent = String(e);
  }
});

// ── 规则热度打分 ──────────────────────────────────────────────
async function scoreTrending(rows) {
  try {
    const resp = await fetch('/api/trending_score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: rows }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') return;
    const scored = data.items || [];
    scored.forEach((item, idx) => {
      lastRows[idx] = item;
      const cell = document.querySelector(`.trending-cell[data-row="${idx}"]`);
      if (cell) {
        cell.innerHTML = trendingBadge(item.trending_score);
        cell.title = item.trending_reason || '';
      }
      const tr = document.querySelector(`tr[data-row-index="${idx}"]`);
      if (tr && (item.trending_score || 0) >= 70) {
        tr.classList.add('bg-orange-50/40');
      }
    });
    // 显示 AI精排按钮（只在有高分内容时显示）
    const highScore = scored.filter(it => (it.trending_score || 0) >= 40);
    const aiRankBtn = document.getElementById('btn-ai-rank');
    if (aiRankBtn) aiRankBtn.classList.toggle('hidden', highScore.length === 0);
  } catch(e) {
    console.warn('trending_score 失败:', e);
  }
}

// ── AI 精排 Top5 ──────────────────────────────────────────────
document.getElementById('btn-ai-rank')?.addEventListener('click', async () => {
  const btn = document.getElementById('btn-ai-rank');
  const panel = document.getElementById('ai-rank-panel');
  if (!panel) return;
  btn.textContent = 'AI 分析中...';
  btn.disabled = true;
  panel.classList.remove('hidden');
  panel.innerHTML = '<div class="text-xs text-gray-400 py-4 text-center">AI 精排中，请稍候...</div>';

  try {
    const resp = await fetch('/api/trending_rank', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: lastRows }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '精排失败');
    const top5 = data.items || [];
    panel.innerHTML = top5.map((it, i) => `
      <div class="flex items-start gap-3 p-3 rounded-xl bg-gradient-to-r from-orange-50 to-yellow-50 border border-orange-100">
        <div class="w-6 h-6 rounded-full bg-orange-400 text-white text-[11px] font-bold flex items-center justify-center shrink-0">${i+1}</div>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-semibold text-gray-800 truncate">${escapeHtml(it.title || '')}</div>
          <div class="text-[11px] text-orange-600 mt-0.5">${escapeHtml(it.ai_reason || it.trending_reason || '')}</div>
        </div>
        <div class="flex flex-col gap-1 shrink-0">
          <button class="rank-graphic-btn text-[10px] text-white bg-[#FF6B2B] hover:bg-[#e05a1f] font-semibold px-2 py-0.5 rounded-md transition-colors" data-item='${JSON.stringify(it)}'>图文</button>
          <button class="rank-video-btn text-[10px] text-[#6C5CE7] border border-[#6C5CE7] hover:bg-[#6C5CE7] hover:text-white font-semibold px-2 py-0.5 rounded-md transition-colors" data-item='${JSON.stringify(it)}'>视频</button>
        </div>
      </div>
    `).join('');

    // 绑定卡片按钮
    panel.querySelectorAll('.rank-graphic-btn').forEach(b => {
      b.addEventListener('click', () => {
        try { const it = JSON.parse(b.dataset.item); sessionStorage.setItem('rewriteItems', JSON.stringify([it])); } catch(e) {}
        window.location.href = '/rewrite';
      });
    });
    panel.querySelectorAll('.rank-video-btn').forEach(b => {
      b.addEventListener('click', () => {
        try { const it = JSON.parse(b.dataset.item); sessionStorage.setItem('videoItems', JSON.stringify({ items: [it] })); } catch(e) {}
        window.location.href = '/video';
      });
    });
  } catch(e) {
    panel.innerHTML = `<div class="text-xs text-red-400 py-2 text-center">精排失败：${escapeHtml(String(e))}</div>`;
  } finally {
    btn.textContent = 'AI 精排 Top5';
    btn.disabled = false;
  }
});

// ==================== 折扣一键生成图文 ====================
function attachGenXhsHandlers() {
  document.querySelectorAll('.gen-xhs-btn').forEach(btn => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', async () => {
      const idx = parseInt(btn.dataset.index || '-1', 10);
      const row = lastRows[idx] || {};
      const origText = btn.textContent;
      btn.textContent = '处理中...';
      btn.disabled = true;
      try {
        const resp = await fetch('/api/deals_to_xhs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title:          row.title          || '',
            content:        row.content        || '',
            cover_image:    row.cover_image    || '',
            price_current:  row.price_current  || '',
            price_original: row.price_original || '',
            discount:       row.discount       || '',
            url:            row.url            || '',
            label:          row.label          || '',
            tag:            '游戏雷达局',
          })
        });
        const data = await resp.json();
        if (data.status !== 'ok') throw new Error(data.message || '接口错误');
        window.open('/xhs_full?token=' + encodeURIComponent(data.token), '_blank');
      } catch (e) {
        alert('生成失败：' + e.message);
      } finally {
        btn.textContent = origText;
        btn.disabled = false;
      }
    });
  });
}

// ==================== Reddit 一键生成评论图文 ====================
function attachRedditAutoHandlers() {
  document.querySelectorAll('.reddit-auto-btn').forEach(btn => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.index || '-1', 10);
      const row = lastRows[idx] || {};
      if (!row.url) return;
      try { sessionStorage.setItem('rewriteItems', JSON.stringify([row])); } catch(e) {}
      window.location.href = '/reddit_edit';
    });
  });
}

// 当前等待粘贴的帖子信息
let pendingPasteRow = null;

function attachScreenshotHandlers() {
  const buttons = document.querySelectorAll('.open-post-btn');
  buttons.forEach(btn => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const idx = parseInt(btn.dataset.index || '-1', 10);
      const row = lastRows[idx] || {};
      let url = row.url;
      if (!url) return;
      url = url.replace(/old\.reddit\.com/g, 'www.reddit.com');
      pendingPasteRow = { url, title: row.title || '', title_zh: row.title_zh || '' };
      window.open(url, '_blank');
      document.getElementById('stat-status').textContent = '已打开';
      document.getElementById('stat-status-sub').textContent = '请登录后截图，回本页粘贴';
      const panel = document.getElementById('screenshot-panel');
      panel.classList.remove('hidden');
      document.getElementById('paste-zone').classList.remove('hidden');
      document.getElementById('paste-preview').classList.add('hidden');
      if (typeof lucide !== 'undefined') lucide.createIcons();
    });
  });
}

// 粘贴截图：处理剪贴板中的图片，成功后自动跳转编辑器
async function handlePasteImage(imageDataUrl) {
  if (!imageDataUrl || !imageDataUrl.startsWith('data:')) return false;
  const row = pendingPasteRow || { url: '', title: '', title_zh: '' };
  const base64Part = imageDataUrl.indexOf(',') >= 0 ? imageDataUrl.split(',')[1] : imageDataUrl;
  try {
    document.getElementById('stat-status').textContent = '处理中...';
    document.getElementById('stat-status-sub').textContent = '';
    const resp = await fetch('/api/paste_screenshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_base64: base64Part,
        url: row.url,
        title: row.title,
        title_zh: row.title_zh
      })
    });
    const data = await resp.json();
    if (data.status !== 'ok') {
      document.getElementById('stat-status').textContent = '粘贴失败';
      document.getElementById('stat-status-sub').textContent = data.message || '';
      return true;
    }
    window.location.href = '/xhs?token=' + encodeURIComponent(data.token || '');
  } catch (err) {
    document.getElementById('stat-status').textContent = '粘贴失败';
    document.getElementById('stat-status-sub').textContent = String(err);
  }
  return true;
}

// 监听粘贴事件
document.addEventListener('paste', (e) => {
  const panel = document.getElementById('screenshot-panel');
  if (!panel || panel.classList.contains('hidden')) return;
  const items = e.clipboardData?.items || [];
  for (const item of items) {
    if (item.type.indexOf('image') !== -1) {
      e.preventDefault();
      const blob = item.getAsFile();
      const reader = new FileReader();
      reader.onload = (ev) => handlePasteImage(ev.target.result);
      reader.readAsDataURL(blob);
      return;
    }
  }
});

document.getElementById('btn-paste-screenshot')?.addEventListener('click', async () => {
  try {
    const items = await navigator.clipboard.read();
    for (const item of items) {
      for (const type of item.types) {
        if (type.indexOf('image') !== -1) {
          const blob = await item.getType(type);
          const reader = new FileReader();
          reader.onload = (ev) => handlePasteImage(ev.target.result);
          reader.readAsDataURL(blob);
          return;
        }
      }
    }
    alert('剪贴板中没有图片，请先截图。');
  } catch (err) {
    if (err.name === 'NotAllowedError') {
      alert('请允许访问剪贴板权限，或直接在本页面按 Ctrl+V 粘贴。');
    } else {
      alert('读取剪贴板失败：' + err.message);
    }
  }
});

document.getElementById('close-screenshot')?.addEventListener('click', () => {
  document.getElementById('screenshot-panel').classList.add('hidden');
  pendingPasteRow = null;
});

// ==================== 折扣合并生成图文 ====================
document.getElementById('btn-merge-xhs')?.addEventListener('click', async () => {
  const checked = Array.from(document.querySelectorAll('.row-select[data-selected="1"]'))
    .sort((a, b) => (a._selectOrder || 0) - (b._selectOrder || 0));
  if (!checked.length) { alert('请先勾选至少一条折扣信息。'); return; }
  const items = checked.map(c => c._rowData).filter(Boolean);
  if (!items.length) return;

  const btn = document.getElementById('btn-merge-xhs');
  const origHTML = btn.innerHTML;
  btn.innerHTML = `<svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 处理中...`;
  btn.disabled = true;
  try {
    const resp = await fetch('/api/deals_to_xhs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items, tag: '游戏雷达局' })
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '接口错误');
    window.open('/xhs_full?token=' + encodeURIComponent(data.token), '_blank');
  } catch (e) {
    alert('生成失败：' + e.message);
  } finally {
    btn.innerHTML = origHTML;
    btn.disabled = false;
  }
});

// AI 改写 — 文字改写 / 视频脚本 双路径
function getSelectedItems() {
  const checked = Array.from(document.querySelectorAll('.row-select[data-selected="1"]'))
    .sort((a, b) => (a._selectOrder || 0) - (b._selectOrder || 0));
  return checked.map(c => c._rowData).filter(Boolean);
}

document.getElementById('btn-rewrite-text')?.addEventListener('click', () => {
  const items = getSelectedItems();
  if (!items.length) { alert('请先在列表中勾选至少一条需要改写的内容。'); return; }
  try { sessionStorage.setItem('rewriteItems', JSON.stringify(items)); } catch(e) {}
  sessionStorage.setItem('rewriteMode', 'text');
  window.location.href = '/rewrite';
});

document.getElementById('btn-rewrite-video')?.addEventListener('click', () => {
  const items = getSelectedItems();
  if (!items.length) { alert('请先在列表中勾选至少一条需要改写的内容。'); return; }
  try { sessionStorage.setItem('rewriteItems', JSON.stringify(items)); } catch(e) {}
  sessionStorage.setItem('rewriteMode', 'video');
  window.location.href = '/rewrite';
});


