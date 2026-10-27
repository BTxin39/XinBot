"""桌面壳的纯逻辑测试（不需要真实窗口）。

依赖 Windows API 的部分（`win32_api`/`shell`）不在这里测：
它们必须在真实桌面上验证，用 mock 只能测出自己写的 mock。
本文件覆盖 `geometry` 与 `settings`——位置夹取、命中判断、状态持久化，
这些是"拔掉副屏后窗口丢失""点到透明区域也响应"之类缺陷的来源。
"""

import json

import pytest

from app.interfaces.desktop import geometry, settings
from app.interfaces.desktop.geometry import Monitor, Rect


def test_monitor_and_rect_helpers():
    monitor = Monitor(0, 0, 1920, 1080)
    assert (monitor.width, monitor.height) == (1920, 1080)
    rect = Rect(10, 20, 100, 50)
    assert (rect.right, rect.bottom) == (110, 70)
    assert rect.contains(10, 20)
    assert not rect.contains(110, 70)
    assert rect.contains(109, 69)


def test_intersection_area():
    a = Rect(0, 0, 100, 100)
    assert a.intersection_area(Rect(50, 50, 100, 100)) == 50 * 50
    assert a.intersection_area(Rect(200, 200, 10, 10)) == 0
    # 完全包含时取小的那个
    assert a.intersection_area(Rect(10, 10, 20, 20)) == 400


class TestClampToMonitors:
    def test_visible_window_unchanged(self):
        monitors = [Monitor(0, 0, 1920, 1080)]
        rect = Rect(100, 100, 320, 420)
        assert geometry.clamp_to_monitors(rect, monitors) == rect

    def test_offscreen_window_moved_back(self):
        monitors = [Monitor(0, 0, 1920, 1080)]
        rect = Rect(5000, 5000, 320, 420)
        fixed = geometry.clamp_to_monitors(rect, monitors)
        assert fixed == Rect(1600, 660, 320, 420)
        assert fixed.left >= 0 and fixed.top >= 0
        assert fixed.right <= 1920 and fixed.bottom <= 1080

    def test_window_on_removed_second_monitor(self):
        """副屏被拔掉后，窗口应被拉回主屏（最常见的位置丢失场景）。"""
        primary = Monitor(0, 0, 1920, 1080)
        rect = Rect(2500, 300, 320, 420)  # 原本在扩展屏幕上
        fixed = geometry.clamp_to_monitors(rect, [primary])
        assert fixed.intersection_area(Rect(0, 0, 1920, 1080)) == 320 * 420

    def test_partially_visible_but_enough_is_kept(self):
        """露出一块足够大的区域时不强行移动（尊重用户摆放）。"""
        monitors = [Monitor(0, 0, 1920, 1080)]
        rect = Rect(1800, 900, 320, 420)  # 右下角探出屏幕，但仍露出 120×180
        assert geometry.clamp_to_monitors(rect, monitors) == rect

    def test_tiny_sliver_is_moved(self):
        """竖向细条要拉回来。

        注意：10×420 的**面积**已经超过阈值，但它宽只有 10px，
        用户捏不住。判定必须宽高都够（这是真实踩到的设计缺陷）。
        """
        monitors = [Monitor(0, 0, 1920, 1080)]
        rect = Rect(-310, 0, 320, 420)  # 左侧只剩 10px 宽
        fixed = geometry.clamp_to_monitors(rect, monitors)
        assert fixed.left == 0

    def test_horizontal_sliver_is_moved(self):
        monitors = [Monitor(0, 0, 1920, 1080)]
        rect = Rect(200, -410, 320, 420)  # 上方只剩 10px 高
        fixed = geometry.clamp_to_monitors(rect, monitors)
        assert fixed.top == 0

    def test_no_monitors_falls_back(self):
        fixed = geometry.clamp_to_monitors(Rect(50, 60, 320, 420), [])
        assert fixed == Rect(0, 0, 320, 420)

    def test_multi_monitor_picks_max_overlap(self):
        left = Monitor(-1920, 0, 1920, 1080)   # 左侧副屏
        right = Monitor(0, 0, 1920, 1080)      # 主屏
        rect = Rect(-1800, 100, 320, 420)      # 大部分在左屏
        assert geometry.clamp_to_monitors(rect, [left, right]) == rect


class TestScaleForMonitor:
    def test_small_window_unchanged(self):
        monitor = Monitor(0, 0, 1920, 1080)
        rect = Rect(10, 10, 320, 420)
        assert geometry.scale_for_monitor(rect, monitor) == rect

    def test_oversized_window_shrinks_proportionally(self):
        monitor = Monitor(0, 0, 800, 600)
        rect = Rect(0, 0, 1600, 1200)
        fitted = geometry.scale_for_monitor(rect, monitor, margin=8)
        assert fitted.width <= 800 and fitted.height <= 600
        # 等比：原比例 4:3，缩放后仍应是 4:3（允许取整误差）
        assert abs(fitted.width / fitted.height - 1600 / 1200) < 0.02
        # 居中
        assert fitted.left >= 0 and fitted.top >= 0


def test_clamp_scale_bounds():
    assert geometry.clamp_scale(0.1) == 0.4
    assert geometry.clamp_scale(10) == 3.0
    assert geometry.clamp_scale(1.5) == 1.5


class TestHitTest:
    window = Rect(100, 100, 320, 420)

    def test_outside_window(self):
        assert not geometry.hit_test(50, 50, self.window, None)

    def test_inside_without_content_uses_window(self):
        # 未知角色区域时宁可多响应，也不要完全点不到
        assert geometry.hit_test(150, 150, self.window, None)

    def test_outside_content_rect(self):
        content = Rect(10, 10, 100, 100)  # 窗口内的左上角小块
        assert not geometry.hit_test(350, 450, self.window, content)
        assert geometry.hit_test(120, 120, self.window, content)

    def test_alpha_ratio_below_threshold_rejected(self):
        content = Rect(0, 0, 320, 420)
        # 点在透明的角落：alpha 占比极低 → 应当穿透，不响应
        assert not geometry.hit_test(110, 110, self.window, content, alpha_ratio=0.0)
        assert not geometry.hit_test(
            110, 110, self.window, content, alpha_ratio=0.001, alpha_threshold=0.02
        )

    def test_unknown_alpha_falls_back_to_rectangle(self):
        """None 表示"还没有掩码数据"，此时只按矩形判断（与 0.0 区分）。"""
        content = Rect(0, 0, 320, 420)
        assert geometry.hit_test(110, 110, self.window, content, alpha_ratio=None)

    def test_alpha_ratio_above_threshold_accepted(self):
        content = Rect(0, 0, 320, 420)
        assert geometry.hit_test(110, 110, self.window, content, alpha_ratio=0.5)


class TestPetWindowState:
    def test_defaults_are_sane(self):
        state = settings.PetWindowState()
        assert state.width > 0 and state.height > 0
        assert state.scale == 1.0
        assert state.click_through is True

    def test_first_run_goes_bottom_right(self):
        """从未定位过时落到主屏右下角——桌宠最自然的位置。"""
        monitors = [Monitor(0, 0, 1920, 1080)]
        rect = settings.PetWindowState().restore(monitors, margin=48)
        assert rect.right <= 1920 and rect.bottom <= 1080
        assert rect.left > 1920 // 2, "应该在右下角"
        assert rect.top > 1080 // 2

    def test_restore_uses_saved_position(self):
        monitors = [Monitor(0, 0, 1920, 1080)]
        state = settings.PetWindowState(x=200, y=300)
        assert state.restore(monitors) == Rect(200, 300, state.width, state.height)

    def test_restore_clamps_offscreen_saved_position(self):
        monitors = [Monitor(0, 0, 1920, 1080)]
        state = settings.PetWindowState(x=9000, y=9000)
        rect = state.restore(monitors)
        assert rect.left < 1920 and rect.top < 1080

    def test_normalized_rejects_absurd_values(self):
        """手改配置写坏字段时，收敛成可用值而不是抛异常。"""
        state = settings.PetWindowState(
            width=-5, height=0, scale=99, x="8", y=None
        ).normalized()
        assert state.width >= 80 and state.height >= 80
        assert state.scale == 3.0
        assert state.x == 8
        assert state.y == -1, "None 应回落成 -1（未定位），而不是崩溃"


class TestPersistence:
    def test_load_missing_returns_default(self, tmp_path):
        state = settings.load(tmp_path)
        assert isinstance(state, settings.PetWindowState)
        assert state.visible is True

    def test_save_then_load_roundtrip(self, tmp_path):
        original = settings.PetWindowState(x=42, y=64, scale=1.25, click_through=False)
        path = settings.save(tmp_path, original)
        assert path.is_file()
        loaded = settings.load(tmp_path)
        assert (loaded.x, loaded.y) == (42, 64)
        assert loaded.scale == 1.25
        assert loaded.click_through is False

    def test_corrupt_file_falls_back(self, tmp_path):
        path = settings.state_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not json", encoding="utf-8")
        assert settings.load(tmp_path) == settings.PetWindowState()

    def test_unknown_fields_are_ignored(self, tmp_path):
        """旧版本/新版本字段差异不应让桌宠起不来。"""
        path = settings.state_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"x": 10, "y": 20, "future_field": True}), encoding="utf-8"
        )
        loaded = settings.load(tmp_path)
        assert (loaded.x, loaded.y) == (10, 20)

    def test_save_is_atomic(self, tmp_path):
        """不应留下半写的临时文件。"""
        settings.save(tmp_path, settings.PetWindowState(x=1, y=2))
        leftovers = list((tmp_path / "data").glob("*.tmp"))
        assert leftovers == []


def test_state_path_is_under_data(tmp_path):
    assert settings.state_path(tmp_path).parent.name == "data"


# ── 多显示器 ──────────────────────────────────────────────────────

PRIMARY = Monitor(0, 0, 1920, 1080, "\\\\.\\DISPLAY1")
SECOND = Monitor(1920, 0, 3840, 1080, "\\\\.\\DISPLAY2")


def test_find_monitor_by_name():
    monitors = [PRIMARY, SECOND]
    assert geometry.find_monitor(monitors, SECOND.name) is SECOND
    assert geometry.find_monitor(monitors, "\\\\.\\DISPLAY9") is None
    assert geometry.find_monitor(monitors, "") is None


def test_monitor_at_point():
    monitors = [PRIMARY, SECOND]
    assert geometry.monitor_at(monitors, 10, 10) is PRIMARY
    assert geometry.monitor_at(monitors, 2000, 500) is SECOND


def test_monitor_at_outside_falls_back_to_nearest():
    monitors = [PRIMARY, SECOND]
    # 坐标在屏幕外时也要给出一个显示器，而不是 None
    assert geometry.monitor_at(monitors, -5000, 100) is PRIMARY


def test_bottom_right_uses_target_monitor():
    rect = geometry.bottom_right(SECOND, 320, 420, margin=48)
    assert rect.left == SECOND.right - 320 - 48
    assert rect.top == SECOND.bottom - 420 - 48
    assert rect.right <= SECOND.right


def test_restore_places_on_saved_monitor_when_never_positioned():
    """用户上次把它放在副屏，重启后应回到副屏，而不是跳回主屏。"""
    state = settings.PetWindowState(x=-1, y=-1, monitor=SECOND.name)
    rect = state.restore([PRIMARY, SECOND], dpi=1.0)
    assert rect.left >= SECOND.left, "应当落在副屏上"


def test_restore_falls_back_when_saved_monitor_removed():
    """副屏被拔掉后不能把窗口丢在屏幕外。"""
    state = settings.PetWindowState(x=-1, y=-1, monitor=SECOND.name)
    rect = state.restore([PRIMARY], dpi=1.0)
    assert rect.right <= PRIMARY.right
    assert rect.bottom <= PRIMARY.bottom


def test_restore_keeps_position_on_second_monitor():
    state = settings.PetWindowState(x=2000, y=300, monitor=SECOND.name)
    rect = state.restore([PRIMARY, SECOND], dpi=1.0)
    assert rect.left == 2000 and rect.top == 300


# ── 高 DPI ────────────────────────────────────────────────────────

@pytest.mark.parametrize("dpi", [1.0, 1.25, 1.5, 2.0])
def test_logical_physical_roundtrip(dpi):
    """逻辑 → 物理 → 逻辑 必须回到原值（不能因为取整而漂移）。"""
    state = settings.PetWindowState(x=100, y=200, width=320, height=420)
    physical = state.to_physical(dpi)
    state.from_physical(physical, dpi)
    assert (state.x, state.y) == (100, 200)
    assert (state.width, state.height) == (320, 420)


def test_physical_size_scales_with_dpi():
    state = settings.PetWindowState(width=320, height=420)
    assert state.to_physical(1.0).width == 320
    assert state.to_physical(2.0).width == 640
    assert state.to_physical(1.5).height == 630


def test_saved_size_is_logical_not_physical(tmp_path):
    """核心回归：存的必须是逻辑像素。

    之前存的是物理像素，换到 100% 缩放的屏幕上窗口会明显偏大。
    """
    state = settings.PetWindowState(width=320, height=420)
    state.from_physical(Rect(900, 500, 480, 630), dpi=1.5)  # 1.5 倍下的物理尺寸
    settings.save(tmp_path, state)

    loaded = settings.load(tmp_path)
    assert (loaded.width, loaded.height) == (320, 420)
    assert loaded.dpi == pytest.approx(1.5)
    assert (loaded.x, loaded.y) == (600, 333)


def test_restore_returns_physical_pixels():
    state = settings.PetWindowState(x=100, y=100, width=320, height=420)
    rect = state.restore([PRIMARY], dpi=2.0)
    assert (rect.left, rect.top) == (200, 200)
    assert (rect.width, rect.height) == (640, 840)


def test_dpi_is_persisted_and_normalized(tmp_path):
    state = settings.PetWindowState(dpi=1.75)
    settings.save(tmp_path, state)
    assert settings.load(tmp_path).dpi == pytest.approx(1.75)


def test_legacy_state_without_dpi_loads(tmp_path):
    """旧版本文件没有 dpi 字段——不能因此读不出来。"""
    path = settings.state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"x": 10, "y": 20, "width": 320, "height": 420}),
                    encoding="utf-8")
    loaded = settings.load(tmp_path)
    assert (loaded.x, loaded.y) == (10, 20)
    assert loaded.dpi == 0.0


def test_absurd_dpi_is_clamped_to_zero():
    """dpi 是手改字段，负数/None 不该让换算炸掉。"""
    assert settings.PetWindowState(dpi=-3).normalized().dpi == 0.0
    assert settings.PetWindowState(dpi=None).normalized().dpi == 0.0


def test_zero_dpi_falls_back_to_one():
    """dpi=0（旧文件/未知）时按 1:1 处理，不能除零或抛异常。"""
    state = settings.PetWindowState(width=320, height=420)
    assert state.to_physical(0).width == 320
    state.from_physical(Rect(0, 0, 320, 420), 0)
    assert (state.width, state.height) == (320, 420)


def test_shell_module_imports_without_windows():
    """外壳模块必须能在没有真实窗口的情况下被导入（CLI --help 会触发）。"""
    from app.interfaces.desktop import shell

    assert shell.WINDOW_TITLE
    assert shell.POLL_SECONDS > 0
    assert shell.DRAG_THRESHOLD >= 1
