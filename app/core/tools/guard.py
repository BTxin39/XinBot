"""工具安全审批层。

职责：在工具执行前根据危险等级决定是否放行。

这是"让 Agent 有能力"和"不让 Agent 搞破坏"的分界线。

设计决策：
  1. SAFE 工具直接放行，不回调 — 否则 get_time 每次都要弹确认框
  2. READ_ONLY 工具默认全部在白名单中，直接放行
     不在白名单的 READ_ONLY 工具需要审批（与 DANGEROUS 相同）
  3. DANGEROUS 工具必须通过审批回调 — 回调由外层注入
  4. 没有回调时默认拒绝 — fail-safe 原则

为什么审批逻辑和交互方式要分离？
  CLI：用 input() 问用户
  GUI/Live2D：弹窗
  测试：lambda tool, kwargs: True
  如果写死在 ToolManager 里，换前端就要改核心代码。
"""

from typing import TYPE_CHECKING, Callable

from app.core.tools.base import DangerLevel

if TYPE_CHECKING:  # 仅用于类型标注
    from app.core.tools.base import BaseTool

# ── 类型定义 ──────────────────────────────────────────────────────

ApprovalCallback = Callable[["BaseTool", dict], bool]
"""审批回调签名：
    tool   — 被调用的工具实例，可读 name/description/danger_level
    kwargs — LLM 传入的参数字典，用于展示给用户做判断
    返回 True=批准，False=拒绝

具体实现由调用方注入（CLI 见 `app.interfaces.cli.approval`）。见 docs/DECISIONS_V0.2.md §9。
"""


# ── ToolGuard ─────────────────────────────────────────────────────

class ToolGuard:
    """工具安全审批守卫。

    使用：guard.check(tool, arguments) → bool

    示例:
        # CLI 环境（默认所有 READ_ONLY 工具在白名单，直接放行）
        guard = ToolGuard(cli_approval_callback)

        # 去掉某个 READ_ONLY 工具的白名单，让它也需要审批
        guard = ToolGuard(cli_approval_callback, readonly_whitelist={"read_file"})
        # → read_file 放行，其他 READ_ONLY 工具需要审批

        # 测试环境
        guard = ToolGuard(lambda tool, kwargs: True)

        # 默认安全（拒绝所有 DANGEROUS 操作）
        guard = ToolGuard()
    """

    def __init__(
        self,
        approval_callback: ApprovalCallback | None = None,
        readonly_whitelist: set[str] | None = None,
    ):
        """初始化安全守卫。

        Args:
            approval_callback: DANGEROUS 工具的审批回调（也用于不在白名单的 READ_ONLY 工具）。
                               None 时默认拒绝所有需要审批的操作（fail-safe）。
            readonly_whitelist: READ_ONLY 工具的白名单。
                                None → 所有 READ_ONLY 工具直接放行（默认）。
                                传入 set → 在 set 中的放行，不在的需要审批。
        """
        self._callback = approval_callback
        # None = "全部放行"的哨兵值；传入 set 后，只有 set 内的放行
        self._readonly_whitelist = readonly_whitelist

    def check(self, tool: "BaseTool", kwargs: dict) -> bool:
        """检查工具是否可以执行。

        判断链：
          SAFE      → 直接通过
          READ_ONLY → 白名单检查：
                        - whitelist=None（默认）→ 放行
                        - 在白名单中 → 放行
                        - 不在白名单 → 走审批回调（同 DANGEROUS）
          DANGEROUS → 有回调则回调决定，无回调则拒绝（fail-safe）
          其他      → 拒绝（防御性编程）
        """
        level = tool.danger_level

        if level == DangerLevel.SAFE:
            return True

        if level == DangerLevel.READ_ONLY:
            # None = 哨兵值，表示所有 READ_ONLY 工具都在白名单中
            if self._readonly_whitelist is None:
                return True
            # 不在白名单 → 走审批
            if tool.name not in self._readonly_whitelist:
                return self._ask_user(tool, kwargs)
            return True

        if level == DangerLevel.DANGEROUS:
            return self._ask_user(tool, kwargs)

        # 未知等级 → 拒绝（防御性编程）
        return False

    def _ask_user(self, tool: "BaseTool", kwargs: dict) -> bool:
        """统一的审批询问入口。"""
        if self._callback is None:
            return False  # fail-safe
        try:
            return self._callback(tool, kwargs)
        except Exception:
            return False  # 回调崩了也算不安全
