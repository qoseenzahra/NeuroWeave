"""Cache expensive read-only checks by file identity; permission checks always run first."""
from collections import OrderedDict
from threading import RLock
import time

_items=OrderedDict();_lock=RLock()

def checked_file(path,kind,action,ttl=600):
    stat=path.stat()
    key=(str(path.resolve()),stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,kind)
    with _lock:
        item=_items.get(key)
        if item and time.monotonic()-item[0]<ttl:return item[1]
    result=action()
    after=path.stat()
    if (stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('检查期间文件发生变化，请重试')
    with _lock:
        _items[key]=(time.monotonic(),result);_items.move_to_end(key)
        while len(_items)>4096:_items.popitem(last=False)
    return result
