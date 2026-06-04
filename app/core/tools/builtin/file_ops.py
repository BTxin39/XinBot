"""文件操作工具。

三个基础文件工具：
- read_file:  读取文本文件内容（READ_ONLY）
- list_directory: 列出目录内容（READ_ONLY）
- write_file: 写入文本文件（DANGEROUS，需审批）

设计要点：
1. 所有路径解析为绝对路径，避免"../../etc/passwd"类攻击
2. execute() 返回 str，出错时返回错误描述而不是抛异常
3. 读文件有大小上限（10KB），防止把大文件灌进 LLM 上下文
4. 写文件会创建父目录（如果不存在），提升用户体验
"""

from pathlib import Path

from app.core.tools.base import BaseTool, DangerLevel, ToolParameter

# 读文件上限：防止把二进制大文件或日志文件灌进 LLM 上下文
MAX_READ_BYTES = 10 * 1024  # 10 KB


def _resolve_path(path_str: str) -> Path:
    """将传入的路径字符串解析为绝对路径。

    相对路径 → 相对于当前工作目录展开。
    绝对路径 → 保持原样。
    """
    return Path(path_str).expanduser().resolve()


class ReadFileTool(BaseTool):
    """读取文本文件内容。"""

    name = "read_file"
    description = (
        "读取文本文件的内容。"
        "可以读取代码、文档、配置文件等。"
        "不要用这个工具读取二进制文件（图片、PDF 等）。"
        f"最多读取 {MAX_READ_BYTES // 1024} KB 的内容。"
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="要读取的文件路径。可以是相对路径或绝对路径。",
        )
    ]
    danger_level = DangerLevel.READ_ONLY

    def execute(self, path: str) -> str:
        try:
            file_path = _resolve_path(path)

            if not file_path.exists():
                return f"文件不存在: {file_path}"

            if not file_path.is_file():
                return f"路径不是文件: {file_path}"

            content = file_path.read_text(encoding="utf-8")
            if len(content) > MAX_READ_BYTES:
                content = (
                    content[:MAX_READ_BYTES]
                    + f"\n\n…（文件过大，已截断。原始大小: {len(content)} 字符）"
                )

            return content

        except UnicodeDecodeError:
            return f"无法以 UTF-8 编码读取文件（可能是二进制文件）: {file_path}"
        except PermissionError:
            return f"没有权限读取文件: {file_path}"
        except OSError as e:
            return f"读取文件时发生错误: {e}"


class ListDirectoryTool(BaseTool):
    """列出目录中的文件和子目录。"""

    name = "list_directory"
    description = (
        "列出指定目录下的文件和子目录。"
        "适合了解项目结构、查看有哪些文件。"
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="要列出的目录路径。可以是相对路径或绝对路径。",
        )
    ]
    danger_level = DangerLevel.READ_ONLY

    def execute(self, path: str) -> str:
        try:
            dir_path = _resolve_path(path)

            if not dir_path.exists():
                return f"目录不存在: {dir_path}"

            if not dir_path.is_dir():
                return f"路径不是目录: {dir_path}"

            items = []
            for item in sorted(dir_path.iterdir()):
                marker = "/" if item.is_dir() else ""
                items.append(f"  {item.name}{marker}")

            if not items:
                return f"目录为空: {dir_path}"

            return f"目录 {dir_path} 的内容：\n" + "\n".join(items)

        except PermissionError:
            return f"没有权限访问目录: {dir_path}"
        except OSError as e:
            return f"读取目录时发生错误: {e}"


class WriteFileTool(BaseTool):
    """写入文本文件。DANGEROUS — 需要用户审批。"""

    name = "write_file"
    description = (
        "将文本内容写入文件。如果文件已存在则覆盖。"
        "可以创建代码文件、文档、配置文件等。"
        "写入前需要用户确认。"
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="要写入的文件路径。可以是相对路径或绝对路径。",
        ),
        ToolParameter(
            name="content",
            type="string",
            description="要写入的文本内容。",
        ),
    ]
    danger_level = DangerLevel.DANGEROUS

    def execute(self, path: str, content: str) -> str:
        try:
            file_path = _resolve_path(path)

            # 如果目标是目录，拒绝
            if file_path.exists() and file_path.is_dir():
                return f"路径是目录，无法写入: {file_path}"

            # 创建父目录（如果不存在）
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content, encoding="utf-8")

            # 友好反馈：如果路径在项目内，显示相对路径
            try:
                display_path = file_path.relative_to(Path.cwd())
            except ValueError:
                display_path = file_path

            return f"文件已写入: {display_path}\n写入 {len(content)} 字符"

        except PermissionError:
            return f"没有权限写入文件: {file_path}"
        except OSError as e:
            return f"写入文件时发生错误: {e}"
