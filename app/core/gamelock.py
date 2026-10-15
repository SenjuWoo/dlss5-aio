"""Serialize AIO writers to a game across the GUI and CLI.

The operating system releases the lock after a crash. Keeping the empty
sidecar avoids a race caused by deleting a file another process has opened.
"""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import os
import threading

_held = threading.local()


@contextmanager
def locked(folder):
    """Hold one nonblocking OS lock; never take over another writer's lock."""
    path = Path(folder).resolve() / ".dlss5-aio.lock"
    key = os.path.normcase(str(path))
    held = getattr(_held, "paths", None)
    if held is None:
        held = _held.paths = set()
    # Route switching and failed-install rollback call uninstall internally.
    if key in held:
        yield
        return
    if path.is_symlink():
        raise OSError("The game's AIO lock is a symbolic link; no changes were made.")
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise OSError("Another AIO operation is writing to this game. Wait for it to finish.") from error
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def exclusive(function):
    """Give the install and runtime updater the same game-folder boundary."""
    @wraps(function)
    def wrapped(game, *args, **kwargs):
        with locked(game.folder):
            return function(game, *args, **kwargs)
    return wrapped
