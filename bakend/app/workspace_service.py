"""Server filesystem operations with persisted, single-use user confirmations.

Proposals do not mutate disk. Confirmation is deliberately separate from model
tools. Trash metadata and audit records live in SQLite, never in a Git checkpoint.
"""
from __future__ import annotations

import base64
import fnmatch
import heapq
import getpass
import json
import os
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .workspace_models import Workspace, WorkspaceCreate, WorkspaceUpdate, FileOperationRequest
from .workspace_paths import WorkspacePaths, within
from . import workspace_io as secure_io


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path: Path):
    try:
        s = path.lstat()
        return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_mode]
    except FileNotFoundError:
        return None


class WorkspaceService:
    def __init__(self, store, default_root: Path):
        self.store = store
        self.paths = WorkspacePaths(default_root)
        if not self.paths.default.exists() and not os.getenv("WORKSPACE_DEFAULT_ROOT"):
            self.paths.resolve(self.paths.default, ".", write=True).mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.run_lock = threading.RLock()
        self.protected_paths = lambda: [Path(store.database_path)]
        with store._lock, store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspace_operations (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, status TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspace_trash (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspace_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspace_tool_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, turn_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_workspace_tool_turn ON workspace_tool_events(turn_id, id);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
            if "workspace_id" not in columns:
                db.execute("ALTER TABLE conversations ADD COLUMN workspace_id TEXT")

    def get(self, workspace_id: str, *, active: bool = True) -> Workspace:
        with self.store._connect() as db:
            row = db.execute("SELECT payload FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if not row:
            raise KeyError("工作区不存在")
        result = Workspace.model_validate_json(row[0])
        if active and result.status != "active":
            raise ValueError("工作区已归档或移除，请先恢复工作区记录")
        return result

    def list(self) -> list[Workspace]:
        with self.store._connect() as db:
            rows = db.execute("SELECT payload FROM workspaces ORDER BY id DESC").fetchall()
        return [Workspace.model_validate_json(row[0]) for row in rows
                if json.loads(row[0])["status"] != "deleted"]

    def _save(self, record: Workspace):
        with self.store._lock, self.store._connect() as db:
            db.execute("INSERT INTO workspaces VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                       (record.id, record.model_dump_json()))
        return record

    def create(self, request: WorkspaceCreate) -> Workspace:
        root = self.paths.browse_root(request.root_path)
        if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
            raise ValueError("请选择后端账户可读取的已有服务器目录")
        return self._save(Workspace(id=f"ws_{uuid4().hex}", name=request.name.strip(), root_path=str(root),
                                    description=request.description, created_at=now(), updated_at=now()))

    def update(self, workspace_id: str, request: WorkspaceUpdate):
        record = self.get(workspace_id, active=False)
        changes = request.model_dump(exclude_none=True)
        return self._save(record.model_copy(update={**changes, "updated_at": now()}))

    def remove(self, workspace_id: str):
        record = self.get(workspace_id, active=False)
        self._save(record.model_copy(update={"status": "deleted", "updated_at": now()}))
        return {"removed": True, "disk_preserved": True, "root_path": record.root_path}

    def bind_conversation(self, conversation_id: str, workspace_id: str | None):
        if workspace_id:
            self.get(workspace_id)
        with self.store._lock, self.store._connect() as db:
            if db.execute("UPDATE conversations SET workspace_id=?, updated_at=? WHERE conversation_id=?",
                          (workspace_id, now(), conversation_id)).rowcount != 1:
                raise KeyError("对话不存在")

    def root(self, workspace_id: str | None = None, root_path: str | None = None):
        if workspace_id:
            stored = Path(self.get(workspace_id).root_path)
            resolved = self.paths.browse_root(str(stored))
            if stored != resolved:
                raise PermissionError("工作区根目录被重定向，请重新检查并登记")
            return resolved
        return self.paths.browse_root(root_path)

    def inspect(self, path=".", workspace_id=None, root_path=None, *, sensitive=False):
        root = self.root(workspace_id, root_path)
        target = self.paths.resolve(root, path, sensitive=sensitive)
        result = {"name": target.name, "path": str(target), "relative_path": str(target.relative_to(root)),
                  "exists": target.exists()}
        if target.exists():
            with secure_io.directory_fd(target.parent) as parent:
                info = os.fstat(parent) if parent is not None and not target.name else os.stat(
                    target if parent is None else target.name, dir_fd=parent, follow_symlinks=False)
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise PermissionError("路径已变化或不是普通文件/目录")
            result.update(type="directory" if stat.S_ISDIR(info.st_mode) else "file", size=info.st_size,
                          modified_at=datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                          permissions=stat.filemode(info.st_mode), readable=os.access(target, os.R_OK),
                          writable=os.access(target, os.W_OK), symlink=(root / path).is_symlink())
        return result

    def list_directory(self, path=".", workspace_id=None, root_path=None, cursor=None, limit=None,
                       sort="name", filter="", show_hidden=False):
        root = self.root(workspace_id, root_path)
        directory = self.paths.resolve(root, path)
        if not directory.is_dir():
            raise ValueError("路径不是目录")
        limit = max(1, min(limit or self.paths.page_size, 200))
        if sort not in {"name", "modified", "size"}:
            raise ValueError("不支持的排序")
        stamp = fingerprint(directory)
        context = [str(directory), sort, filter, show_hidden, stamp]
        after = None
        if cursor:
            try:
                payload = json.loads(base64.urlsafe_b64decode(cursor))
                if payload["context"] != context:
                    raise ValueError("目录或筛选条件已变化，请刷新")
                after = tuple(payload["after"])
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("分页游标已失效，请刷新") from exc

        def entries():
            # Only this layer is enumerated. nsmallest bounds retained entries to
            # one page instead of materializing/sorting an enormous directory.
            with os.scandir(directory) as items:
                for item in items:
                    if (not show_hidden and item.name.startswith(".")) or filter.casefold() not in item.name.casefold():
                        continue
                    try:
                        target = self.paths.resolve(root, item.path)
                        info = target.stat()
                        folder = stat.S_ISDIR(info.st_mode)
                        primary = -info.st_mtime_ns if sort == "modified" else -info.st_size if sort == "size" else item.name.casefold()
                        key = (0 if folder else 1, primary, item.name)
                        if after is None or key > after:
                            yield key, item.name
                    except (OSError, ValueError):
                        continue
        page = heapq.nsmallest(limit + 1, entries())
        more = len(page) > limit
        page = page[:limit]
        rows = []
        for _, name in page:
            try:
                rows.append(self.inspect(str(directory / name), workspace_id, root_path))
            except OSError:
                continue
        token = base64.urlsafe_b64encode(json.dumps({"context": context, "after": page[-1][0]}).encode()).decode() if more else None
        return {"root_path": str(root), "path": str(directory), "relative_path": str(directory.relative_to(root)),
                "items": rows, "has_more": more, "next_cursor": token, "limit": limit}

    def read_text(self, path, workspace_id=None, root_path=None, offset=0, max_chars=None, *, sensitive=False):
        root = self.root(workspace_id, root_path)
        target = self.paths.resolve(root, path, sensitive=sensitive)
        name = target.name.lower()
        if any(name.endswith(ext) for ext in (".nii", ".nii.gz", ".mgz", ".mgh", ".mif", ".mih", ".dcm", ".ima", ".h5", ".hdf5", ".gz", ".zip", ".npy", ".npz")):
            raise ValueError("影像或二进制文件仅可查看元数据；请交给对应 Skill/Runner 分析")
        if not target.is_file():
            raise ValueError("只能读取普通文本文件")
        if offset < 0 or offset > 2_000_000:
            raise ValueError("文本 offset 必须在 0–2000000 字符之间")
        count = max(1, min(max_chars or self.paths.text_max, self.paths.text_max))
        # Bounded prefix inspection before decoding. Never open FIFOs/devices.
        fd = secure_io.open_read(target)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("不是普通文本文件")
            prefix = os.read(fd, 8192)
            if b"\x00" in prefix or (len(prefix) > 132 and prefix[128:132] == b"DICM") or any(b < 9 or 13 < b < 32 for b in prefix):
                raise ValueError("检测到二进制内容，不能作为文本返回")
            os.lseek(fd, 0, os.SEEK_SET)
            with os.fdopen(fd, "r", encoding="utf-8-sig", errors="strict") as stream:
                fd = -1
                stream.read(offset)
                value = stream.read(count + 1)
                if any(ord(char) < 9 or 13 < ord(char) < 32 for char in value):
                    raise ValueError("请求区间包含二进制控制字符，不能作为文本返回")
        except UnicodeError as exc:
            raise ValueError("文件不是可识别的 UTF-8 文本") from exc
        finally:
            if fd >= 0:
                os.close(fd)
        return {"path": str(target), "offset": offset, "text": value[:count], "truncated": len(value) > count,
                "next_offset": offset + min(len(value), count), "max_chars": count}

    def search(self, path=".", workspace_id=None, root_path=None, pattern="*", max_depth=2, max_results=100):
        root = self.root(workspace_id, root_path)
        start = self.paths.resolve(root, path)
        if not start.is_dir():
            raise ValueError("搜索起点必须是目录")
        if not 0 <= max_depth <= 5 or not 1 <= max_results <= 200:
            raise ValueError("搜索深度限制 0–5，结果数限制 1–200")
        stack = [(start, 0)]
        results, scanned, reason = [], 0, None
        deadline = time.monotonic() + 5
        while stack and reason is None:
            directory, depth = stack.pop()
            try:
                with os.scandir(directory) as entries:
                    for item in entries:
                        scanned += 1
                        if scanned > 20000 or time.monotonic() > deadline:
                            reason = "扫描数量或时间上限"
                            break
                        if item.name.startswith(".") or item.is_symlink():
                            continue
                        try:
                            target = self.paths.resolve(root, item.path)
                            if fnmatch.fnmatch(item.name.casefold(), pattern.casefold()):
                                results.append(self.inspect(str(target), workspace_id, root_path))
                                if len(results) >= max_results:
                                    reason = "结果数量上限"
                                    break
                            if depth < max_depth and target.is_dir():
                                stack.append((target, depth + 1))
                        except OSError:
                            continue
            except PermissionError:
                continue
        return {"items": results, "scanned": scanned, "max_depth": max_depth, "truncated": reason is not None,
                "stop_reason": reason}

    def _protect(self, *paths: Path):
        for candidate in paths:
            for protected in self.protected_paths():
                protected = Path(protected).resolve()
                if within(candidate, protected) or within(protected, candidate):
                    raise PermissionError(f"路径正被后台任务或平台存储使用，不能修改：{candidate}")

    def _trash_root(self, workspace_id):
        root = self.root(workspace_id)
        configured = Path(self.paths.trash_name)
        target = configured / workspace_id if configured.is_absolute() else root / configured
        allowed = next((p for p in self.paths.roots if within(target.resolve(), p)), None)
        if allowed is None:
            raise PermissionError("回收站不在允许访问的根目录内")
        return self.paths.resolve(allowed, str(target), write=True, internal=True)

    def _operation_paths(self, action, request):
        root = self.root(request.workspace_id)
        source = self.paths.resolve(root, request.path, write=True, sensitive=action == "read-sensitive")
        target = self.paths.resolve(root, request.destination, write=True) if request.destination else None
        if action == "rename":
            if not request.destination or Path(request.destination).name != request.destination or request.destination in {".", ".."}:
                raise ValueError("重命名只接受新名称，不能包含目录")
            target = self.paths.resolve(root, str(source.parent / request.destination), write=True)
        if action == "delete" and not request.permanent:
            target = self._trash_root(request.workspace_id) / uuid4().hex / source.name
        if source == root or target == root:
            raise PermissionError("不能修改工作区根目录本身")
        if action in {"copy", "move", "rename"} and target is None:
            raise ValueError("必须指定准确的目标路径（含文件或文件夹名称）")
        if target and (within(target, source) or within(source, target)):
            raise ValueError("源路径和目标路径不能相同或互相包含")
        if action == "mkdir":
            if source.exists():
                raise ValueError("目标已存在")
            if not source.parent.is_dir():
                raise ValueError("请先创建父目录")
        elif not source.exists():
            raise FileNotFoundError("源路径不存在")
        if action not in {"read-sensitive", "copy"}:
            self._protect(source)
        if target:
            self._protect(target)
            if action != "delete" and not target.parent.is_dir():
                raise ValueError("目标父目录不存在")
            if target.exists() and not request.overwrite:
                raise ValueError("目标已存在；覆盖必须另行明确确认")
        return source, target

    def propose(self, action: str, request: FileOperationRequest):
        if action not in {"mkdir", "copy", "move", "rename", "delete", "read-sensitive"}:
            raise ValueError("不支持的文件操作")
        if request.permanent and action != "delete":
            raise ValueError("permanent 仅适用于删除")
        if request.conversation_id:
            conversation = self.store.get_conversation(request.conversation_id)
            if not conversation or conversation.workspace_id != request.workspace_id:
                raise ValueError("操作工作区与当前对话不匹配")
        source, target = self._operation_paths(action, request)
        operation = {"id": uuid4().hex, "workspace_id": request.workspace_id, "action": action,
                     "source": str(source), "target": str(target) if target else None,
                     "conversation_id": request.conversation_id, "request": request.model_dump(),
                     "source_fingerprint": fingerprint(source), "target_fingerprint": fingerprint(target) if target else None,
                     "root_fingerprint": fingerprint(self.root(request.workspace_id))[:2],
                     "created_at": now(), "expires_at": time.time() + 600, "status": "pending", "confirmed": False}
        with self.store._lock, self.store._connect() as db:
            db.execute("INSERT INTO workspace_operations VALUES(?,?,?,?,?)",
                       (operation["id"], request.workspace_id, "pending", json.dumps(operation), now()))
        self._audit(operation, "awaiting_confirmation")
        return operation

    def operation(self, operation_id):
        with self.store._connect() as db:
            row = db.execute("SELECT payload,status FROM workspace_operations WHERE id=?", (operation_id,)).fetchone()
        if not row:
            raise KeyError("操作不存在")
        return {**json.loads(row[0]), "status": row[1]}

    def _audit(self, operation, result, error=None):
        entry = {key: operation.get(key) for key in ("id", "workspace_id", "conversation_id", "action", "source", "target", "confirmed")}
        entry.update(actor=f"backend-account:{getpass.getuser()}", time=now(), result=result, error=error)
        with self.store._lock, self.store._connect() as db:
            db.execute("INSERT INTO workspace_audit(payload) VALUES(?)", (json.dumps(entry),))

    def _trash(self, workspace_id, source, target=None, conversation_id=None):
        trash_id = uuid4().hex
        target = target or self._trash_root(workspace_id) / trash_id / source.name
        secure_io.mkdir(target.parent, parents=True, exist_ok=False)
        record = {"id": trash_id, "workspace_id": workspace_id, "original_path": str(source),
                  "trash_path": str(target), "deleted_at": now(), "conversation_id": conversation_id, "status": "prepared"}
        # Persist before moving: an interrupted process leaves a recoverable record.
        with self.store._lock, self.store._connect() as db:
            db.execute("INSERT INTO workspace_trash VALUES(?,?,?)", (trash_id, workspace_id, json.dumps(record)))
        try:
            secure_io.rename(source, target)
        except OSError:
            # Refuse cross-filesystem moves rather than risking a partial deletion.
            raise ValueError("移动至回收站失败；回收站需与源文件在同一文件系统，源文件保留")
        record["status"] = "deleted"
        with self.store._lock, self.store._connect() as db:
            db.execute("UPDATE workspace_trash SET payload=? WHERE id=?", (json.dumps(record), trash_id))
        return record

    def _validate_tree(self, path: Path):
        budget = 100000
        stack = [path]
        while stack:
            entry = stack.pop()
            budget -= 1
            if budget < 0:
                raise ValueError("目录超过 100000 项，请分批操作")
            if entry.is_symlink() or self.paths.sensitive(entry) or self.paths.special(entry):
                raise PermissionError("目录含符号链接、敏感或特殊内容，拒绝操作")
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(entry) as items:
                    stack.extend(Path(item.path) for item in items)
            elif not stat.S_ISREG(info.st_mode):
                raise PermissionError("目录含特殊文件，拒绝操作")

    def confirm(self, operation_id, conversation_id=None):
        with self.lock:
            operation = self.operation(operation_id)
            if operation["conversation_id"] != conversation_id:
                raise PermissionError("确认会话与操作会话不匹配")
            if operation["status"] != "pending" or operation["expires_at"] < time.time():
                raise ValueError("操作已执行、过期或正在执行；请重新检查路径")
            # Reserve the paths atomically against new Runner submissions, but
            # never hold the Runner lock during a large copy or directory walk.
            with self.run_lock:
                self._protect(Path(operation["source"])) if operation["action"] not in {"copy", "read-sensitive"} else None
                if operation.get("target"):
                    self._protect(Path(operation["target"]))
                with self.store._lock, self.store._connect() as db:
                    if db.execute("UPDATE workspace_operations SET status='running' WHERE id=? AND status='pending'", (operation_id,)).rowcount != 1:
                        raise ValueError("此操作已被确认")
            operation["confirmed"] = True
            self._audit(operation, "started")
            try:
                result = self._execute(operation)
                operation.update(status="succeeded", result=result)
            except Exception as exc:
                operation.update(status="failed", error=str(exc))
                self._audit(operation, "failed", str(exc))
            else:
                self._audit(operation, "succeeded")
            with self.store._lock, self.store._connect() as db:
                persisted = operation
                if operation["action"] == "read-sensitive" and operation.get("result"):
                    # A sensitive preview is returned once to the confirming UI,
                    # never retained in history, audit, or operation JSON.
                    persisted = {**operation, "result": {k: v for k, v in operation["result"].items() if k != "text"}}
                db.execute("UPDATE workspace_operations SET status=?,payload=? WHERE id=?",
                           (operation["status"], json.dumps(persisted), operation_id))
            return operation

    def _execute(self, operation):
        action = operation["action"]
        request = FileOperationRequest.model_validate(operation["request"])
        root = self.root(request.workspace_id)
        if fingerprint(root)[:2] != operation["root_fingerprint"]:
            raise ValueError("工作区目录已被替换，请重新确认")
        if action == "restore":
            return self._restore(operation)
        source, target = self._operation_paths(action, request)
        # Delete's generated destination is frozen at proposal time.
        if action == "delete" and not request.permanent:
            target = Path(operation["target"])
            self.paths.resolve(self._trash_root(request.workspace_id), str(target), write=True, internal=True)
        if fingerprint(source) != operation["source_fingerprint"] or (fingerprint(target) if target else None) != operation["target_fingerprint"]:
            raise ValueError("源或目标自预览后已变化，请重新确认")
        if action == "read-sensitive":
            return self.read_text(str(source), request.workspace_id, sensitive=True)
        if action == "mkdir":
            secure_io.mkdir(source)
        else:
            self._validate_tree(source)
            backup = None
            staging = None
            if action == "copy":
                staging = target.with_name(".neuroweave-copy-" + uuid4().hex)
                operation["staging_path"] = str(staging)
                with self.store._lock, self.store._connect() as db:
                    db.execute("UPDATE workspace_operations SET payload=? WHERE id=?", (json.dumps(operation), operation["id"]))
                secure_io.copy(source, staging, self.paths)
                self._validate_tree(staging)
                # A failed or interrupted copy keeps its staging path in the
                # audit operation. The visible target remains untouched until
                # the full copy is ready for a no-replace atomic rename.
                if fingerprint(target) != operation["target_fingerprint"]:
                    raise ValueError("复制过程中目标发生变化，已保留临时副本，未替换目标")
            if target and target.exists():
                self._validate_tree(target)
                backup = self._trash(request.workspace_id, target, conversation_id=request.conversation_id)
            if action == "copy":
                secure_io.rename(staging, target)
            elif action in {"move", "rename"}:
                secure_io.rename(source, target)
            elif action == "delete":
                if request.permanent:
                    secure_io.remove(source)
                else:
                    return self._trash(request.workspace_id, source, target, request.conversation_id)
            return {"source": str(source), "target": str(target) if target else None, "overwritten_backup": backup}
        return {"path": str(source)}

    def trash(self, workspace_id):
        self.get(workspace_id, active=False)
        with self.store._connect() as db:
            rows = db.execute("SELECT payload FROM workspace_trash WHERE workspace_id=? ORDER BY rowid DESC LIMIT 500", (workspace_id,)).fetchall()
        return [json.loads(row[0]) for row in rows if json.loads(row[0])["status"] != "restored"]

    def propose_restore(self, trash_id, conversation_id=None, destination=None):
        with self.store._connect() as db:
            row = db.execute("SELECT payload FROM workspace_trash WHERE id=?", (trash_id,)).fetchone()
        if not row:
            raise KeyError("回收站记录不存在")
        record = json.loads(row[0])
        workspace_id = record["workspace_id"]
        source = self.paths.resolve(self._trash_root(workspace_id), record["trash_path"], write=True, internal=True)
        target = self.paths.resolve(self.root(workspace_id), destination or record["original_path"], write=True)
        self._protect(target)
        if not source.exists() or target.exists() or not target.parent.is_dir():
            raise ValueError("回收站内容不存在、原位置被占用或父目录不存在；请选择新的目标路径")
        request = FileOperationRequest(workspace_id=workspace_id, path=str(target), conversation_id=conversation_id)
        operation = {"id": uuid4().hex, "workspace_id": workspace_id, "action": "restore", "source": str(source),
                     "target": str(target), "trash_id": trash_id, "conversation_id": conversation_id,
                     "request": request.model_dump(), "source_fingerprint": fingerprint(source), "target_fingerprint": None,
                     "root_fingerprint": fingerprint(self.root(workspace_id))[:2], "created_at": now(),
                     "expires_at": time.time() + 600, "status": "pending", "confirmed": False}
        with self.store._lock, self.store._connect() as db:
            db.execute("INSERT INTO workspace_operations VALUES(?,?,?,?,?)", (operation["id"], workspace_id, "pending", json.dumps(operation), now()))
        self._audit(operation, "awaiting_confirmation")
        return operation

    def _restore(self, operation):
        workspace_id = operation["workspace_id"]
        source = self.paths.resolve(self._trash_root(workspace_id), operation["source"], write=True, internal=True)
        target = self.paths.resolve(self.root(workspace_id), operation["target"], write=True)
        self._protect(target)
        if fingerprint(source) != operation["source_fingerprint"] or target.exists():
            raise ValueError("恢复路径已变化，请重新确认")
        secure_io.rename(source, target)
        with self.store._lock, self.store._connect() as db:
            row = db.execute("SELECT payload FROM workspace_trash WHERE id=?", (operation["trash_id"],)).fetchone()
            record = json.loads(row[0])
            record.update(status="restored", restored_at=now(), restored_path=str(target))
            db.execute("UPDATE workspace_trash SET payload=? WHERE id=?", (json.dumps(record), record["id"]))
        return {"restored_path": str(target)}

    def event(self, turn_id, payload):
        payload = {**payload, "time": now()}
        with self.store._lock, self.store._connect() as db:
            db.execute("INSERT INTO workspace_tool_events(turn_id,payload) VALUES(?,?)", (turn_id, json.dumps(payload)))
        return payload

    def events(self, turn_id):
        with self.store._connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM workspace_tool_events WHERE turn_id=? ORDER BY id LIMIT 100", (turn_id,))]
