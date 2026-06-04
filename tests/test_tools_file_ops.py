"""文件操作工具的测试。

使用 pytest 的 tmp_path fixture 创建临时文件系统，
避免测试污染实际项目目录。
"""

import pytest
from app.core.tools.builtin.file_ops import (
    ReadFileTool,
    ListDirectoryTool,
    WriteFileTool,
)


class TestReadFileTool:
    def test_reads_existing_file(self, tmp_path):
        """能读取存在的文件内容。"""
        file = tmp_path / "hello.txt"
        file.write_text("Hello, XinBot!", encoding="utf-8")

        tool = ReadFileTool()
        result = tool.execute(path=str(file))

        assert "Hello, XinBot!" in result

    def test_file_not_found(self, tmp_path):
        """文件不存在时返回错误信息，不抛异常。"""
        tool = ReadFileTool()
        result = tool.execute(path=str(tmp_path / "not_exists.txt"))

        assert "文件不存在" in result

    def test_path_is_directory(self, tmp_path):
        """目标路径是目录时返回错误信息。"""
        tool = ReadFileTool()
        result = tool.execute(path=str(tmp_path))

        assert "不是文件" in result

    def test_large_file_truncated(self, tmp_path):
        """超过 10KB 的文件会被截断。"""
        file = tmp_path / "large.txt"
        # 写入 15KB 数据
        file.write_text("X" * (15 * 1024), encoding="utf-8")

        tool = ReadFileTool()
        result = tool.execute(path=str(file))

        assert "已截断" in result
        assert len(result) < 15 * 1024  # 确实被截断了


class TestListDirectoryTool:
    def test_lists_directory_contents(self, tmp_path):
        """列出目录中的文件和子目录。"""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")
        (tmp_path / "subdir").mkdir()

        tool = ListDirectoryTool()
        result = tool.execute(path=str(tmp_path))

        assert "file1.txt" in result
        assert "file2.py" in result
        assert "subdir/" in result  # 目录带 / 后缀

    def test_empty_directory(self, tmp_path):
        """空目录返回提示信息。"""
        tool = ListDirectoryTool()
        result = tool.execute(path=str(tmp_path))

        assert "目录为空" in result

    def test_directory_not_found(self, tmp_path):
        """目录不存在时返回错误信息。"""
        tool = ListDirectoryTool()
        result = tool.execute(path=str(tmp_path / "not_a_dir"))

        assert "目录不存在" in result

    def test_path_is_file(self, tmp_path):
        """路径指向文件时返回错误信息。"""
        file = tmp_path / "test.txt"
        file.write_text("hello")

        tool = ListDirectoryTool()
        result = tool.execute(path=str(file))

        assert "不是目录" in result

    def test_items_sorted(self, tmp_path):
        """目录内容应该排序输出。"""
        (tmp_path / "c.txt").write_text("c")
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        tool = ListDirectoryTool()
        result = tool.execute(path=str(tmp_path))

        # 验证排序：a 应该在 b 前面，b 应该在 c 前面
        a_pos = result.index("a.txt")
        b_pos = result.index("b.txt")
        c_pos = result.index("c.txt")
        assert a_pos < b_pos < c_pos


class TestWriteFileTool:
    def test_writes_file(self, tmp_path):
        """写入新文件。"""
        target = tmp_path / "output.txt"
        tool = WriteFileTool()
        result = tool.execute(path=str(target), content="XinBot was here!")

        assert "已写入" in result
        assert target.read_text(encoding="utf-8") == "XinBot was here!"

    def test_overwrites_existing_file(self, tmp_path):
        """覆盖已存在的文件。"""
        target = tmp_path / "existing.txt"
        target.write_text("old content")

        tool = WriteFileTool()
        tool.execute(path=str(target), content="new content")

        assert target.read_text(encoding="utf-8") == "new content"

    def test_creates_parent_directories(self, tmp_path):
        """写入深度路径时自动创建父目录。"""
        target = tmp_path / "deep" / "nested" / "file.txt"

        tool = WriteFileTool()
        result = tool.execute(path=str(target), content="deep content")

        assert "已写入" in result
        assert target.read_text(encoding="utf-8") == "deep content"

    def test_rejects_directory_path(self, tmp_path):
        """目标路径是目录时返回错误。"""
        tool = WriteFileTool()
        result = tool.execute(path=str(tmp_path), content="test")

        assert "路径是目录" in result

    def test_danger_level_is_dangerous(self):
        """WriteFileTool 必须是 DANGEROUS 等级。"""
        tool = WriteFileTool()
        from app.core.tools.base import DangerLevel
        assert tool.danger_level == DangerLevel.DANGEROUS


class TestDangerLevels:
    """确认各工具的危险等级设置正确。"""

    def test_read_file_is_readonly(self):
        from app.core.tools.base import DangerLevel
        assert ReadFileTool().danger_level == DangerLevel.READ_ONLY

    def test_list_directory_is_readonly(self):
        from app.core.tools.base import DangerLevel
        assert ListDirectoryTool().danger_level == DangerLevel.READ_ONLY

    def test_write_file_is_dangerous(self):
        from app.core.tools.base import DangerLevel
        assert WriteFileTool().danger_level == DangerLevel.DANGEROUS
