// 隐藏彩蛋
console.log("%c 游戏雷达局 · GAME RADAR HQ", "background: #0A0F1E; color: #60A5FA; padding: 6px 12px; border-radius: 4px; font-weight: bold; letter-spacing: 2px;");

const STYLES = [
    { id: 'intel', name: '📡 情报局', class: 'theme-intel', bg: '#0D1B2A', text: '#E8EDF2' },
    { id: 'shoujo', name: '🌸 少女星', class: 'theme-shoujo', bg: '#FFF0F5', text: '#5C2A4E' },
    { id: 'acid', name: '⚡ 冲击波', class: 'theme-acid', bg: '#CCFF00', text: '#000' },
    { id: 'tech', name: '🔵 科技风', class: 'theme-tech', bg: '#0A0F1E', text: '#FFF' },
    { id: 'pro', name: '📰 公众号风', class: 'theme-pro', bg: '#0F1824', text: '#C8D8E8' },
];

let state = {
    styleId: 'intel',
    titleSize: 48,
    introSize: 14,
    bodySize: 15,
    headerSize: 14,
    footerSize: 10,
    coverImgH: 220,
    coverImage: null,
    bodyImages: {}
};

const renderer = new marked.Renderer();
renderer.image = function(href, title, text) {
    let widthStyle = '';
    let altText = text;
    if (text && text.includes('|')) {
        const parts = text.split('|');
        altText = parts[0];
        const width = parts[1];
        if (width.match(/^[0-9]+(%|px)$/)) {
            widthStyle = `width: ${width};`;
        }
    }
    let imgSource = href;
    if (href && href.startsWith('img:')) {
        const id = href.split(':')[1];
        if (state.bodyImages[id]) {
            imgSource = state.bodyImages[id];
        }
    }
    const safeKey = (href || '').replace(/"/g, '&quot;');
    return `<img src="${imgSource}" alt="${altText}" title="${title || ''}" style="${widthStyle}" data-img-key="${safeKey}">`;
};

marked.setOptions({ breaks: true, gfm: true, renderer: renderer });

// ==================== 预览区图片交互（大小拖拽 + 对齐） ====================

let currentImgEl = null;
// 图片样式持久化：key = Markdown href（img:xxx 或外链 URL），value = {width, align}
const imgStyleMap = {};

function setImgToolsEnabled(enabled) {
    const tools = document.getElementById('img-tools');
    if (!tools) return;
    if (enabled) {
        tools.classList.remove('opacity-50', 'pointer-events-none');
    } else {
        tools.classList.add('opacity-50', 'pointer-events-none');
    }
}

function selectPreviewImage(img) {
    if (currentImgEl === img) return;
    if (currentImgEl) {
        currentImgEl.style.outline = '';
        currentImgEl.style.outlineOffset = '';
    }
    currentImgEl = img;
    if (currentImgEl) {
        currentImgEl.style.outline = '2px solid #3B82F6';
        currentImgEl.style.outlineOffset = '2px';
        setImgToolsEnabled(true);
        syncImgToolsFromElement(currentImgEl);
    } else {
        setImgToolsEnabled(false);
    }
}

function syncImgToolsFromElement(img) {
    const range = document.getElementById('img-width-range');
    const label = document.getElementById('img-width-val');
    if (!range || !label || !img) return;
    const parent = img.parentElement;
    const parentWidth = parent ? parent.getBoundingClientRect().width : img.getBoundingClientRect().width;
    const imgWidth = img.getBoundingClientRect().width;
    let pct = Math.round((imgWidth / parentWidth) * 100);
    if (!isFinite(pct) || pct <= 0) pct = 100;
    pct = Math.max(30, Math.min(100, pct));
    range.value = String(pct);
    label.textContent = pct + '%';
}

// 将对齐样式直接写到 DOM 元素（供当场应用和重渲还原共用）
function _applyAlignToEl(el, mode) {
    if (!el) return;
    el.style.display = 'block';
    el.style.marginTop = '12px';
    el.style.marginBottom = '12px';
    if (mode === 'left') {
        el.style.marginLeft = '0';
        el.style.marginRight = 'auto';
    } else if (mode === 'right') {
        el.style.marginLeft = 'auto';
        el.style.marginRight = '0';
    } else {
        el.style.marginLeft = 'auto';
        el.style.marginRight = 'auto';
    }
}

function applyImgWidth(percent) {
    if (!currentImgEl) return;
    const pct = Math.max(30, Math.min(100, percent));
    currentImgEl.style.width = pct + '%';
    currentImgEl.style.maxWidth = '100%';
    // 持久化到 map，重渲后可还原
    const key = currentImgEl.getAttribute('data-img-key');
    if (key) {
        imgStyleMap[key] = imgStyleMap[key] || {};
        imgStyleMap[key].width = pct + '%';
    }
}

function applyImgAlign(mode) {
    if (!currentImgEl) return;
    _applyAlignToEl(currentImgEl, mode);
    // 持久化到 map，重渲后可还原
    const key = currentImgEl.getAttribute('data-img-key');
    if (key) {
        imgStyleMap[key] = imgStyleMap[key] || {};
        imgStyleMap[key].align = mode;
    }
}

function bindImageTools() {
    const range = document.getElementById('img-width-range');
    const label = document.getElementById('img-width-val');
    const btnLeft = document.getElementById('img-align-left');
    const btnCenter = document.getElementById('img-align-center');
    const btnRight = document.getElementById('img-align-right');

    if (range) {
        range.addEventListener('input', function () {
            const v = parseInt(this.value, 10) || 100;
            if (label) label.textContent = v + '%';
            applyImgWidth(v);
        });
    }
    if (btnLeft) btnLeft.addEventListener('click', function () { applyImgAlign('left'); });
    if (btnCenter) btnCenter.addEventListener('click', function () { applyImgAlign('center'); });
    if (btnRight) btnRight.addEventListener('click', function () { applyImgAlign('right'); });

    setImgToolsEnabled(false);
}

function attachPreviewImageHandlers() {
    const container = document.getElementById('preview-canvas');
    if (!container) return;
    // currentImgEl 指向的旧 DOM 已被清空，重置选中状态
    currentImgEl = null;
    setImgToolsEnabled(false);

    const imgs = container.querySelectorAll('.markdown-body img');
    imgs.forEach(img => {
        // 还原之前保存的样式（宽度 + 对齐）
        const key = img.getAttribute('data-img-key');
        if (key && imgStyleMap[key]) {
            const saved = imgStyleMap[key];
            if (saved.width) {
                img.style.width = saved.width;
                img.style.maxWidth = '100%';
            }
            if (saved.align) {
                _applyAlignToEl(img, saved.align);
            }
        }
        img.style.cursor = 'pointer';
        img.addEventListener('click', function (e) {
            e.stopPropagation();
            selectPreviewImage(img);
        });
    });
    // 防止每次 updatePreview 重复绑定 container 的点击事件
    if (!container._bgClickBound) {
        container._bgClickBound = true;
        container.addEventListener('click', function (e) {
            if (e.target === container) {
                selectPreviewImage(null);
            }
        });
    }
}

window.onload = () => {
    renderStyleGrid();
    initUrlParams();
    applyPrefill();
    updateTitleCount();
    updatePreview();
    lucide.createIcons();
    initResizers();
    enablePasteImage();
    bindImageTools();
};

function applyPrefill() {
    const p = window._XHS_PREFILL;
    if (!p) return;
    if (p.title) {
        const el = document.getElementById('input-title');
        if (el) el.value = p.title + '';
        const xhsTitleEl = document.getElementById('publish-xhs-title');
        if (xhsTitleEl) { xhsTitleEl.value = (p.title + '').slice(0, 20); updateXhsTitleCount(); }
    }
    if (p.content) document.getElementById('input-content').value = p.content;
    if (p.tag)     document.getElementById('input-tag').value     = p.tag;
    if (p.image_b64 && p.image_b64.startsWith('data:')) {
        state.coverImage = p.image_b64;
    }
    if (p.body_images && typeof p.body_images === 'object') {
        Object.assign(state.bodyImages, p.body_images);
    }
    if (p.desc) {
        const descEl = document.getElementById('publish-desc');
        if (descEl) descEl.value = p.desc;
    }
    if (p.style) {
        const found = STYLES.find(s => s.id === p.style);
        if (found) state.styleId = p.style;
    }
    updateTitleCount();
}

function updateTitleCount() {
    const input   = document.getElementById('input-title');
    const countEl = document.getElementById('input-title-count');
    if (!input || !countEl) return;
    countEl.textContent = (input.value || '').length + ' 字';
}

function updateXhsTitleCount() {
    const input   = document.getElementById('publish-xhs-title');
    const countEl = document.getElementById('publish-xhs-title-count');
    if (!input || !countEl) return;
    const len = (input.value || '').length;
    countEl.textContent = len + '/20';
    countEl.className = 'absolute right-2 top-1/2 -translate-y-1/2 text-[10px] tabular-nums pointer-events-none ' +
        (len >= 20 ? 'text-red-500 font-bold' : len >= 16 ? 'text-amber-500' : 'text-gray-400');
}

// 图片标题变化时，若 XHS 标题为空则自动同步（截取20字）
function autoSyncXhsTitle() {
    const xhsTitleEl = document.getElementById('publish-xhs-title');
    if (!xhsTitleEl || xhsTitleEl.value.trim()) return;
    const imgTitle = (document.getElementById('input-title').value || '').trim();
    xhsTitleEl.value = imgTitle.slice(0, 20);
    updateXhsTitleCount();
}

let isToolbarOpen = false;
function toggleToolbar() {
    isToolbarOpen = !isToolbarOpen;
    const actions = document.getElementById('toolbar-actions');
    const toggleIcon = document.querySelector('#toolbar-toggle i');
    if (isToolbarOpen) {
        actions.classList.remove('scale-0', 'opacity-0');
        toggleIcon.setAttribute('data-lucide', 'x');
    } else {
        actions.classList.add('scale-0', 'opacity-0');
        toggleIcon.setAttribute('data-lucide', 'settings-2');
    }
    lucide.createIcons();
}

function hideToolbar() {
    if(isToolbarOpen) toggleToolbar();
}

let panelState = { left: { width: 350, collapsed: false }, right: { width: 320, collapsed: false } };

function togglePanel(side) {
    const panel = document.getElementById(`${side}-panel`);
    const btnIcon = document.querySelector(`#${side}-toggle i`);
    panelState[side].collapsed = !panelState[side].collapsed;
    if (panelState[side].collapsed) {
        panelState[side].width = parseInt(panel.style.width);
        panel.style.width = '0px'; panel.style.padding = '0px'; panel.style.border = 'none';
        btnIcon.setAttribute('data-lucide', side === 'left' ? 'chevron-right' : 'chevron-left');
    } else {
        panel.style.width = panelState[side].width + 'px';
        panel.style.removeProperty('padding'); panel.style.removeProperty('border');
        btnIcon.setAttribute('data-lucide', side === 'left' ? 'chevron-left' : 'chevron-right');
    }
    lucide.createIcons();
}

function initResizers() {
    setupResizer('resizer-left', 'left-panel', 'left');
    setupResizer('resizer-right', 'right-panel', 'right');
}

function setupResizer(resizerId, panelId, side) {
    const resizer = document.getElementById(resizerId);
    const panel = document.getElementById(panelId);
    let isResizing = false;
    const getX = (e) => e.touches ? e.touches[0].clientX : e.clientX;
    const startResize = (e) => { isResizing = true; resizer.classList.add('active'); document.body.style.cursor = 'col-resize'; document.body.classList.add('select-none'); if (e.touches) e.preventDefault(); };
    const onMove = (e) => {
        if (!isResizing) return;
        if (panelState[side].collapsed) togglePanel(side);
        const clientX = getX(e);
        const container = document.getElementById('xhs-full-container');
        const rect = container.getBoundingClientRect();
        let newWidth = side === 'left' ? clientX - rect.left : rect.right - clientX;
        if (newWidth < 100) newWidth = 100; if (newWidth > 600) newWidth = 600;
        panel.style.width = newWidth + 'px'; panelState[side].width = newWidth;
    };
    const endResize = () => { if(isResizing) { isResizing = false; resizer.classList.remove('active'); document.body.style.cursor = 'default'; document.body.classList.remove('select-none'); } };
    resizer.addEventListener('mousedown', startResize); document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', endResize);
    resizer.addEventListener('touchstart', startResize, { passive: false }); document.addEventListener('touchmove', onMove, { passive: false }); document.addEventListener('touchend', endResize);
}

function initUrlParams() {
    const urlParams = new URLSearchParams(window.location.search);
    if(urlParams.has('title')) {
        const el = document.getElementById('input-title');
        if (el) el.value = decodeURIComponent(urlParams.get('title'));
    }
    if(urlParams.has('content')) document.getElementById('input-content').value = decodeURIComponent(urlParams.get('content'));
}

async function pasteFromClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        const textarea = document.getElementById('input-content');
        textarea.value = textarea.value.substring(0, textarea.selectionStart) + text + textarea.value.substring(textarea.selectionEnd);
        textarea.focus(); updatePreview();
    } catch (err) { alert('请使用 Ctrl+V 粘贴'); }
}

function enablePasteImage() {
    document.getElementById('input-content').addEventListener('paste', function(e) {
        const items = (e.clipboardData || e.originalEvent.clipboardData).items;
        for (let i = 0; i < items.length; i++) {
            if (items[i].kind === 'file' && items[i].type.indexOf('image/') !== -1) {
                e.preventDefault();
                const reader = new FileReader();
                reader.onload = function(event) {
                    const id = Date.now().toString(); state.bodyImages[id] = event.target.result;
                    const textarea = document.getElementById('input-content');
                    textarea.value = textarea.value.substring(0, textarea.selectionStart) + `![截图](img:${id})` + textarea.value.substring(textarea.selectionEnd);
                    updatePreview();
                };
                reader.readAsDataURL(items[i].getAsFile());
            }
        }
    });
}

function renderStyleGrid() {
    const grid = document.getElementById('style-grid'); grid.innerHTML = '';
    STYLES.forEach(style => {
        const btn = document.createElement('button');
        const isActive = style.id === state.styleId;
        btn.className = `p-2.5 rounded-lg border text-xs font-bold transition-all flex items-center justify-center gap-2 relative overflow-hidden group ${isActive ? 'border-black bg-black text-white' : 'border-gray-200 hover:bg-gray-50'}`;
        btn.innerHTML = `<div class="w-2 h-2 rounded-full border border-black/10 ${isActive ? 'border-white/50' : ''}" style="background-color: ${style.bg}"></div>${style.name.split(' ')[1]}`;
        btn.onclick = () => { state.styleId = style.id; renderStyleGrid(); updatePreview(); };
        grid.appendChild(btn);
    });
}

function handleImageUpload(input) {
    const file = input.files[0]; if (!file) return;
    const reader = new FileReader(); reader.onload = (e) => { state.coverImage = e.target.result; updatePreview(); }; reader.readAsDataURL(file);
}

function handleBodyImageUpload(input) {
    const file = input.files[0]; if (!file) return;
    const reader = new FileReader(); reader.onload = (e) => {
        const id = Date.now().toString(); state.bodyImages[id] = e.target.result;
        const textarea = document.getElementById('input-content'); textarea.value = textarea.value + `\n![插图](img:${id})\n`; updatePreview(); input.value = '';
    }; reader.readAsDataURL(file);
}

function clearImage() { state.coverImage = null; document.getElementById('cover-image-upload').value = ''; updatePreview(); }

// ==================== 自动分页 ====================
function autoSplitContent(raw) {
    // 1. 先按 @--- 硬分页
    const hardSegs = raw.split('@---');
    const pages = [];
    const CHARS_PER_PAGE = 420; // 每页字符预算（约 15 行正文）

    for (const seg of hardSegs) {
        const trimmed = seg.trim();
        if (!trimmed) continue;

        // 2. 按段落（空行）为单位贪心打包，## 不触发分页
        const parts = trimmed.split(/\n\n+/).filter(p => p.trim());
        if (!parts.length) { pages.push(trimmed); continue; }

        let buffer = '';
        for (const part of parts) {
            const candidate = buffer ? buffer + '\n\n' + part.trim() : part.trim();
            if (buffer && candidate.length > CHARS_PER_PAGE) {
                pages.push(buffer.trim());
                buffer = part.trim();
            } else {
                buffer = candidate;
            }
        }
        if (buffer.trim()) pages.push(buffer.trim());
    }
    return pages.filter(p => p.trim());
}

// ==================== 核心：渲染与包裹逻辑 ====================
function updatePreview() {
    const container = document.getElementById('preview-canvas'); container.innerHTML = '';

    const title = document.getElementById('input-title').value;
    const date = document.getElementById('input-date').value;
    const tag = document.getElementById('input-tag').value;
    const rawContent = document.getElementById('input-content').value;

    state.bodySize = parseInt(document.getElementById('body-size').value, 10);
    state.titleSize = parseInt(document.getElementById('title-size').value, 10);
    const headerSelect = document.getElementById('header-size');
    if (headerSelect) {
        state.headerSize = parseInt(headerSelect.value, 10);
        document.getElementById('header-size-val').innerText = state.headerSize + 'px';
    }

    const baseSize = document.getElementById('heading-scale').value;
    document.getElementById('heading-scale-val').innerText = baseSize + 'px';
    document.getElementById('dynamic-heading-style').innerHTML = `
        .markdown-body h1 { font-size: ${baseSize}px !important; line-height: 1.3 !important; }
        .markdown-body h2 { font-size: ${Math.round(baseSize * 0.75)}px !important; line-height: 1.35 !important; margin-top: 0.5em !important; margin-bottom: 0.3em !important; }
        .markdown-body h3 { font-size: ${Math.round(baseSize * 0.6)}px !important; margin-top: 0.5em !important; }
        .markdown-body h4 { font-size: ${Math.round(baseSize * 0.5)}px !important; }
    `;

    const footerRange = document.getElementById('footer-size');
    if (footerRange) {
        state.footerSize = parseInt(footerRange.value, 10);
        document.getElementById('footer-size-val').innerText = state.footerSize + 'px';
    }

    const coverImgHRange = document.getElementById('cover-img-h');
    if (coverImgHRange) {
        state.coverImgH = parseInt(coverImgHRange.value, 10);
        document.getElementById('cover-img-h-val').innerText = state.coverImgH + 'px';
    }

    document.getElementById('body-size-val').innerText = state.bodySize + 'px';
    document.getElementById('title-size-val').innerText = state.titleSize + 'px';

    const sizeVal = document.getElementById('canvas-size').value.split('x');
    const cardWidth = sizeVal[0];
    const cardHeight = sizeVal[1];
    const styleConfig = STYLES.find(s => s.id === state.styleId);

    // 自动分页（不再单独渲染封面卡）
    const pages = autoSplitContent(rawContent);

    const createCardWithDownload = (elementHTML, filename) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'relative group';

        const card = document.createElement('div');
        card.className = `card-wrapper ${styleConfig.class}`;
        card.style.width = cardWidth + 'px';
        card.style.height = cardHeight + 'px';
        card.innerHTML = elementHTML;

        const btn = document.createElement('button');
        btn.className = 'absolute top-3 right-3 z-50 bg-black/60 hover:bg-black text-white p-2 rounded-full opacity-0 group-hover:opacity-100 transition-all duration-200 shadow-lg cursor-pointer transform hover:scale-110';
        btn.title = "保存为JPG";
        btn.innerHTML = '<i data-lucide="download" size="16"></i>';
        btn.onclick = (e) => { e.stopPropagation(); saveSingleCard(card, filename, btn); };

        wrapper.appendChild(card);
        wrapper.appendChild(btn);
        return wrapper;
    };

    pages.forEach((pageText, index) => {
        const isFirstPage = index === 0;
        let bodyRaw = pageText.trim();

        // 第一页：如果正文以 # 开头则删掉（改用封面标题字段代替）
        if (isFirstPage) {
            bodyRaw = bodyRaw.replace(/^\s*#\s+.+?(?:\n|$)/m, '').trim();
        }

        let processedText = bodyRaw.replace(/::: row\n([\s\S]*?)\n:::/g, '<div class="img-row">$1</div>');
        const htmlContent = marked.parse(processedText);

        container.appendChild(createCardWithDownload(
            renderPageHTML(styleConfig, htmlContent, index + 1, date, {
                isFirstPage,
                firstPageTitle: isFirstPage ? title : null,
                hasCoverImage:  isFirstPage && !!state.coverImage,
            }),
            `rednote_page_${index + 1}.jpg`
        ));
    });
    attachPreviewImageHandlers();
    lucide.createIcons();
}

// ==================== 极速 JPG 导出逻辑 ====================
async function saveSingleCard(element, filename, btn) {
    const originalIcon = btn.innerHTML;
    btn.innerHTML = '<i data-lucide="loader-2" class="animate-spin" size="16"></i>';
    btn.classList.add('bg-blue-600', 'opacity-100'); btn.classList.remove('bg-black/60', 'group-hover:opacity-100');

    try {
        const dataUrl = await htmlToImage.toJpeg(element, {
            quality: 0.85,
            pixelRatio: 4,
            backgroundColor: '#ffffff'
        });
        saveAs(dataUrl, filename);
    } catch (error) {
        console.error('保存失败:', error);
        alert('保存出错');
    } finally {
        setTimeout(() => {
            btn.innerHTML = originalIcon;
            btn.classList.remove('bg-blue-600', 'opacity-100');
            btn.classList.add('bg-black/60');
            lucide.createIcons();
        }, 300);
    }
}

async function downloadAll() {
    const btn = document.querySelector('button[onclick="downloadAll()"]');
    const originalText = btn.innerHTML;
    const cards = document.querySelectorAll('.card-wrapper');
    btn.innerHTML = `<i data-lucide="loader-2" class="animate-spin" size="14"></i> 导出中...`;
    lucide.createIcons();

    try {
        for (let i = 0; i < cards.length; i++) {
            btn.innerHTML = `<i data-lucide="loader-2" class="animate-spin" size="14"></i> ${i+1}/${cards.length}`;
            lucide.createIcons();
            const dataUrl = await htmlToImage.toJpeg(cards[i], {
                quality: 0.85,
                pixelRatio: 4,
                backgroundColor: '#ffffff'
            });
            saveAs(dataUrl, `rednote_${i+1}.jpg`);
            // 多张时稍作间隔，避免浏览器阻止批量下载
            if (cards.length > 1) await new Promise(r => setTimeout(r, 300));
        }
    } catch (error) {
        console.error('导出失败:', error);
        alert('导出出错');
    } finally {
        btn.innerHTML = originalText;
        lucide.createIcons();
    }
}

// ==================== 卡片渲染函数 ====================
function renderCoverHTML(config, title, date, tag, intro) {
    if (state.coverImage) {
        let themeStyles = {
            'shoujo': { bg: '#FFF0F5', text: '#8C4A7A', title: '#5C2A4E', border: '#E8829A', fontTitle: "'Noto Sans SC', sans-serif", fontBody: "'Noto Sans SC', sans-serif" },
            'acid':   { bg: '#CCFF00', text: '#000', title: '#000', border: '#000', fontTitle: "sans-serif", fontBody: "'Noto Sans SC', sans-serif" },
            'tech':   { bg: '#0F172A', text: '#94A3B8', title: '#FFF', border: '#3B82F6', fontTitle: "'Inter', sans-serif", fontBody: "'Inter', sans-serif" }
        };
        let s = themeStyles[config.id];
        let titleStyle = `color: ${s.title};`;
        if(config.id === 'tech') titleStyle = `background: linear-gradient(to right, #60A5FA, #A78BFA); -webkit-background-clip: text; color: transparent;`;

        return `
        <div class="card-bg p-0 flex flex-col h-full overflow-hidden" style="padding: 0; background-color: ${s.bg};">
            <div class="h-[55%] w-full relative overflow-hidden bg-gray-100"><img src="${state.coverImage}" class="w-full h-full object-cover"></div>
            <div class="h-[45%] w-full p-8 flex flex-col justify-center text-left">
                <div class="flex items-center gap-2 mb-4 text-xs font-bold opacity-70" style="color: ${s.text};"><i data-lucide="user" size="14"></i><span>${tag}</span></div>
                <h1 class="leading-[1.1] mb-5 font-bold" style="font-size: ${state.titleSize}px; margin-left:0; margin-right:0; text-align: left; text-shadow: none; border: none; padding: 0; font-family: ${s.fontTitle}; ${titleStyle}">${title}</h1>
                <div class="pl-4 border-l-4 leading-relaxed opacity-90 font-medium" style="border-color: ${s.border}; color: ${s.text}; font-family: ${s.fontBody}; white-space: pre-wrap; font-size: ${state.introSize}px;">${intro}</div>
            </div>
        </div>`;
    }
    if (config.id === 'acid') return `<div class="card-bg"><div class="flex justify-between border-b-2 border-black pb-2 mb-6 font-mono font-bold" style="font-size: 36px;"><span>${date}</span><span>ISSUE</span></div><div class="flex-1 flex flex-col justify-center items-center text-center"><h1 class="text-black font-black uppercase leading-[0.9] transform skew-x-2 drop-shadow-xl" style="font-size: ${state.titleSize}px;">${title}</h1><div class="mt-6 bg-black text-[#CCFF00] px-4 py-2 font-bold text-lg transform skew-x-12">${tag}</div></div></div>`;
    if (config.id === 'tech') return `<div class="card-bg justify-center relative"><div class="grid-bg"></div><div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] bg-blue-500/20 blur-[100px] rounded-full pointer-events-none"></div><div class="z-10 text-center"><div class="text-blue-400 font-mono text-xs mb-6 tracking-[0.3em] uppercase border border-blue-500/30 inline-block px-3 py-1 rounded bg-blue-900/20 backdrop-blur">System Ready</div><h1 class="font-bold leading-tight mb-6" style="font-size: ${state.titleSize}px; background: linear-gradient(to right, #60A5FA, #A78BFA); -webkit-background-clip: text; color: transparent;">${title}</h1><div class="flex items-center justify-center gap-2 text-gray-400 font-mono" style="font-size: 36px;"><span>${date}</span><span class="text-blue-500">//</span><span>${tag}</span></div></div></div>`;
    return `<div class="card-bg justify-center text-center"><h1 class="font-bold text-gray-900 mt-4" style="font-size: ${state.titleSize}px">${title}</h1></div>`;
}

function renderCoverHTMLV2(config, title, date, tag, intro) {
    const typeSize = state.headerSize || 14;

    // ── 游戏雷达局：独立分支 ──
    if (config.id === 'intel') {
        const coverImg = state.coverImage
            ? `<div style="margin:0 16px 14px;border-radius:6px;overflow:hidden;border:1px solid rgba(255,107,43,0.25);height:${state.coverImgH}px;flex-shrink:0;"><img src="${state.coverImage}" style="width:100%;height:100%;object-fit:cover;"></div>`
            : '';
        const mainFlex = state.coverImage ? 'padding:18px 22px 10px' : 'flex:1;padding:24px 22px 18px';
        return `
        <div class="card-bg" style="position:relative;background:#0D1B2A;padding:0;display:flex;flex-direction:column;overflow:hidden;height:100%;box-sizing:border-box;font-family:'Inter','Noto Sans SC',sans-serif;">
            <div style="background:#070F1A;border-bottom:2px solid #FF6B2B;padding:7px 18px;display:flex;align-items:center;flex-shrink:0;position:relative;z-index:1;">
                <span style="font-size:10px;color:#FF6B2B;font-weight:800;letter-spacing:0.06em;font-family:'Noto Sans SC',sans-serif;">&#9679; GAME RADAR</span>
            </div>
            <div style="${mainFlex};display:flex;flex-direction:column;justify-content:center;position:relative;z-index:1;">
                ${date ? `<div style="display:inline-flex;align-items:center;gap:5px;background:rgba(255,107,43,0.15);border:1px solid rgba(255,107,43,0.45);color:#FF6B2B;font-size:${typeSize}px;font-weight:700;padding:3px 10px;border-radius:3px;margin-bottom:12px;width:fit-content;letter-spacing:1px;">[INFO] ${date}</div>` : ''}
                <h1 style="font-size:${state.titleSize}px;font-weight:900;color:#FFFFFF;line-height:1.15;margin:0 0 12px;letter-spacing:-0.01em;">${title}</h1>
                ${intro ? `<p style="color:#8AACBE;font-size:13px;line-height:1.6;margin:0;border-left:2px solid rgba(255,107,43,0.5);padding-left:10px;">${intro}</p>` : ''}
            </div>
            ${coverImg}
            <div style="background:#FF6B2B;padding:7px 18px;display:flex;align-items:center;flex-shrink:0;position:relative;z-index:1;">
                <span style="font-size:${state.footerSize}px;color:#fff;font-weight:800;letter-spacing:0.06em;font-family:'Noto Sans SC',sans-serif;">${tag || '游戏雷达局'}</span>
            </div>
        </div>`;
    }

    // ── 有封面图：统一顶部色条 + 文字 + 图片布局 ──
    if (state.coverImage) {
        const imgS = {
            'shoujo':  { bg: '#FFF0F5', tc: '#5C2A4E',      sc: '#8C4A7A', bar: 'linear-gradient(to right,#E8829A,#F4B8C8)', fT: "'Noto Sans SC',sans-serif",          fB: "'Noto Sans SC',sans-serif"         },
            'acid':    { bg: '#CCFF00', tc: '#000',          sc: '#000',    bar: '#000',                                      fT: 'sans-serif',                         fB: "'Noto Sans SC',sans-serif" },
            'tech':    { bg: '#0A0F1E', tc: 'transparent',  sc:'#94A3B8',  bar: 'linear-gradient(to right,#3B82F6,#8B5CF6)', fT: "'Inter',sans-serif",                 fB: "'Inter',sans-serif"       },
            'pro':     { bg: '#0F1824', tc: '#EAF0F8',       sc:'#8AACBE',  bar: '#E8820C',                                   fT: "'Noto Sans SC',sans-serif",          fB: "'Noto Sans SC',sans-serif" }
        };
        const s = imgS[config.id] || imgS['shoujo'];
        const tStyle = config.id === 'tech'
            ? 'background:linear-gradient(to right,#60A5FA,#A78BFA);-webkit-background-clip:text;color:transparent;'
            : `color:${s.tc};`;
        const tagColor = config.id === 'pro' ? 'color:#fff;background:#E8820C;padding:6px 16px;font-weight:800;' : `color:${s.sc};border-top:1px solid rgba(0,0,0,0.07);padding:8px 24px;text-align:center;`;
        return `
        <div class="card-bg flex flex-col h-full overflow-hidden" style="padding:0;background:${s.bg};position:relative;">
            <div style="height:${config.id==='pro'?'2px':'5px'};background:${s.bar};flex-shrink:0;position:relative;z-index:1;"></div>
            <div style="padding:16px 24px 10px;position:relative;z-index:1;">
                ${date ? `<div style="font-size:${typeSize}px;color:${s.sc};font-weight:700;margin-bottom:6px;font-family:${s.fT};">${date}</div>` : ''}
                <h1 style="font-size:${state.titleSize}px;font-weight:900;line-height:1.15;margin:0 0 8px;font-family:${s.fT};${tStyle}">${title}</h1>
                ${intro ? `<div class="markdown-body" style="color:${s.sc};font-family:${s.fB};font-size:${state.introSize || 13}px;">${marked.parse(intro)}</div>` : ''}
            </div>
            <div style="height:${state.coverImgH}px;flex-shrink:0;margin:0 16px 12px;border-radius:${config.id==='pro'?'4px':'8px'};overflow:hidden;background:#111;position:relative;z-index:1;">
                <img src="${state.coverImage}" style="width:100%;height:100%;object-fit:cover;">
            </div>
            ${tag ? `<div style="font-size:${state.footerSize}px;${tagColor}">${tag}</div>` : ''}
        </div>`;
    }

    // ── 无封面图：各主题几何装饰封面 ──

    // 1. 少女星：粉白底 + 渐变光晕 + 花瓣装饰圆 + CP卡片感
    if (config.id === 'shoujo') {
        return `
        <div class="card-bg" style="position:relative;background:#FFF0F5;padding:36px 32px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;height:100%;box-sizing:border-box;font-family:'Noto Sans SC',sans-serif;">
            <div style="position:absolute;right:-40px;top:-40px;width:200px;height:200px;border-radius:50%;background:radial-gradient(circle,rgba(232,130,154,0.22),transparent);pointer-events:none;"></div>
            <div style="position:absolute;left:-30px;bottom:-30px;width:160px;height:160px;border-radius:50%;background:radial-gradient(circle,rgba(244,184,200,0.28),transparent);pointer-events:none;"></div>
            <div style="position:absolute;right:28px;bottom:90px;width:64px;height:64px;border-radius:50%;border:2px solid rgba(232,130,154,0.35);pointer-events:none;"></div>
            <div style="position:absolute;right:44px;bottom:106px;width:32px;height:32px;border-radius:50%;background:rgba(232,130,154,0.15);pointer-events:none;"></div>
            <div style="position:relative;z-index:1;">
                ${date ? `<div style="display:inline-flex;align-items:center;gap:6px;font-size:${typeSize}px;color:#E8829A;font-weight:700;margin-bottom:14px;letter-spacing:1px;background:rgba(232,130,154,0.10);border:1px solid rgba(232,130,154,0.35);padding:3px 10px;border-radius:20px;">✦ ${date}</div>` : ''}
                <h1 style="font-size:${state.titleSize}px;font-weight:900;color:#5C2A4E;line-height:1.2;margin:0 0 14px;letter-spacing:0.01em;">${title}</h1>
                <div style="width:40px;height:3px;background:linear-gradient(to right,#E8829A,#F4B8C8);border-radius:2px;margin-bottom:14px;"></div>
                ${intro ? `<p style="color:#8C4A7A;font-size:13px;line-height:1.7;margin:0;">${intro}</p>` : ''}
            </div>
            <div style="position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;padding-top:14px;border-top:1px solid rgba(232,130,154,0.25);">
                <span style="font-size:${state.footerSize}px;color:#8C4A7A;font-weight:700;">${tag || ''}</span>
                <span style="font-size:14px;color:rgba(232,130,154,0.7);">✿</span>
            </div>
        </div>`;
    }

    // 2. 锐角警报：酸黄 + 黑色斜切色块 + GAME水印 + 底部黑条
    if (config.id === 'acid') {
        return `
        <div class="card-bg" style="position:relative;background:#CCFF00;padding:28px 28px 0;display:flex;flex-direction:column;overflow:hidden;height:100%;box-sizing:border-box;">
            <div style="position:absolute;right:0;top:0;width:100%;height:100%;background:#000;clip-path:polygon(62% 0%,100% 0%,100% 100%,46% 100%);pointer-events:none;"></div>
            <div style="position:absolute;left:-8px;top:28px;font-size:108px;font-weight:900;color:#000;opacity:0.08;line-height:1;font-family:sans-serif;letter-spacing:-4px;pointer-events:none;user-select:none;">GAME</div>
            <div style="position:relative;z-index:1;flex:1;display:flex;flex-direction:column;justify-content:center;padding-bottom:16px;">
                ${date ? `<div style="font-size:${typeSize}px;color:#000;font-weight:900;margin-bottom:12px;text-transform:uppercase;letter-spacing:3px;font-family:monospace;">${date}</div>` : ''}
                <h1 style="font-size:${state.titleSize}px;font-weight:900;color:#000;text-transform:uppercase;line-height:1.05;text-shadow:5px 5px 0 rgba(0,0,0,0.12);letter-spacing:-0.5px;margin:0 0 16px;max-width:58%;">${title}</h1>
                ${intro ? `<p style="color:#000;font-size:13px;line-height:1.5;margin:0;font-weight:700;max-width:55%;">${intro}</p>` : ''}
            </div>
            <div style="position:relative;z-index:1;margin:0 -28px;background:#000;height:44px;display:flex;align-items:center;padding:0 28px;flex-shrink:0;">
                <span style="font-size:${state.footerSize}px;color:#CCFF00;font-weight:800;letter-spacing:3px;text-transform:uppercase;font-family:monospace;">${tag || 'AUTHOR'}</span>
            </div>
        </div>`;
    }

    // 4. 霓虹矩阵：深色 + "/"装饰 + 双色光晕 + 状态栏
    if (config.id === 'tech') {
        return `
        <div class="card-bg" style="position:relative;background:#0A0F1E;padding:28px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;height:100%;box-sizing:border-box;font-family:'Inter',monospace;">
            <div style="position:absolute;left:-12px;top:-30px;font-size:220px;font-weight:900;color:#3B82F6;opacity:0.10;line-height:1;pointer-events:none;user-select:none;font-family:monospace;">/</div>
            <div style="position:absolute;right:-50px;bottom:-50px;width:180px;height:180px;border-radius:50%;background:radial-gradient(circle,rgba(59,130,246,0.5),transparent);filter:blur(35px);pointer-events:none;"></div>
            <div style="position:absolute;right:10px;bottom:10px;width:110px;height:110px;border-radius:50%;background:radial-gradient(circle,rgba(139,92,246,0.45),transparent);filter:blur(22px);pointer-events:none;"></div>
            <div style="position:relative;z-index:1;">
                <div style="font-size:10px;color:#3B82F6;font-family:monospace;letter-spacing:2px;margin-bottom:18px;opacity:0.8;">● LIVE &nbsp;//&nbsp; GAMING NEWS &nbsp;//&nbsp; 2026</div>
                ${date ? `<div style="font-size:${typeSize}px;color:#94A3B8;font-family:monospace;margin-bottom:10px;letter-spacing:1px;">${date}</div>` : ''}
                <h1 style="font-size:${state.titleSize}px;font-weight:900;line-height:1.15;margin:0 0 14px;background:linear-gradient(to right,#60A5FA,#A78BFA);-webkit-background-clip:text;color:transparent;">${title}</h1>
                ${intro ? `<p style="color:#94A3B8;font-size:13px;line-height:1.6;margin:0;">${intro}</p>` : ''}
            </div>
            <div style="position:relative;z-index:1;border-top:1px solid rgba(59,130,246,0.3);padding-top:12px;display:flex;align-items:center;justify-content:space-between;">
                <span style="font-size:${state.footerSize}px;color:#60A5FA;font-family:monospace;letter-spacing:1px;">${tag || ''}</span>
                <span style="font-size:12px;color:rgba(59,130,246,0.5);font-family:monospace;">◈</span>
            </div>
        </div>`;
    }

    // 5. 公众号风：深海军蓝 + 琥珀橙
    if (config.id === 'pro') {
        const coverImg = state.coverImage
            ? `<div style="margin:0 0 14px;border-radius:6px;overflow:hidden;border:1px solid rgba(232,130,12,0.25);height:${state.coverImgH}px;flex-shrink:0;"><img src="${state.coverImage}" style="width:100%;height:100%;object-fit:cover;"></div>`
            : '';
        return `
        <div class="card-bg" style="position:relative;background:#0F1824;padding:0;display:flex;flex-direction:column;overflow:hidden;height:100%;box-sizing:border-box;font-family:'Noto Sans SC','Inter',sans-serif;">
            <div style="background:#0A1220;border-bottom:2px solid #E8820C;padding:7px 18px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;position:relative;z-index:1;">
                <span style="font-size:10px;color:#E8820C;font-weight:800;letter-spacing:3px;font-family:monospace;">&#9632; GAME RADAR HQ</span>
                <span style="font-size:10px;color:rgba(232,130,12,0.45);font-family:monospace;">WEEKLY</span>
            </div>
            <div style="flex:1;padding:22px 24px 16px;display:flex;flex-direction:column;justify-content:center;position:relative;z-index:1;">
                ${date ? `<div style="display:inline-flex;align-items:center;gap:5px;background:rgba(232,130,12,0.12);border:1px solid rgba(232,130,12,0.4);color:#E8820C;font-size:${typeSize}px;font-weight:700;padding:3px 10px;border-radius:3px;margin-bottom:12px;width:fit-content;letter-spacing:1px;">${date}</div>` : ''}
                <h1 style="font-size:${state.titleSize}px;font-weight:900;color:#EAF0F8;line-height:1.15;margin:0 0 12px;letter-spacing:-0.01em;">${title}</h1>
                <div style="width:36px;height:3px;background:#E8820C;border-radius:2px;margin-bottom:12px;"></div>
                ${intro ? `<p style="color:#8AACBE;font-size:13px;line-height:1.6;margin:0;border-left:2px solid rgba(232,130,12,0.5);padding-left:10px;">${intro}</p>` : ''}
            </div>
            ${coverImg}
            <div style="background:#E8820C;padding:7px 18px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;position:relative;z-index:1;">
                <span style="font-size:${state.footerSize}px;color:#fff;font-weight:800;letter-spacing:2px;">${tag || '游戏雷达局'}</span>
                <span style="font-size:10px;color:rgba(255,255,255,0.65);font-family:monospace;">&#9679; WEEKLY</span>
            </div>
        </div>`;
    }

    // fallback
    return `<div class="card-bg flex flex-col h-full justify-center text-center"><h1 style="font-size:${state.titleSize}px;font-weight:900;">${title}</h1></div>`;
}

function renderPageHTML(config, html, pageNum, date, opts) {
    opts = opts || {};
    const isFirstPage  = opts.isFirstPage;
    const hasCoverImage = opts.hasCoverImage;

    // 封面图 banner（第一页顶部全宽图，紧跟 headerBar 之后）
    const coverPads = { intel: 24, shoujo: 32, acid: 24, tech: 24, pro: 24 };
    const pad = coverPads[config.id] || 24;
    const coverImgHtml = hasCoverImage
        ? `<div style="margin:0 -${pad}px 10px;height:${state.coverImgH}px;flex-shrink:0;overflow:hidden;"><img src="${state.coverImage}" style="width:100%;height:100%;object-fit:cover;"></div>`
        : '';

    // 标题块（第一页使用封面标题字段）
    const titleBlock = (isFirstPage && opts.firstPageTitle)
        ? `<div class="first-page-title-block markdown-body" style="font-size: ${document.getElementById('heading-scale').value}px;"><h1>${opts.firstPageTitle}</h1></div>`
        : '';

    const bodyHtml = `<div class="markdown-body flex-1 overflow-hidden" style="font-size: ${state.bodySize}px">${html}</div>`;
    const userName = document.getElementById('input-tag').value || '';

    // 顶部主题色条（负 margin 抵消 card-bg padding，撑满卡片宽度）
    const headerBars = {
        'intel':   `<div style="margin:-24px -24px 14px;flex-shrink:0;"><div style="height:2px;background:#FF6B2B;"></div><div style="background:#070F1A;border-bottom:1px solid rgba(255,107,43,0.3);padding:5px 24px;display:flex;align-items:center;"><span style="font-size:9px;color:#FF6B2B;font-weight:800;letter-spacing:0.06em;font-family:'Noto Sans SC',sans-serif;">&#9679; GAME RADAR</span></div></div>`,
        'shoujo':  `<div style="height:4px;margin:-32px -32px 18px;background:linear-gradient(to right,#E8829A,#F4B8C8);flex-shrink:0;"></div>`,
        'acid':    `<div style="height:8px;margin:-24px -24px 14px;background:#000;flex-shrink:0;"></div>`,
        'tech':    `<div style="height:4px;margin:-24px -24px 14px;background:linear-gradient(to right,#3B82F6,#8B5CF6);flex-shrink:0;"></div>`,
        'pro':     `<div style="margin:-24px -24px 14px;flex-shrink:0;"><div style="height:2px;background:#E8820C;"></div><div style="background:#0A1220;border-bottom:1px solid rgba(232,130,12,0.25);padding:5px 24px;display:flex;align-items:center;justify-content:space-between;"><span style="font-size:9px;color:#E8820C;font-weight:800;letter-spacing:2px;font-family:monospace;">&#9632; GAME RADAR HQ</span><span style="font-size:9px;color:rgba(232,130,12,0.4);font-family:monospace;">WEEKLY</span></div></div>`
    };
    const headerBar = headerBars[config.id] || '';

    // 页尾样式 —— intel / pro 用实心色块 bar，其余用细线文字
    let footerHtml = '';
    if (userName) {
        if (config.id === 'intel') {
            footerHtml = `<div style="margin-top:auto;margin-left:-24px;margin-right:-24px;margin-bottom:-24px;background:#FF6B2B;padding:8px 18px;display:flex;align-items:center;flex-shrink:0;position:relative;z-index:1;">
                <span style="font-size:${state.footerSize}px;color:#fff;font-weight:800;letter-spacing:0.06em;font-family:'Noto Sans SC',sans-serif;">${userName}</span>
            </div>`;
        } else if (config.id === 'pro') {
            footerHtml = `<div style="margin-top:auto;margin-left:-24px;margin-right:-24px;margin-bottom:-24px;background:#E8820C;padding:8px 18px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;position:relative;z-index:1;">
                <span style="font-size:${state.footerSize}px;color:#fff;font-weight:800;letter-spacing:2px;font-family:monospace;">${userName}</span>
                <span style="font-size:10px;color:rgba(255,255,255,0.65);font-family:monospace;">&#9632; WEEKLY</span>
            </div>`;
        } else {
            const footerStyles = {
                'shoujo': `color:#E8829A;border-top:1px solid rgba(232,130,154,0.3);font-family:'Noto Sans SC',sans-serif;`,
                'acid':   `color:#000;border-top:3px solid #000;font-weight:800;`,
                'tech':   `color:#60A5FA;border-top:1px solid rgba(59,130,246,0.3);font-family:monospace;letter-spacing:1px;`,
            };
            const footerStyle = footerStyles[config.id] || '';
            footerHtml = `<div class="mt-auto w-full px-2 py-2 text-center" style="font-size:${state.footerSize}px;${footerStyle}">${userName}</div>`;
        }
    }

    return `<div class="card-bg flex flex-col h-full">${headerBar}${coverImgHtml}${titleBlock}${bodyHtml}${footerHtml}</div>`;
}

// ==================== 缩放与布局 ====================
let currentZoom = 1.0;
let isGridView = false;
function changeZoom(delta) {
    currentZoom = parseFloat((currentZoom + delta).toFixed(1));
    currentZoom = Math.min(Math.max(currentZoom, 0.2), 2.0);
    const canvas = document.getElementById('preview-canvas');
    canvas.style.transform = `scale(${currentZoom})`;
    if(isGridView) canvas.style.width = `${100/currentZoom}%`;
    else canvas.style.width = '100%';
    document.getElementById('zoom-val').innerText = Math.round(currentZoom * 100) + '%';
}

// ==================== 一键发布小红书（Modal 流程） ====================

let _xhsFullPendingTitle = '';
let _xhsFullPendingDesc  = '';

function _xhsfFormatDTLocal(date) {
    const pad = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function openXhsFullPublishModal() {
    const modal = document.getElementById('xhs-full-publish-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    // 重置状态
    const nowR = document.getElementById('xhsf-publish-now');
    const laterR = document.getElementById('xhsf-publish-later');
    const dtInput = document.getElementById('xhsf-post-time-input');
    if (nowR) nowR.checked = true;
    if (laterR) laterR.checked = false;
    if (dtInput) { dtInput.disabled = true; dtInput.value = ''; }
    lucide.createIcons();
}

function closeXhsFullPublishModal() {
    const modal = document.getElementById('xhs-full-publish-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.style.display = 'none';
}

// 入口：验证 → 弹窗
function publishToXhs() {
    // XHS 标题优先用右栏"发布设置"中的独立字段，为空则取图片标题前20字
    let xhsTitle = (document.getElementById('publish-xhs-title').value || '').trim();
    if (!xhsTitle) {
        const imgTitle = (document.getElementById('input-title').value || '').trim();
        xhsTitle = imgTitle.slice(0, 20);
    }
    const desc = (document.getElementById('publish-desc').value || '').trim() || xhsTitle;
    if (!xhsTitle) { alert('请先填写小红书标题（右侧"发布设置"中）。'); return; }
    const cards = document.querySelectorAll('.card-wrapper');
    if (!cards.length) { alert('没有可发布的卡片，请先编辑内容。'); return; }
    _xhsFullPendingTitle = xhsTitle;
    _xhsFullPendingDesc  = desc;
    openXhsFullPublishModal();
}

// 实际执行：渲染 → 上传 → 发布
async function _doPublishToXhs(cookie, isDraft) {
    const statusEl = document.getElementById('xhs-publish-status');
    const title = _xhsFullPendingTitle;
    const desc  = _xhsFullPendingDesc;
    const cards = document.querySelectorAll('.card-wrapper');

    try {
        // Step 1: 渲染所有卡片为 JPG
        statusEl.textContent = '正在渲染卡片图片...';
        const images = [];
        for (let i = 0; i < cards.length; i++) {
            statusEl.textContent = `正在渲染卡片 ${i + 1}/${cards.length}...`;
            try {
                const dataUrl = await htmlToImage.toJpeg(cards[i], {
                    quality: 0.85, pixelRatio: 2, backgroundColor: '#ffffff', cacheBust: true
                });
                if (dataUrl && dataUrl.startsWith('data:')) images.push(dataUrl);
            } catch (renderErr) {
                console.warn(`卡片 ${i + 1} 渲染失败，尝试备用方案...`, renderErr);
                const dataUrl = await htmlToImage.toPng(cards[i], {
                    backgroundColor: '#ffffff', cacheBust: true, skipAutoScale: true
                });
                if (dataUrl && dataUrl.startsWith('data:')) images.push(dataUrl);
            }
        }
        if (!images.length) {
            statusEl.innerHTML = '<span class="text-red-500 font-semibold">卡片渲染失败，请先用「导出」按钮检查是否正常。</span>';
            alert('卡片图片渲染失败，无法发布。');
            return;
        }

        // Step 2: 上传图片
        statusEl.textContent = `正在上传 ${images.length} 张图片...`;
        const uploadResp = await fetch('/api/upload_images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ images })
        });
        const uploadData = await uploadResp.json();
        if (uploadData.status !== 'ok') {
            statusEl.textContent = '上传失败：' + (uploadData.message || '未知错误');
            return;
        }

        // Step 3: 调用发布 API
        statusEl.textContent = isDraft ? '正在保存到草稿箱（私密笔记）...' : '正在发布到小红书...';
        const publishResp = await fetch('/xhs_api_publish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title.slice(0, 20),
                desc,
                cookie,
                image_token: uploadData.token,
                is_draft: isDraft || false,
                source: 'cards',
            })
        });
        const publishData = await publishResp.json();
        if (publishData.status !== 'ok') {
            statusEl.innerHTML = `<span class="text-red-500 font-semibold">${isDraft ? '保存草稿' : '发布'}失败：${publishData.message || '未知错误'}</span>`;
            alert((isDraft ? '保存草稿' : '发布') + '失败：' + (publishData.message || '未知错误'));
            return;
        }
        if (isDraft) {
            statusEl.innerHTML = '<span class="text-green-600 font-semibold">已保存为草稿！</span> <span class="text-gray-500">请前往小红书 App / 创作中心，找到该私密笔记，设置发布时间后公开发布。</span>';
            alert('已保存为草稿（私密笔记）！\n\n请前往小红书 App 或创作中心，找到该笔记，修改可见范围并设置发布时间后公开发布。');
        } else {
            statusEl.innerHTML = '<span class="text-green-600 font-semibold">发布成功！</span>';
            if (publishData.url) {
                window.open(publishData.url, '_blank');
                statusEl.innerHTML += ` <a href="${publishData.url}" target="_blank" class="text-blue-500 underline">查看笔记</a>`;
            }
            alert('发布成功！笔记已发布到小红书。' + (publishData.url ? '\n链接：' + publishData.url : ''));
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = `<span class="text-red-500 font-semibold">发布出错：${e}</span>`;
        alert('发布出错：' + e);
    }
}

// Modal 事件绑定（DOMContentLoaded 后执行）
document.addEventListener('DOMContentLoaded', function () {
    const nowR       = document.getElementById('xhsf-publish-now');
    const draftR     = document.getElementById('xhsf-publish-draft');
    const btnCancel  = document.getElementById('xhsf-publish-cancel');
    const btnConfirm = document.getElementById('xhsf-publish-confirm');
    const confirmLabel = document.getElementById('xhsf-confirm-label');

    // 切换确认按钮文案
    function updateConfirmLabel() {
        if (!confirmLabel) return;
        confirmLabel.textContent = (draftR && draftR.checked) ? '保存草稿' : '确认发布';
    }
    if (nowR)   nowR.addEventListener('change',   updateConfirmLabel);
    if (draftR) draftR.addEventListener('change', updateConfirmLabel);

    if (btnCancel) btnCancel.addEventListener('click', closeXhsFullPublishModal);

    if (btnConfirm) btnConfirm.addEventListener('click', async () => {
        const cookieEl = document.getElementById('xhsf-cookie-input');
        const cookie = (cookieEl ? cookieEl.value : '').trim();
        if (!cookie) { alert('请填写小红书 Cookie。'); cookieEl && cookieEl.focus(); return; }

        const isDraft = !!(draftR && draftR.checked);
        closeXhsFullPublishModal();
        await _doPublishToXhs(cookie, isDraft);
    });

    // 初始化 XHS 标题字数显示
    updateXhsTitleCount();
});

function toggleLayout() {
    isGridView = !isGridView;
    const canvas = document.getElementById('preview-canvas');
    const btn = document.getElementById('layout-btn');
    if (isGridView) {
        canvas.classList.remove('flex-col', 'items-center');
        canvas.classList.add('flex-row', 'flex-wrap', 'justify-center', 'items-start');
        canvas.style.width = `${100/currentZoom}%`;
        btn.innerHTML = `<i data-lucide="list" size="16"></i> <span>列表视图</span>`;
        btn.classList.add('text-blue-600');
    } else {
        canvas.classList.add('flex-col', 'items-center');
        canvas.classList.remove('flex-row', 'flex-wrap', 'justify-center', 'items-start');
        canvas.style.width = '100%';
        btn.innerHTML = `<i data-lucide="layout-grid" size="16"></i> <span>网格视图</span>`;
        btn.classList.remove('text-blue-600');
    }
    lucide.createIcons();
}

// 点击 Modal 背景关闭
document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('xhs-full-publish-modal')?.addEventListener('click', function(e) {
        if (e.target === this) closeXhsFullPublishModal();
    });
});
