"""
QwenPaw 代码编辑器插件 v0.1.2
在线代码编辑：浏览/打开/编辑/新建/保存工作区文本与代码文件。
基于 Monaco Editor（VSCode 同款编辑器核心，CDN 加载，前端无构建）。

访问范围（安全默认）：
  - 工作区模式（默认）：仅允许 WORKING_DIR 内路径。
  - 平台模式（WORKING_DIR 位于 /run/csi/mount-root/nas 之下自动判定）：
    允许访问所有可访问路径（遵循系统权限），与 file-browser 一致；
    access_root 仍指向 NAS 持久层根，作为默认文件树根。
  - 越界路径返回 403（工作区模式）。

接口（挂载于 /api/qwenpaw-code-editor/）：
  - GET  /status            插件状态、版本、WORKING_DIR、当前模式、快捷根目录列表
  - GET  /ls?path=          列出目录（path 支持绝对路径或相对 WORKING_DIR；空 = WORKING_DIR）
  - GET  /read?path=        读取文本文件内容（二进制/超大文件安全拦截；默认上限 2MB）
  - POST /write             保存文件 {path, content}（UTF-8；自动创建父目录；拒绝覆盖目录）
"""
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PLUGIN_VERSION = "0.1.2"

# 编辑器适合打开的文件大小上限（默认 2MB，超出提示用文件浏览器下载）
MAX_READ_BYTES = 2 * 1024 * 1024

# 二进制检测：读取头部若干字节，含 NUL 即视为二进制
_BIN_PROBE = 8192

router = APIRouter()

# ---------- 路径与访问控制 ----------

def _platform_root() -> Path:
    """平台 NAS 持久层根（WORKING_DIR 挂载点之上）。"""
    return Path("/run/csi/mount-root/nas").resolve()

def _working_dir() -> Path:
    """运行时数据根目录（与 QwenPaw / file-browser 一致：优先 QWENPAW_WORKING_DIR）。"""
    wd = os.environ.get("QWENPAW_WORKING_DIR") or os.environ.get("WORKING_DIR") or ""
    if wd and os.path.isdir(wd):
        return Path(wd).resolve()
    return Path.cwd().resolve()

def _is_platform_env() -> bool:
    """WORKING_DIR 位于 /run/csi/mount-root/nas 下即判定为平台环境。"""
    wd = _working_dir()
    try:
        wd.relative_to(_platform_root())
        return True
    except ValueError:
        return False

def _mode() -> str:
    return "platform" if _is_platform_env() else "workdir"

def _access_root() -> Path:
    """当前模式允许访问的根（仅用于 status 展示 / 前端默认树根）。

    - 平台模式：默认树根为 NAS 持久层根，但访问不限（遵循系统权限）
    - 工作区模式：仅允许 WORKING_DIR
    """
    return _platform_root() if _is_platform_env() else _working_dir()

def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = _working_dir() / p
    p = p.resolve()
    if _is_platform_env():
        # 平台模式：允许访问所有可访问路径（遵循系统权限），与 file-browser 一致
        return p
    try:
        p.relative_to(_working_dir().resolve())
    except ValueError:
        raise HTTPException(403, "路径超出访问范围（当前模式：workdir）")
    return p

# ---------- 工具 ----------

def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    units = ["KB", "MB", "GB", "TB"]
    v = float(n)
    for u in units:
        v /= 1024.0
        if v < 1024:
            return f"{v:.1f} {u}"
    return f"{v:.1f} PB"

def _looks_binary(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            chunk = f.read(_BIN_PROBE)
    except OSError:
        return False
    return b"\x00" in chunk

def _sorted_items(p: Path) -> list:
    """目录项：目录在前、名称自然排序。"""
    items = []
    try:
        entries = list(p.iterdir())
    except OSError as e:
        raise HTTPException(500, f"读取目录失败：{e}")
    for e in entries:
        try:
            st = e.stat()
        except OSError:
            continue
        items.append({
            "name": e.name,
            "path": str(e),
            "type": "dir" if e.is_dir() else "file",
            "size": st.st_size,
            "mtime": int(st.st_mtime),
        })
    items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
    return items


def _agent_workspace_dirs(wd: Path) -> list:
    """扫描各智能体工作区目录（兼容两种部署布局）。

    布局A：WORKING_DIR 自身即某个智能体工作区（<...>/workspaces/<agent_id>）
           → 扫描父级 workspaces/（结果含 WORKING_DIR 自身）
    布局B：WORKING_DIR 为平台根（<...>）→ 扫描其下 workspaces/ 子目录
    """
    if wd.parent.name == "workspaces" and wd.parent.is_dir():
        agent_root = wd.parent
    else:
        ws = wd / "workspaces"
        if not ws.is_dir():
            return []
        agent_root = ws
    try:
        return sorted(
            (c for c in agent_root.iterdir()
             if c.is_dir() and not c.name.startswith(".")),
            key=lambda c: c.name,
        )
    except OSError:
        return []


def _roots() -> list:
    """快捷根目录列表（与 file-browser 一致）：WORKING_DIR、系统路径、各智能体工作区、NAS 根。"""
    wd = _working_dir().resolve()
    if not _is_platform_env():
        out = [{"path": str(wd), "label": "WORKING_DIR"}]
        for d in _agent_workspace_dirs(wd):
            try:
                rr = d.resolve()
                rr.relative_to(wd)
            except (OSError, ValueError):
                continue
            if rr == wd:
                continue
            out.append({"path": str(rr), "label": "🤖 " + rr.name + "（工作区）"})
        return out

    roots = [wd, Path("/tmp"), Path("/home"), Path("/root"), Path("/workspace")]
    roots.extend(_agent_workspace_dirs(wd))
    nas = Path("/run/csi/mount-root/nas")
    if nas.is_dir():
        roots.append(nas)
    roots.append(Path("/app"))
    roots.append(Path("/"))
    agent_paths = set()
    for d in _agent_workspace_dirs(wd):
        try:
            agent_paths.add(d.resolve())
        except OSError:
            pass
    seen = set()
    out = []
    for r in roots:
        try:
            rr = r.resolve()
        except OSError:
            continue
        if rr in seen or not rr.exists():
            continue
        seen.add(rr)
        if rr == wd:
            label = "WORKING_DIR"
        elif rr == Path("/").resolve():
            label = "/ (文件系统根)"
        elif rr in agent_paths:
            label = "🤖 " + rr.name + "（工作区）"
        else:
            label = str(rr)
        out.append({"path": str(rr), "label": label})
    return out

# ---------- 数据模型 ----------

class WriteReq(BaseModel):
    path: str
    content: str

# ---------- 接口 ----------

@router.get("/status")
async def status():
    wd = _working_dir()
    return {
        "id": "qwenpaw-code-editor",
        "name": "代码编辑器",
        "version": PLUGIN_VERSION,
        "working_dir": str(wd),
        "mode": _mode(),
        "access_root": str(_access_root()),
        "roots": _roots(),
    }

@router.get("/ls")
async def ls(path: str = Query("", description="目录路径（绝对或相对 WORKING_DIR；空 = WORKING_DIR）")):
    p = _resolve(path)
    if not p.exists():
        raise HTTPException(404, "路径不存在")
    if not p.is_dir():
        raise HTTPException(400, "不是目录")
    return {"path": str(p), "items": _sorted_items(p)}

@router.get("/read")
async def read_file(path: str = Query("", description="文件路径（绝对或相对 WORKING_DIR）")):
    p = _resolve(path)
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    if p.is_dir():
        raise HTTPException(400, "是目录，不是文件")
    size = p.stat().st_size
    if size > MAX_READ_BYTES:
        raise HTTPException(
            413,
            f"文件过大（{_fmt_size(size)}，上限 {_fmt_size(MAX_READ_BYTES)}），请在文件浏览器中下载查看",
        )
    if _looks_binary(p):
        raise HTTPException(415, "二进制文件不支持编辑，请在文件浏览器中下载")
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "非 UTF-8 文本文件暂不支持编辑")
    except OSError as e:
        raise HTTPException(500, f"读取失败：{e}")
    return {"path": str(p), "size": size, "content": content}

@router.post("/write")
async def write_file(req: WriteReq):
    p = _resolve(req.path)
    if p.exists() and p.is_dir():
        raise HTTPException(400, "目标路径是目录，不能写入")
    # 自动创建父目录（新建文件场景）
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(req.content, encoding="utf-8")
    except OSError as e:
        raise HTTPException(500, f"保存失败：{e}")
    return {"path": str(p), "bytes": p.stat().st_size}

# ---------- 插件注册 ----------

class CodeEditorPlugin:
    """代码编辑器插件"""

    def __init__(self):
        self.name = "代码编辑器"
        self.version = PLUGIN_VERSION
        self.id = "qwenpaw-code-editor"
        self.router = router

    def register(self, api) -> None:
        if hasattr(api, "register_http_router"):
            api.register_http_router(
                self.router,
                prefix="/qwenpaw-code-editor",
                tags=["qwenpaw-code-editor"],
            )
            logger.info("[qwenpaw-code-editor] HTTP router registered at /api/qwenpaw-code-editor")

        if hasattr(api, "register_startup_hook"):
            api.register_startup_hook("qwenpaw_code_editor_startup", self._startup)

        if hasattr(api, "register_shutdown_hook"):
            api.register_shutdown_hook("qwenpaw_code_editor_shutdown", self._shutdown)

    async def _startup(self) -> None:
        logger.info(
            "[qwenpaw-code-editor] Plugin v%s started - workdir=%s mode=%s",
            PLUGIN_VERSION,
            _working_dir().resolve(),
            _mode(),
        )

    async def _shutdown(self) -> None:
        logger.info("[qwenpaw-code-editor] Plugin stopped")

# REQUIRED: 模块级 plugin 实例
plugin = CodeEditorPlugin()

