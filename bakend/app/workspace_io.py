"""Filesystem primitives anchored to directory descriptors on Linux.

resolve() checks scope; O_NOFOLLOW on every parent closes the usual symlink
replacement race between validation and opening. renameat2 never overwrites an
unconfirmed destination that appeared after preview. Windows rename is already
no-replace; Windows deployments retain canonical/reparse-point checks.
"""
from contextlib import contextmanager
import ctypes
import errno
import os
from pathlib import Path
import shutil
import stat


@contextmanager
def directory_fd(path: Path):
    if os.name == "nt":
        yield None
        return
    path = path.absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def rename(source: Path, target: Path):
    if os.name == "nt":
        os.rename(source, target)
        return
    with directory_fd(source.parent) as src, directory_fd(target.parent) as dst:
        if stat.S_ISLNK(os.stat(source.name, dir_fd=src, follow_symlinks=False).st_mode):
            raise PermissionError("源路径已变成符号链接")
        libc = ctypes.CDLL(None, use_errno=True)
        if not hasattr(libc, "renameat2"):
            raise OSError("当前系统缺少原子不覆盖 renameat2 支持")
        call = libc.renameat2
        call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        call.restype = ctypes.c_int
        if call(src, os.fsencode(source.name), dst, os.fsencode(target.name), 1):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))


def mkdir(path: Path, *, parents=False, exist_ok=False):
    if parents and not path.parent.exists():
        mkdir(path.parent, parents=True, exist_ok=True)
    with directory_fd(path.parent) as parent:
        try:
            os.mkdir(path if parent is None else path.name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            if not exist_ok or path.is_symlink() or not path.is_dir():
                raise


def open_read(path: Path):
    with directory_fd(path.parent) as parent:
        fd = os.open(path if parent is None else path.name,
                     os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise PermissionError("不是普通文件")
    return fd


def copy(source: Path, target: Path, policy, budget=None):
    budget = budget if budget is not None else [100000]
    budget[0] -= 1
    if budget[0] < 0 or policy.sensitive(source) or source.is_symlink():
        raise PermissionError("复制目录超过限制或包含敏感内容/符号链接")
    with directory_fd(source.parent) as src, directory_fd(target.parent) as dst:
        source_name = source if src is None else source.name
        target_name = target if dst is None else target.name
        source_stat = os.stat(source_name, dir_fd=src, follow_symlinks=False)
        if stat.S_ISDIR(source_stat.st_mode):
            os.mkdir(target_name, mode=0o700, dir_fd=dst)
            with directory_fd(source) as source_dir:
                with os.scandir(source if source_dir is None else source_dir) as children:
                    for child in children:
                        copy(source / child.name, target / child.name, policy, budget)
        elif stat.S_ISREG(source_stat.st_mode):
            fd = os.open(source_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=src)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise PermissionError("复制源已不再是普通文件")
                output = os.open(target_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dst)
                with os.fdopen(output, "wb") as dest, os.fdopen(fd, "rb") as origin:
                    fd = -1
                    shutil.copyfileobj(origin, dest, 1024 * 1024)
            finally:
                if fd >= 0:
                    os.close(fd)
        else:
            raise PermissionError("拒绝复制符号链接或特殊文件")


def remove(path: Path):
    with directory_fd(path.parent) as parent:
        if path.is_dir():
            if parent is not None and not shutil.rmtree.avoids_symlink_attacks:
                raise OSError(errno.ENOTSUP, "此 Python 不支持安全递归删除")
            shutil.rmtree(path if parent is None else path.name, dir_fd=parent)
        else:
            os.unlink(path if parent is None else path.name, dir_fd=parent)
