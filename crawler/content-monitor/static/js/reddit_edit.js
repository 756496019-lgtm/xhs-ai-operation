let screenshots     = [];   // [{dataUrl, name}]
let translatedImages = []; // base64 data URLs of rendered cards
let currentItem     = null;

// ── 初始化：从 sessionStorage 读取条目 ────────────────────────
(function init() {
  try {
    const raw = sessionStorage.getItem('rewriteItems');
    if (!raw) return;
    const items = JSON.parse(raw) || [];
    currentItem = items[0] || null;
    if (currentItem && currentItem.title) {
      document.getElementById('xhs-title').value =
        ('【reddit热帖】' + currentItem.title).slice(0, 20);
    }
  } catch (e) {
    console.warn('无法读取 rewriteItems:', e);
  }
})();

// ── 截图粘贴（Ctrl+V）────────────────────────────────────────
document.addEventListener('paste', (e) => {
  const items = e.clipboardData?.items || [];
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const blob = item.getAsFile();
      if (!blob) continue;
      const reader = new FileReader();
      reader.onload = (ev) => addScreenshot(ev.target.result, 'screenshot.png');
      reader.readAsDataURL(blob);
      e.preventDefault();
      break;
    }
  }
});

// ── 点击上传 ──────────────────────────────────────────────────
document.getElementById('drop-zone').addEventListener('click', () => {
  document.getElementById('file-input').click();
});

document.getElementById('file-input').addEventListener('change', function () {
  Array.from(this.files || []).forEach((file) => {
    const reader = new FileReader();
    reader.onload = (e) => addScreenshot(e.target.result, file.name);
    reader.readAsDataURL(file);
  });
  this.value = '';
});

// ── 截图管理 ─────────────────────────────────────────────────
function addScreenshot(dataUrl, name) {
  if (screenshots.length >= 5) { alert('最多支持 5 张截图'); return; }
  screenshots.push({ dataUrl, name: name || 'screenshot' });
  renderImageList();
}

function removeScreenshot(i) {
  screenshots.splice(i, 1);
  translatedImages = [];
  document.getElementById('preview-area').classList.add('hidden');
  document.getElementById('empty-preview').classList.remove('hidden');
  document.getElementById('publish-section').classList.add('hidden');
  renderImageList();
}

function renderImageList() {
  const list = document.getElementById('image-list');
  const btn  = document.getElementById('btn-translate');
  list.innerHTML = '';

  if (!screenshots.length) {
    list.classList.add('hidden');
    btn.disabled = true;
    return;
  }

  list.classList.remove('hidden');
  btn.disabled = false;

  screenshots.forEach((ss, i) => {
    const row = document.createElement('div');
    row.className = 'flex items-center gap-2 p-2 rounded-lg border border-gray-100 bg-gray-50';
    row.innerHTML = `
      <img src="${ss.dataUrl}" class="w-14 h-9 object-cover rounded border border-gray-200 shrink-0">
      <span class="flex-1 text-[11px] text-gray-600 font-medium">截图 ${i + 1}</span>
      <button onclick="removeScreenshot(${i})"
              class="p-1 text-gray-300 hover:text-red-400 transition-colors shrink-0">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>`;
    list.appendChild(row);
  });
}

// ── AI 识别翻译 ───────────────────────────────────────────────
document.getElementById('btn-translate').addEventListener('click', async () => {
  if (!screenshots.length) { alert('请先上传或粘贴截图'); return; }

  const btn    = document.getElementById('btn-translate');
  const status = document.getElementById('translate-status');
  btn.disabled    = true;
  translatedImages = [];
  document.getElementById('publish-section').classList.add('hidden');

  try {
    status.textContent = `正在 AI 分析 ${screenshots.length} 张截图（约 10-20 秒）…`;

    const resp = await fetch('/api/analyze_screenshot', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ images: screenshots.map(s => s.dataUrl) }),
    });
    if (!resp.ok) throw new Error(`服务器错误 ${resp.status}`);
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '分析失败');

    const results = data.results || [];

    // 逐张渲染翻译叠加图（html-to-image，绝对定位覆盖）
    const container = document.createElement('div');
    container.style.cssText = 'position:fixed;left:-9999px;top:0;z-index:-1;pointer-events:none;';
    document.body.appendChild(container);

    for (let i = 0; i < screenshots.length; i++) {
      status.textContent = `正在渲染图 ${i + 1}/${screenshots.length}…`;
      const result   = results[i] || {};
      const comments = result.status === 'ok' ? (result.comments || []) : [];
      const card     = buildOverlayCard(screenshots[i].dataUrl, comments);
      container.appendChild(card);
      await new Promise(r => setTimeout(r, 80)); // 等待字体渲染
      const dataUrl  = await window.htmlToImage.toJpeg(card, {
        quality: 0.92, pixelRatio: 2, backgroundColor: '#1a1a1b', cacheBust: true,
      });
      translatedImages.push(dataUrl);
      container.removeChild(card);
    }
    document.body.removeChild(container);

    // 展示预览
    renderPreview();

    // 自动生成文案
    const allTranslations = results.flatMap(r => r.status === 'ok' ? (r.comments || []) : []);
    const item = currentItem || {};
    let content = item.title ? `Reddit 热帖：「${item.title_zh || item.title}」\n\n` : '';
    if (allTranslations.length) {
      content += '精选评论：\n' + allTranslations.slice(0, 6).map(c => `• ${c.chinese}`).join('\n');
      content += '\n\n—— 游戏雷达局，今日资讯已送达';
      content += '\n\n#游戏# #Reddit热帖# #外网热议# #游戏资讯# #游戏雷达局#';
    }
    document.getElementById('xhs-content').value = content;
    document.getElementById('publish-section').classList.remove('hidden');

    status.textContent = `完成，已生成 ${translatedImages.length} 张图片。`;

  } catch (e) {
    status.textContent = '失败：' + e.message;
  } finally {
    btn.disabled = false;
  }
});

// ── 预览渲染 ──────────────────────────────────────────────────
function renderPreview() {
  const grid  = document.getElementById('preview-grid');
  const area  = document.getElementById('preview-area');
  const empty = document.getElementById('empty-preview');
  const count = document.getElementById('preview-count');
  const dlBtn = document.getElementById('btn-download-all');

  grid.innerHTML = '';
  area.classList.remove('hidden');
  empty.classList.add('hidden');
  count.textContent = `共 ${translatedImages.length} 张`;
  dlBtn.classList.remove('hidden');
  dlBtn.classList.add('flex');

  translatedImages.forEach((imgData, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'relative group';
    wrap.innerHTML = `
      <img src="${imgData}" class="w-full rounded-xl border border-gray-100 object-top"
           style="max-height:280px;object-fit:cover;object-position:top;">
      <div class="absolute bottom-2 left-2 bg-black/60 text-white text-[10px] px-2 py-0.5 rounded-full">
        图 ${i + 1}
      </div>
      <button onclick="downloadSingle(${i})"
              class="absolute top-2 right-2 bg-black/60 hover:bg-black/80 text-white text-[10px] px-2 py-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        下载
      </button>`;
    grid.appendChild(wrap);
  });
}

// ── 下载单张 ──────────────────────────────────────────────────
function downloadSingle(i) {
  if (!translatedImages[i]) return;
  saveAs(translatedImages[i], `reddit_${i + 1}.jpg`);
}

// ── 导出全部 ──────────────────────────────────────────────────
async function downloadAllReddit() {
  if (!translatedImages.length) { alert('请先生成图片'); return; }
  const btn = document.getElementById('btn-download-all');
  btn.disabled = true;
  for (let i = 0; i < translatedImages.length; i++) {
    btn.textContent = `${i + 1}/${translatedImages.length}`;
    saveAs(translatedImages[i], `reddit_${i + 1}.jpg`);
    if (i < translatedImages.length - 1) await new Promise(r => setTimeout(r, 300));
  }
  btn.disabled = false;
  btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>\u5bfc\u51fa\u5168\u90e8`;
}

// ── 翻译叠加卡片（html-to-image 方案）────────────────────────
// 截图作背景，中文翻译绝对定位叠加在 AI 估算的对应区域上
function buildOverlayCard(screenshotDataUrl, blocks) {
  const CARD_W = 750;
  const FONT   = "'PingFang SC','Microsoft YaHei','Noto Sans SC',Arial,sans-serif";

  const card = document.createElement('div');
  card.style.cssText = `width:${CARD_W}px;background:#1a1a1b;position:relative;overflow:hidden;font-family:${FONT};box-sizing:border-box;`;

  // 截图底图
  const imgEl = document.createElement('img');
  imgEl.src = screenshotDataUrl;
  imgEl.crossOrigin = 'anonymous';
  imgEl.style.cssText = 'width:100%;display:block;';
  card.appendChild(imgEl);

  if (blocks && blocks.length > 0) {
    const N = blocks.length;

    // 判断每个 block 是否有有效位置（y_start/y_end 均不为 null，且 y_end - y_start > 2）
    blocks.forEach((b, i) => {
      if (!b.chinese) return;

      const hasValidPos = b.y_start != null && b.y_end != null && (b.y_end - b.y_start) > 2;
      const yStart = hasValidPos ? b.y_start : (i / N) * 100;
      const yEnd   = hasValidPos ? b.y_end   : ((i + 1) / N) * 100;

      // 帖子标题/正文用蓝色主题，评论用橙色主题
      const isPost   = b.type === 'post_title' || b.type === 'post_body';
      const accent   = isPost ? '#0079D3' : '#FF4500';
      const zhColor  = isPost ? '#7FBFFF' : '#FF8C69';
      const bgColor  = isPost ? 'rgba(0,40,80,0.92)' : 'rgba(13,13,14,0.90)';

      const overlay = document.createElement('div');
      overlay.style.cssText = `
        position:absolute;left:0;right:0;
        top:${yStart}%;
        min-height:${Math.max(yEnd - yStart, 5)}%;
        background:${bgColor};
        border-left:3px solid ${accent};
        padding:8px 12px 8px 14px;
        box-sizing:border-box;
      `;

      // 类型标签
      if (isPost) {
        const tag = document.createElement('div');
        tag.style.cssText = `font-size:9px;color:${accent};font-weight:700;letter-spacing:0.08em;margin-bottom:4px;text-transform:uppercase;`;
        tag.textContent = b.type === 'post_title' ? '▍帖子标题' : '▍帖子正文';
        overlay.appendChild(tag);
      }

      // 英文原文（弱化）
      if (b.english) {
        const en = document.createElement('div');
        en.style.cssText = 'font-size:11px;color:#6b6c6d;line-height:1.5;margin-bottom:3px;word-break:break-word;';
        en.textContent = b.english;
        overlay.appendChild(en);
      }

      // 中文翻译（主角）
      const zh = document.createElement('div');
      const zhSize = isPost && b.type === 'post_title' ? '16px' : '14px';
      zh.style.cssText = `font-size:${zhSize};color:${zhColor};line-height:1.7;font-weight:${isPost ? '600' : '500'};word-break:break-word;`;
      zh.textContent = b.chinese;
      overlay.appendChild(zh);

      card.appendChild(overlay);
    });
  }

  // 页脚品牌条
  const footer = document.createElement('div');
  footer.style.cssText = 'background:#111112;padding:9px;text-align:center;font-size:10px;color:#3a3a3b;letter-spacing:0.05em;';
  footer.textContent = '游戏雷达局 · 今日资讯已送达';
  card.appendChild(footer);

  return card;
}

function escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── 一键发布 ──────────────────────────────────────────────────
document.getElementById('btn-publish').addEventListener('click', async () => {
  const title   = document.getElementById('xhs-title').value.trim();
  const content = document.getElementById('xhs-content').value.trim();
  const cookie  = document.getElementById('xhs-cookie').value.trim();
  const status  = document.getElementById('publish-status');

  if (!translatedImages.length) { alert('请先点击「AI 识别并翻译」生成图片'); return; }
  if (!cookie)                   { alert('请输入小红书 Cookie'); return; }
  if (!title || !content)        { alert('请填写标题和文案'); return; }

  const isDraft = document.querySelector('input[name="reddit-publish-mode"]:checked')?.value === 'draft';

  const btn = document.getElementById('btn-publish');
  btn.disabled = true;
  status.textContent = isDraft ? '正在发至草稿箱…' : '正在发布…';

  try {
    const resp = await fetch('/api/publish_reddit_direct', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ image_b64s: translatedImages, title, content, cookie, is_draft: isDraft }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '发布失败');
    if (isDraft) {
      status.innerHTML = '<span class="text-green-600 font-semibold">已发至草稿箱！</span>';
    } else {
      status.innerHTML = '<span class="text-green-600 font-semibold">发布成功！</span>';
      if (data.url) {
        status.innerHTML += ` <a href="${data.url}" target="_blank" class="text-blue-500 underline text-xs">查看笔记</a>`;
      }
    }
  } catch (e) {
    status.textContent = '发布失败：' + e.message;
  } finally {
    btn.disabled = false;
  }
});

// ── 先去编辑器 ────────────────────────────────────────────────
document.getElementById('btn-open-editor').addEventListener('click', async () => {
  const title   = document.getElementById('xhs-title').value.trim();
  const content = document.getElementById('xhs-content').value.trim();
  const status  = document.getElementById('publish-status');

  if (!translatedImages.length) { alert('请先生成图片'); return; }
  status.textContent = '跳转中…';

  try {
    const resp = await fetch('/api/cards_to_xhs', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ image_b64s: translatedImages, title, content, tag: '游戏雷达局', desc: '#游戏# #Reddit热帖# #外网热议# #游戏资讯# #游戏雷达局#' }),
    });
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.message || '跳转失败');
    window.open('/xhs_full?token=' + data.token, '_blank');
    status.textContent = '已在新标签页打开生成器。';
  } catch (e) {
    status.textContent = '跳转失败：' + e.message;
  }
});
