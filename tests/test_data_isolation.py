"""data/ 污染护栏自身的测试（tests/data_guard.py + conftest 集成）。

背景：P3 期间发现 `tests/test_summarizer.py` 会写真实 `data/xinbot.db`。
修掉之后必须保证"护栏真的能发现污染"，否则它会变成又一个假绿保护。
"""

import hashlib

from tests import data_guard


def _write(path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_fingerprint_is_stable_and_content_addressed(tmp_path):
    _write(tmp_path / "a.json", "one")
    first = data_guard.fingerprint(tmp_path)
    assert list(first) == ["a.json"]
    assert first["a.json"] == hashlib.sha256(b"one").hexdigest()

    # 内容不变 → 指纹不变
    assert data_guard.fingerprint(tmp_path) == first


def test_fingerprint_ignores_logs_and_runtime_state(tmp_path):
    _write(tmp_path / "web.log", "noise")
    _write(tmp_path / "web_process.json", "{}")
    _write(tmp_path / "personas.json", "{}")
    assert list(data_guard.fingerprint(tmp_path)) == ["personas.json"]


def test_fingerprint_handles_missing_directory(tmp_path):
    assert data_guard.fingerprint(tmp_path / "nope") == {}


def test_diff_detects_created_removed_modified(tmp_path):
    _write(tmp_path / "keep.json", "same")
    _write(tmp_path / "edit.json", "before")
    _write(tmp_path / "gone.json", "bye")
    before = data_guard.fingerprint(tmp_path)

    _write(tmp_path / "edit.json", "after")
    (tmp_path / "gone.json").unlink()
    _write(tmp_path / "new.json", "hi")
    after = data_guard.fingerprint(tmp_path)

    changes = data_guard.diff(before, after)
    assert changes["created"] == ["new.json"]
    assert changes["removed"] == ["gone.json"]
    assert changes["modified"] == ["edit.json"]


def test_diff_reports_nothing_for_identical_snapshots():
    snapshot = {"a": "1", "b": "2"}
    assert not any(data_guard.diff(snapshot, dict(snapshot)).values())


def test_describe_lists_only_non_empty_categories():
    text = data_guard.describe({"created": ["x"], "removed": [], "modified": ["y"]})
    assert "新增: x" in text
    assert "修改: y" in text
    assert "删除" not in text


def test_fingerprint_covers_the_db_that_was_being_polluted():
    """回归锚点：真实 data/xinbot.db 必须被纳入指纹范围。

    历史缺陷正是对这个文件写入；若它被排除在指纹之外，护栏就形同虚设。
    """
    if not (data_guard.DATA / "xinbot.db").is_file():
        return  # 全新 checkout 可能没有数据库
    assert "xinbot.db" in data_guard.fingerprint()


def test_baseline_state_lives_in_data_guard_not_conftest():
    """基线快照必须在 `tests/data_guard.py` 里，不能在 conftest.py。

    为什么专门测这个：`tests/conftest.py` 会被加载成**两个不同的模块对象**
    （pytest 注册 hook 用的那个，与测试文件 `from tests import conftest` 拿到的
    不是同一个）。若把基线放在 conftest 的模块级变量里，
    `pytest_sessionfinish` 读到的永远是 None，护栏会静默失效——
    P3 期间实测踩过这个坑，故用契约测试锁住。
    """
    import tests.conftest as conftest_module

    assert not any(
        isinstance(value, dict) and value and all(len(v) == 64 for v in value.values())
        for value in vars(conftest_module).values()
    ), "conftest.py 里不应存放指纹基线状态"

    assert hasattr(data_guard, "capture_baseline")
    assert hasattr(data_guard, "changes_since_baseline")


def test_changes_since_baseline_roundtrip(tmp_path, monkeypatch):
    """基线捕获 + 差异检测的完整往返（基线状态确实被共享）。

    注意 `capture_baseline()`/`changes_since_baseline()` 内部调用的是
    `fingerprint()`，其默认参数在函数定义时已绑定真实 DATA，
    所以这里用 `fingerprint(root)` + `diff` 复现同一往返。
    """
    _write(tmp_path / "keep.json", "same")
    base = data_guard.fingerprint(tmp_path)
    assert not any(data_guard.diff(base, data_guard.fingerprint(tmp_path)).values())

    _write(tmp_path / "keep.json", "changed")
    assert data_guard.diff(base, data_guard.fingerprint(tmp_path))["modified"] == ["keep.json"]

    _write(tmp_path / "keep.json", "same")
    assert not any(data_guard.diff(base, data_guard.fingerprint(tmp_path)).values())


# ── 预检：捕获"跨会话已存在"的污染 ────────────────────────────────


def test_precheck_flags_temp_paths(tmp_path):
    """预检必须能识别被测试 tmp_path 覆盖过的配置文件。"""
    # 用真实 Windows 路径形态（单反斜杠），与 json.dump 落盘后的内容一致
    _write(
        tmp_path / "runtime_config.json",
        r'{"db_path": "C:\Users\x\AppData\Local\Temp\tmpabc\m.db"}',
    )
    problems = data_guard.precheck(tmp_path)
    assert problems and "runtime_config.json" in problems[0]


def test_precheck_flags_pytest_tmpdir_style(tmp_path):
    _write(
        tmp_path / "llm_registry.json",
        '{"path": "/tmp/pytest-of-user/pytest-42/test_x0/registry.json"}',
    )
    assert data_guard.precheck(tmp_path)


def test_precheck_passes_clean_config(tmp_path):
    _write(tmp_path / "runtime_config.json", '{"db_path": "data/xinbot.db"}')
    _write(tmp_path / "llm_registry.json", '{"providers": []}')
    assert data_guard.precheck(tmp_path) == []


def test_precheck_ignores_missing_files(tmp_path):
    assert data_guard.precheck(tmp_path) == []


def test_real_runtime_config_points_into_data_dir():
    """回归锚点：真实 runtime_config.json 的 db_path 必须指向 data/。

    历史缺陷：它曾被测试的 tmp_path 覆盖成
    `...\\AppData\\Local\\Temp\\tmpXXXX\\m.db`，使应用静默使用临时数据库
    （用户真实对话历史"消失"）。指纹护栏只能发现会话期间的改动，
    这条断言直接盯住那个字段。
    """
    import json

    config_path = data_guard.DATA / "runtime_config.json"
    if not config_path.is_file():
        return  # 全新 checkout 尚无配置
    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_path = config.get("db_path", "")
    assert "data" in db_path.replace("\\", "/"), f"db_path 未指向 data/：{db_path!r}"
    assert "tmp" not in db_path.lower() and "temp" not in db_path.lower()
