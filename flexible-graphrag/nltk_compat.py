"""NLTK data for LlamaIndex's SentenceSplitter, as plain files.

nltk 3.10.4+ refuses to open a hardlinked file, and uv installs packages as hardlinks to its cache,
so the NLTK data inside llama-index-core fails the first ingest after a uv install ("refusing
multiply-linked file"). Unless NLTK_DATA is set, use_plain_nltk_data() copies that data once into
the user cache folder and points NLTK_DATA at the copy (LlamaIndex reads NLTK_DATA the first time
it needs NLTK). One copy per llama-index-core version (nltk_data/<version>).

nltk 3.10.4+ also refuses to read a data folder that another account can write to, and a umask of
0002 (Ubuntu's default for many users) makes the copy group-writable, so the copy is made private
(go-w), and an older copy that is not private is replaced.
"""
import importlib.metadata
import importlib.util
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def _writable_by_others(path: Path) -> bool:
    return any(p.lstat().st_mode & 0o022 for p in (path, *path.rglob("*")))


def _make_private(path: Path) -> None:
    """Remove group and world write from path and everything under it (links are left alone)."""
    for p in (path, *path.rglob("*")):
        if not p.is_symlink():
            p.chmod(p.stat().st_mode & ~0o022)


def use_plain_nltk_data() -> None:
    if os.environ.get("NLTK_DATA"):
        return  # the user's own folder
    try:
        spec = importlib.util.find_spec("llama_index.core")  # without importing LlamaIndex
        if spec is None or not spec.submodule_search_locations:
            return
        bundled = Path(list(spec.submodule_search_locations)[0]) / "_static" / "nltk_cache"
        if not bundled.is_dir():
            return
        import platformdirs
        # one copy per llama-index-core version, so venvs with different versions don't replace each other's
        version = importlib.metadata.version("llama-index-core")
        target = Path(platformdirs.user_cache_dir("flexible-graphrag", appauthor=False)) / "nltk_data" / version
        if target.is_dir() and os.name == "posix" and _writable_by_others(target):
            # nltk would refuse it, and a file changed while it was writable keeps the change
            shutil.rmtree(target, ignore_errors=True)
            logger.info(f"Replacing NLTK data copy that other accounts could write to: {target}")
        if not target.is_dir():
            # Copied next to it, then renamed: the backend and Langflow may start at the same time
            tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(bundled, tmp)
            if os.name == "posix":
                _make_private(tmp)
                for parent in (target.parent, target.parent.parent):  # nltk_data/, flexible-graphrag/
                    parent.chmod(parent.stat().st_mode & ~0o022)
            try:
                tmp.rename(target)
            except OSError:
                shutil.rmtree(tmp, ignore_errors=True)  # another process put its copy there first
            logger.info(f"NLTK data for LlamaIndex copied to {target}")
        os.environ["NLTK_DATA"] = str(target)
    except Exception as e:
        logger.warning(f"Could not set up a copy of LlamaIndex's NLTK data ({e}): using its own")
