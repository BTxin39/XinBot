import pytest
from app.core.tools.base import BaseTool, DangerLevel, ToolParameter
from app.core.tools.guard import ToolGuard


# ── 测试用假工具 ──────────────────────────────────────────────────

class FakeSafeTool(BaseTool):
    name = "safe_tool"
    description = "A safe tool"
    parameters = []
    danger_level = DangerLevel.SAFE

    def execute(self, **kwargs) -> str:
        return "safe"


class FakeReadOnlyTool(BaseTool):
    name = "readonly_tool"
    description = "A read-only tool"
    parameters = []
    danger_level = DangerLevel.READ_ONLY

    def execute(self, **kwargs) -> str:
        return "read"


class FakeDangerousTool(BaseTool):
    name = "dangerous_tool"
    description = "A dangerous tool"
    parameters = [
        ToolParameter(name="path", type="string", description="File path"),
    ]
    danger_level = DangerLevel.DANGEROUS

    def execute(self, path: str) -> str:
        return f"wrote to {path}"


# ── 测试 ──────────────────────────────────────────────────────────

class TestToolGuard:
    """测试安全审批核心逻辑。"""

    # ── SAFE ─────────────────────────────────────────────────

    def test_safe_tool_passes_without_callback(self):
        """SAFE 工具不需要回调，直接放行。"""
        guard = ToolGuard()  # 无回调
        tool = FakeSafeTool()
        assert guard.check(tool, {}) is True

    def test_safe_tool_passes_with_callback(self):
        """SAFE 工具即使有回调也不触发（避免骚扰用户）。"""
        call_count = 0

        def callback(tool, kwargs):
            nonlocal call_count
            call_count += 1
            return False  # 回调拒绝，但 SAFE 不应该走回调

        guard = ToolGuard(callback)
        tool = FakeSafeTool()
        assert guard.check(tool, {}) is True
        assert call_count == 0  # 关键：回调从未被调用

    # ── READ_ONLY（默认白名单 = None，全部放行）─────────────

    def test_readonly_tool_passes_without_callback(self):
        """READ_ONLY 工具默认全部在白名单，直接放行。"""
        guard = ToolGuard()  # whitelist=None
        tool = FakeReadOnlyTool()
        assert guard.check(tool, {}) is True

    def test_readonly_tool_passes_with_callback(self):
        """READ_ONLY 工具在白名单时不触发回调。"""
        call_count = 0

        def callback(tool, kwargs):
            nonlocal call_count
            call_count += 1
            return False

        guard = ToolGuard(callback)  # whitelist=None（默认全部放行）
        tool = FakeReadOnlyTool()
        assert guard.check(tool, {}) is True
        assert call_count == 0

    # ── READ_ONLY 白名单控制 ─────────────────────────────────

    def test_readonly_in_whitelist_passes(self):
        """在指定白名单中的 READ_ONLY 工具直接放行。"""
        guard = ToolGuard(readonly_whitelist={"readonly_tool"})
        tool = FakeReadOnlyTool()
        assert guard.check(tool, {}) is True

    def test_readonly_not_in_whitelist_asks_callback(self):
        """不在白名单中的 READ_ONLY 工具触发审批回调。"""
        call_count = 0

        def callback(tool, kwargs):
            nonlocal call_count
            call_count += 1
            return True

        # 白名单里只有 "other_tool"，不包含 "readonly_tool"
        guard = ToolGuard(callback, readonly_whitelist={"other_tool"})
        tool = FakeReadOnlyTool()
        assert guard.check(tool, {}) is True  # 回调批准
        assert call_count == 1

    def test_readonly_not_in_whitelist_denied_by_callback(self):
        """不在白名单且回调拒绝 → 拦截。"""
        guard = ToolGuard(
            lambda t, k: False,
            readonly_whitelist={"other_tool"},
        )
        tool = FakeReadOnlyTool()
        assert guard.check(tool, {}) is False

    def test_readonly_not_in_whitelist_no_callback_denied(self):
        """不在白名单且没有回调 → 拒绝（fail-safe）。"""
        guard = ToolGuard(readonly_whitelist=set())  # 空白名单
        tool = FakeReadOnlyTool()
        assert guard.check(tool, {}) is False

    # ── DANGEROUS ────────────────────────────────────────────

    def test_dangerous_tool_denied_without_callback(self):
        """没有审批回调时，DANGEROUS 工具被拒绝（fail-safe）。"""
        guard = ToolGuard()  # 无回调
        tool = FakeDangerousTool()
        assert guard.check(tool, {"path": "/etc/hosts"}) is False

    def test_dangerous_tool_passes_when_callback_returns_true(self):
        """回调批准 → 放行。"""
        guard = ToolGuard(lambda tool, kwargs: True)
        tool = FakeDangerousTool()
        assert guard.check(tool, {"path": "test.txt"}) is True

    def test_dangerous_tool_denied_when_callback_returns_false(self):
        """回调拒绝 → 拦截。"""
        guard = ToolGuard(lambda tool, kwargs: False)
        tool = FakeDangerousTool()
        assert guard.check(tool, {"path": "test.txt"}) is False

    def test_callback_receives_correct_tool_and_kwargs(self):
        """验证回调拿到的参数是正确的。"""
        received_tool = None
        received_kwargs = None

        def callback(tool, kwargs):
            nonlocal received_tool, received_kwargs
            received_tool = tool
            received_kwargs = kwargs
            return True

        guard = ToolGuard(callback)
        tool = FakeDangerousTool()
        guard.check(tool, {"path": "/data/test.txt"})

        assert received_tool is tool
        assert received_kwargs == {"path": "/data/test.txt"}

    def test_callback_exception_causes_denial(self):
        """回调抛异常 → 拒绝（fail-safe，不能因回调崩了而放行）。"""

        def crashing_callback(tool, kwargs):
            raise RuntimeError("回调内部错误")

        guard = ToolGuard(crashing_callback)
        tool = FakeDangerousTool()
        assert guard.check(tool, {"path": "test.txt"}) is False

    def test_unknown_danger_level_denied(self):
        """防御性：如果 danger_level 被篡改为无效值，拒绝执行。"""
        tool = FakeSafeTool()
        # 模拟 danger_level 被意外修改为非法值
        object.__setattr__(tool, "danger_level", "not_a_real_level")

        guard = ToolGuard()
        # 非法等级应该走 fallthrough 分支，返回 False
        result = guard.check(tool, {})
        assert result is False  # 防御性拒绝
