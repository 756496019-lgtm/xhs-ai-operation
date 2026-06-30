// 当前上传的图片 token，发布时使用
let xhsUploadToken = null;
// 一键发布时暂存的标题和正文
let xhsPendingPublish = null;

// 将图片 base64 上传到服务器，自动保存到 xhs_uploads 目录
async function uploadCurrentImageToServer() {
  const img = document.getElementById('xhs-image');
  if (!img || !img.src || img.src.startsWith('blob:') || img.src === window.location.href) return null;
  let dataUrl = img.src;
  if (!dataUrl.startsWith('data:')) return null;
  try {
    const resp = await fetch('/api/upload_images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ images: [dataUrl] })
    });
    const data = await resp.json();
    if (data.status === 'ok' && data.token) {
      return data.token;
    }
  } catch (e) {
    console.warn('图片上传失败:', e);
  }
  return null;
}

// ==================== 更换图片 ====================
document.getElementById('image-upload').addEventListener('change', async function () {
  const file = this.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async function (e) {
    // Support both new template (#xhs-image exists) and old template (no img element)
    let img = document.getElementById('xhs-image');
    if (!img) {
      // Old template: find the image container and inject an <img> element
      const uploadInput = document.getElementById('image-upload');
      // Walk up to find the card's image container (bg-gray-900 div)
      const container = uploadInput
        ? uploadInput.closest('.card').querySelector('.bg-gray-900')
        : null;
      if (container) {
        img = document.createElement('img');
        img.id = 'xhs-image';
        img.className = 'max-h-full max-w-full object-contain';
        img.style.display = 'none';
        container.insertBefore(img, container.firstChild);
      }
    }

    // Find the placeholder by id or by searching for the image-off icon's container
    let placeholder = document.getElementById('xhs-image-placeholder');
    if (!placeholder) {
      const icon = document.querySelector('[data-lucide="image-off"]');
      if (icon) placeholder = icon.closest('div');
    }

    if (img) {
      img.src = e.target.result;
      // Remove Tailwind hidden class AND explicitly set display to ensure visibility
      img.classList.remove('hidden');
      img.style.display = 'block';
      // 自动上传到服务器保存到 xhs_uploads 目录，供发布使用
      xhsUploadToken = await uploadCurrentImageToServer();
    }
    if (placeholder) {
      placeholder.classList.add('hidden');
      placeholder.style.display = 'none';
    }
  };
  reader.readAsDataURL(file);
});

// ==================== 标题字数提醒 ====================
const XHS_TITLE_MAX = 20;
function updateTitleCount() {
  const input = document.getElementById('xhs-title');
  const countEl = document.getElementById('xhs-title-count');
  if (!input || !countEl) return;
  const len = (input.value || '').length;
  countEl.textContent = `${len}/${XHS_TITLE_MAX}`;
  if (len >= XHS_TITLE_MAX) {
    countEl.className = 'text-xs font-medium text-amber-600 shrink-0 w-11 text-right tabular-nums';
  } else if (len >= XHS_TITLE_MAX - 2) {
    countEl.className = 'text-xs font-medium text-amber-500 shrink-0 w-11 text-right tabular-nums';
  } else {
    countEl.className = 'text-xs font-medium text-gray-400 shrink-0 w-11 text-right tabular-nums';
  }
}
const xhsTitleEl = document.getElementById('xhs-title');
if (xhsTitleEl) {
  xhsTitleEl.addEventListener('input', updateTitleCount);
  xhsTitleEl.addEventListener('focus', updateTitleCount);
}
// 页面加载时：若标题为空且文案有内容，用首行填充标题
(function initTitleHint() {
  const textarea = document.getElementById('xhs-text');
  const titleInput = document.getElementById('xhs-title');
  if (textarea && titleInput && !titleInput.value.trim() && textarea.value.trim()) {
    const firstLine = textarea.value.trim().split('\n')[0].slice(0, XHS_TITLE_MAX);
    if (firstLine) titleInput.value = firstLine;
  }
  updateTitleCount();
})();

// ==================== 复制文案 ====================
document.getElementById('copy-xhs-text').addEventListener('click', async function () {
  const text = document.getElementById('xhs-text').value;
  try {
    await navigator.clipboard.writeText(text);
    alert('文案已复制到剪贴板。');
  } catch (e) {
    alert('复制失败，请手动全选后复制。');
  }
});

// ==================== 一键发布 ====================
function openXhsPublishModal() {
  const modal = document.getElementById('xhs-publish-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.style.display = 'flex';
}

function closeXhsPublishModal() {
  const modal = document.getElementById('xhs-publish-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.style.display = 'none';
}

async function performXhsPublish(postTime) {
  const status = document.getElementById('xhs-api-status');
  const pending = xhsPendingPublish;
  if (!pending) return;
  let { title, text } = pending;

  const cookie = window.prompt('请粘贴当前有效的小红书 Cookie：');
  if (!cookie) return;

  if (status) status.textContent = '正在发布到小红书，请稍候...';

  try {
    let imageToken = xhsUploadToken;
    if (!imageToken) {
      if (status) status.textContent = '正在上传图片...';
      imageToken = await uploadCurrentImageToServer();
    }
    const resp = await fetch('/xhs_api_publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, desc: text, cookie, image_token: imageToken || undefined, post_time: null })
    });
    const data = await resp.json();
    if (data.status !== 'ok') {
      if (status) status.innerHTML = `<span class="text-red-500 font-semibold">发布失败：${data.message || '未知错误'}</span>`;
      alert('发布失败：' + (data.message || '未知错误'));
      return;
    }
    if (status) {
      status.innerHTML = `<span class="text-green-600 font-semibold">发布成功！</span>`;
      if (data.url) status.innerHTML += ` <a href="${data.url}" target="_blank" class="text-blue-500 underline">查看笔记</a>`;
    }
    alert('发布成功！' + (data.url ? '\n链接：' + data.url : ''));
  } catch (e) {
    if (status) status.innerHTML = `<span class="text-red-500 font-semibold">请求失败：${e}</span>`;
    alert('发布出错：' + e);
  } finally {
    xhsPendingPublish = null;
  }
}

document.getElementById('btn-xhs-api-publish').addEventListener('click', function () {
  const text = document.getElementById('xhs-text').value.trim();
  let title = (document.getElementById('xhs-title')?.value || '').trim();
  if (!text) { alert('文案为空，请先编辑后再发布。'); return; }
  if (!title) { alert('请填写小红书帖子标题。'); document.getElementById('xhs-title')?.focus(); return; }
  if (title.length > XHS_TITLE_MAX) {
    alert(`标题不能超过 ${XHS_TITLE_MAX} 个字，当前 ${title.length} 字，请精简。`);
    document.getElementById('xhs-title')?.focus();
    return;
  }
  title = title.slice(0, XHS_TITLE_MAX);
  xhsPendingPublish = { title, text };
  openXhsPublishModal();
});

// 发布 Modal 事件绑定
(function initPublishModal() {
  const btnCancel = document.getElementById('xhs-publish-cancel');
  const btnConfirm = document.getElementById('xhs-publish-confirm');
  if (btnCancel) btnCancel.addEventListener('click', () => { xhsPendingPublish = null; closeXhsPublishModal(); });
  if (btnConfirm) btnConfirm.addEventListener('click', async () => { closeXhsPublishModal(); await performXhsPublish(null); });
})();

// ==================== 图片编辑器 ====================

let edCanvas = null;
let edCtx = null;
let edTool = 'crop';
let edBrushColor = '#FF0000';
let edBrushSize = 12;
let edMosaicBlock = 15;
let edIsDrawing = false;
let edCropStart = null;
let edCropEnd = null;
let edPreData = null;   // 裁剪框绘制前的 ImageData 快照
let edHistory = [];     // 撤销历史（data URL 数组）
let edLastPos = null;

// 将事件坐标转换为 canvas 实际像素坐标（处理 CSS 缩放）
function edGetPos(e) {
  const rect = edCanvas.getBoundingClientRect();
  const sx = edCanvas.width / rect.width;
  const sy = edCanvas.height / rect.height;
  const src = e.touches ? e.touches[0] : e;
  return {
    x: Math.round((src.clientX - rect.left) * sx),
    y: Math.round((src.clientY - rect.top) * sy)
  };
}

// 保存当前 canvas 到撤销历史
function edSaveHistory() {
  if (edHistory.length >= 20) edHistory.shift();
  edHistory.push(edCanvas.toDataURL('image/png'));
}

// 撤销
function edUndo() {
  if (!edHistory.length) return;
  const dataUrl = edHistory.pop();
  const img = new Image();
  img.onload = () => {
    edCanvas.width = img.naturalWidth;
    edCanvas.height = img.naturalHeight;
    edCtx.drawImage(img, 0, 0);
    edCropStart = edCropEnd = edPreData = null;
    document.getElementById('crop-confirm-btn').style.display = 'none';
  };
  img.src = dataUrl;
}

// 切换工具
function edSetTool(tool) {
  // 离开裁剪模式时，清除裁剪框
  if (edTool === 'crop' && tool !== 'crop' && edPreData) {
    edCtx.putImageData(edPreData, 0, 0);
    edCropStart = edCropEnd = edPreData = null;
    document.getElementById('crop-confirm-btn').style.display = 'none';
  }
  edTool = tool;

  ['crop', 'brush', 'mosaic'].forEach(t => {
    const btn = document.getElementById('tool-' + t);
    if (!btn) return;
    btn.style.background = t === tool ? '#6C5CE7' : 'transparent';
    btn.style.color = t === tool ? '#fff' : '#94a3b8';
  });

  const bs = document.getElementById('brush-settings');
  if (bs) bs.style.display = (tool === 'brush' || tool === 'mosaic') ? 'flex' : 'none';

  const cw = document.getElementById('brush-color-wrap');
  if (cw) cw.style.display = tool === 'brush' ? 'flex' : 'none';

  if (edCanvas) edCanvas.style.cursor = tool === 'crop' ? 'crosshair' : 'cell';
}

// 绘制裁剪遮罩 + 选择框
function edDrawCropOverlay() {
  if (!edPreData || !edCropStart || !edCropEnd) return;
  // 先恢复干净底图
  edCtx.putImageData(edPreData, 0, 0);

  const x = Math.min(edCropStart.x, edCropEnd.x);
  const y = Math.min(edCropStart.y, edCropEnd.y);
  const w = Math.abs(edCropEnd.x - edCropStart.x);
  const h = Math.abs(edCropEnd.y - edCropStart.y);

  // 半透明遮罩
  edCtx.fillStyle = 'rgba(0,0,0,0.55)';
  edCtx.fillRect(0, 0, edCanvas.width, edCanvas.height);

  // 选区还原（从快照取回）
  edCtx.putImageData(edPreData, 0, 0, x, y, w, h);

  // 虚线边框
  edCtx.strokeStyle = '#fff';
  edCtx.lineWidth = Math.max(1, edCanvas.width / 600);
  edCtx.setLineDash([8, 4]);
  edCtx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
  edCtx.setLineDash([]);

  // 四角手柄
  const hs = Math.max(6, Math.round(edCanvas.width / 150));
  edCtx.fillStyle = '#fff';
  [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].forEach(([hx, hy]) => {
    edCtx.fillRect(hx - hs / 2, hy - hs / 2, hs, hs);
  });
}

// 确认裁剪
function edConfirmCrop() {
  if (!edPreData || !edCropStart || !edCropEnd) return;
  const x = Math.min(edCropStart.x, edCropEnd.x);
  const y = Math.min(edCropStart.y, edCropEnd.y);
  const w = Math.abs(edCropEnd.x - edCropStart.x);
  const h = Math.abs(edCropEnd.y - edCropStart.y);
  if (w < 5 || h < 5) {
    edCtx.putImageData(edPreData, 0, 0);
    edCropStart = edCropEnd = edPreData = null;
    document.getElementById('crop-confirm-btn').style.display = 'none';
    return;
  }
  // 恢复干净底图后保存历史（裁剪前状态）
  edCtx.putImageData(edPreData, 0, 0);
  edSaveHistory();
  // 执行裁剪
  const croppedData = edCtx.getImageData(x, y, w, h);
  edCanvas.width = w;
  edCanvas.height = h;
  edCtx.putImageData(croppedData, 0, 0);
  edCropStart = edCropEnd = edPreData = null;
  document.getElementById('crop-confirm-btn').style.display = 'none';
}

// 马赛克：对光标周围区域按像素块取平均色填充
function edMosaic(cx, cy) {
  const block = edMosaicBlock;
  const radius = edBrushSize * 2;
  const startX = Math.max(0, Math.floor((cx - radius) / block) * block);
  const startY = Math.max(0, Math.floor((cy - radius) / block) * block);

  for (let bx = startX; bx < cx + radius; bx += block) {
    for (let by = startY; by < cy + radius; by += block) {
      const pw = Math.min(block, edCanvas.width - bx);
      const ph = Math.min(block, edCanvas.height - by);
      if (pw <= 0 || ph <= 0) continue;
      const px = edCtx.getImageData(bx, by, pw, ph).data;
      let rS = 0, gS = 0, bS = 0;
      const cnt = px.length / 4;
      for (let i = 0; i < px.length; i += 4) { rS += px[i]; gS += px[i + 1]; bS += px[i + 2]; }
      if (cnt > 0) {
        edCtx.fillStyle = `rgb(${Math.round(rS / cnt)},${Math.round(gS / cnt)},${Math.round(bS / cnt)})`;
        edCtx.fillRect(bx, by, pw, ph);
      }
    }
  }
}

// Mouse/Touch 事件处理
function edMouseDown(e) {
  e.preventDefault();
  edIsDrawing = true;
  const pos = edGetPos(e);
  edLastPos = pos;

  if (edTool === 'crop') {
    // 若上次拖拽未完成（遮罩层残留在 canvas 上），先恢复干净底图
    if (edPreData) edCtx.putImageData(edPreData, 0, 0);
    edPreData = edCtx.getImageData(0, 0, edCanvas.width, edCanvas.height);
    edCropStart = pos;
    edCropEnd = null;
    document.getElementById('crop-confirm-btn').style.display = 'none';
  } else if (edTool === 'brush') {
    edSaveHistory();
    edCtx.beginPath();
    edCtx.moveTo(pos.x, pos.y);
  } else if (edTool === 'mosaic') {
    edSaveHistory();
    edMosaic(pos.x, pos.y);
  }
}

function edMouseMove(e) {
  e.preventDefault();
  if (!edIsDrawing) return;
  const pos = edGetPos(e);

  if (edTool === 'crop') {
    edCropEnd = pos;
    edDrawCropOverlay();
  } else if (edTool === 'brush') {
    if (edLastPos) {
      edCtx.beginPath();
      edCtx.moveTo(edLastPos.x, edLastPos.y);
      edCtx.lineTo(pos.x, pos.y);
      edCtx.strokeStyle = edBrushColor;
      edCtx.lineWidth = edBrushSize;
      edCtx.lineCap = 'round';
      edCtx.lineJoin = 'round';
      edCtx.stroke();
    }
    edLastPos = pos;
  } else if (edTool === 'mosaic') {
    edMosaic(pos.x, pos.y);
    edLastPos = pos;
  }
}

function edMouseUp(e) {
  edIsDrawing = false;
  edLastPos = null;
  if (edTool === 'crop' && edCropStart && edCropEnd) {
    const w = Math.abs(edCropEnd.x - edCropStart.x);
    const h = Math.abs(edCropEnd.y - edCropStart.y);
    if (w > 10 && h > 10) {
      document.getElementById('crop-confirm-btn').style.display = 'block';
    }
  }
}

// 打开编辑器
function openEditor(src) {
  edCanvas = document.getElementById('editor-canvas');
  edCtx = edCanvas.getContext('2d', { willReadFrequently: true });
  edHistory = [];
  edCropStart = edCropEnd = edPreData = edLastPos = null;

  const modal = document.getElementById('img-editor-modal');
  modal.style.display = 'flex';

  const image = new Image();
  image.onload = () => {
    edCanvas.width = image.naturalWidth;
    edCanvas.height = image.naturalHeight;
    edCtx.drawImage(image, 0, 0);
  };
  image.src = src;
  edSetTool('crop');
}

// ---- 绑定编辑器 UI 事件 ----

document.getElementById('btn-edit-image').addEventListener('click', () => {
  const img = document.getElementById('xhs-image');
  if (!img || !img.src || img.src === window.location.href) {
    alert('当前没有可编辑的图片。');
    return;
  }
  openEditor(img.src);
});

document.getElementById('tool-crop').addEventListener('click', () => edSetTool('crop'));
document.getElementById('tool-brush').addEventListener('click', () => edSetTool('brush'));
document.getElementById('tool-mosaic').addEventListener('click', () => edSetTool('mosaic'));

document.getElementById('crop-confirm-btn').addEventListener('click', edConfirmCrop);
document.getElementById('editor-undo').addEventListener('click', edUndo);

document.getElementById('editor-apply').addEventListener('click', () => {
  // 裁剪模式：有有效选区则自动确认裁剪，否则仅清除遮罩恢复底图
  if (edTool === 'crop') {
    if (edCropStart && edCropEnd) {
      edConfirmCrop();
    } else if (edPreData) {
      edCtx.putImageData(edPreData, 0, 0);
      edCropStart = edCropEnd = edPreData = null;
      document.getElementById('crop-confirm-btn').style.display = 'none';
    }
  }
  const img = document.getElementById('xhs-image');
  if (img && edCanvas) {
    img.src = edCanvas.toDataURL('image/png');
    xhsUploadToken = null;  // 编辑后需重新上传
  }
  document.getElementById('img-editor-modal').style.display = 'none';
});

document.getElementById('editor-cancel').addEventListener('click', () => {
  document.getElementById('img-editor-modal').style.display = 'none';
});

document.getElementById('brush-color').addEventListener('input', function () {
  edBrushColor = this.value;
});

document.getElementById('brush-size').addEventListener('input', function () {
  edBrushSize = parseInt(this.value);
  document.getElementById('brush-size-label').textContent = this.value;
});

// ---- 绑定 Canvas 鼠标 / 触摸事件 ----
(function () {
  const canvas = document.getElementById('editor-canvas');
  if (!canvas) return;
  canvas.addEventListener('mousedown', edMouseDown);
  canvas.addEventListener('mousemove', edMouseMove);
  canvas.addEventListener('mouseup', edMouseUp);
  canvas.addEventListener('mouseleave', () => { edLastPos = null; });
  canvas.addEventListener('touchstart', edMouseDown, { passive: false });
  canvas.addEventListener('touchmove', edMouseMove, { passive: false });
  canvas.addEventListener('touchend', edMouseUp);

  // 鼠标在 canvas 外松开时同样触发确认逻辑，避免"无反应"
  document.addEventListener('mouseup', (e) => {
    if (edIsDrawing) edMouseUp(e);
  });
})();
