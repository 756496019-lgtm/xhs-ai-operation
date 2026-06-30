"""小红书（XHS）图文笔记发布。"""

from typing import Dict, Any, List
from pathlib import Path

try:
    from xhs import XhsClient  # type: ignore
    from xhs.help import sign as local_sign  # type: ignore
    HAS_XHS = True
except Exception:
    HAS_XHS = False


def _parse_cookie(cookie_string: str) -> Dict[str, str]:
    """将 Cookie 字符串解析为字典。"""
    cookies: Dict[str, str] = {}
    for item in (cookie_string or "").split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        cookies[k.strip()] = v.strip()
    return cookies


def publish_to_xhs(cookie: str, title: str, desc: str, base_dir: Path, max_images: int = 9, post_time: str = None, is_draft: bool = False) -> Dict[str, Any]:
    """使用 xhs 库发布一条图文笔记。

    图片：自动从 base_dir 目录下挑选最近修改的 PNG/JPG 文件，最多 max_images 张。
    Cookie：由前端实时传入，避免长期存储。
    """
    if not HAS_XHS:
        raise RuntimeError("缺少 xhs 依赖，请先运行：pip install xhs python-dotenv requests")

    cookie = (cookie or "").strip()
    if not cookie:
        raise RuntimeError("Cookie 不能为空，请粘贴当前有效的小红书 Cookie。")

    def sign_func(uri, data=None, a1="", web_session=""):
        return local_sign(uri, data, a1=a1)

    client = XhsClient(cookie=cookie, sign=sign_func)

    import types, requests as _req

    # 修复1：SDK 的 get_upload_files_permit 默认取 uploadTempPermits[0]（qos=2，d4 CDN），
    # 而 upload_file 硬编码上传到 ros-upload.xiaohongshu.com（qos=1），导致 file_id/token 与
    # 上传地址不匹配。改为优先选 qos=1 的 permit，确保两者一致。
    def _patched_get_upload_files_permit(self, file_type: str, count: int = 1):
        uri = "/api/media/v1/upload/web/permit"
        params = {
            "biz_name": "spectrum", "scene": file_type,
            "file_count": count, "version": "1", "source": "web",
        }
        res = self.get(uri, params)
        permits = res["uploadTempPermits"]
        # 优先 qos=1（ros-upload.xiaohongshu.com），与下方 upload_file 的 URL 匹配
        permit = next((p for p in permits if p.get("qos") == 1), permits[0])
        return permit["fileIds"][0], permit["token"]

    client.get_upload_files_permit = types.MethodType(_patched_get_upload_files_permit, client)

    # 修复2：SDK 的 upload_file 通过 self.request() 发送 PUT，该方法可能重置
    # Content-Length（导致 invalid content-length）。改为直接用 requests.put() 绕开 SDK session。
    def _patched_upload_file(self, file_id: str, token: str, file_path: str,
                             content_type: str = "image/jpeg"):
        url = "https://ros-upload.xiaohongshu.com/" + file_id
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        resp = _req.put(
            url,
            data=file_bytes,
            headers={
                "X-Cos-Security-Token": token,
                "Content-Type": content_type,
                "Content-Length": str(len(file_bytes)),
            },
            timeout=60,
        )
        # COS 上传成功返回空 body（200），失败时返回 JSON 错误
        if not resp.ok:
            try:
                err = resp.json()
            except Exception:
                err = resp.text
            raise RuntimeError(f"COS 上传失败 HTTP {resp.status_code}: {err}")
        return {}

    client.upload_file = types.MethodType(_patched_upload_file, client)

    candidates: List[Path] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg"):
        candidates.extend(base_dir.glob(pattern))

    if not candidates:
        raise RuntimeError(f"在目录 {base_dir} 下没有找到任何 PNG/JPG 图片，请先在此目录导出卡片或截图。")

    # 图片顺序：按文件名数字升序（1.jpg, 2.jpg, 3.jpg）传给 xhs，
    # 与编辑器/上传顺序一致，小红书端按此顺序展示。
    candidates.sort(key=lambda p: int("".join(filter(str.isdigit, p.stem)) or "0"))
    image_paths = [str(p.resolve()) for p in candidates[:max_images]]

    if not image_paths:
        raise RuntimeError("没有可用的图片文件用于发布。")

    if len(title) > 20:
        title = title[:20]

    result = client.create_image_note(
        title=title,
        desc=desc,
        files=image_paths,
        is_private=is_draft,   # 草稿模式：保存为私密笔记，用户在 XHS App 中手动设置发布时间
        post_time=post_time or None,
    )
    return result
