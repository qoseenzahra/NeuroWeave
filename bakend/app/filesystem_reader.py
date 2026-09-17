"""Bounded read operations shared by dataset and managed-output browsing."""
from __future__ import annotations

import base64
import fnmatch
import heapq
import json
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from . import workspace_io as secure_io


def fingerprint(path: Path):
    try:
        s = path.lstat()
        return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_mode]
    except FileNotFoundError:
        return None


class FilesystemReader:
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

