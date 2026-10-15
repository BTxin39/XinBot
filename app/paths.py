"""项目根目录解析。

为什么需要它：原先 `app/interfaces/web/{server,process}.py` 与
`routes/models.py` 各自用 `Path(__file__).resolve().parents[N]` 推算仓库根目录。
这类"数层数"的写法有两个问题：
    1. 不同深度的文件 N 不同，极易算错（P5 目录搬迁时三个文件全错，
       且其中一处算成了上级目录之外的路径）；
    2. 每次调整目录层级都要重新数一遍。

因此改为按**项目标记文件**向上查找，与层级无关。
"""

from pathlib import Path

# 判定仓库根标志：这些文件存在于仓库根目录
ROOT_MARKERS = ("pyproject.toml", ".git")

# 兜底：从本文件向上最多找这么多层（app/paths.py 在仓库根的下一层）
MAX_DEPTH = 8


def repo_root() -> Path:
    """返回仓库根目录。

    从本文件所在位置向上查找含 `pyproject.toml` 或 `.git` 的目录；
    找不到时退回本文件的上两级（app/ 的父目录），保证仍有可用值。
    """
    here = Path(__file__).resolve()
    for candidate in here.parents[:MAX_DEPTH]:
        if any((candidate / marker).exists() for marker in ROOT_MARKERS):
            return candidate
    return here.parents[1]
