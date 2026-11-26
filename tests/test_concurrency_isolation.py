"""并发导出时，进程级可变状态不能串味。

MCP 的 SSE/HTTP 传输会把同步工具调用分派到线程池；`md_to_word.export()` 也可能被库
调用方多线程使用。这里锁住三处曾经是模块级的状态：CSL 补丁的帧栈、模板必填项明细、
PDF 暂存路径。
"""

from __future__ import annotations

import threading
from pathlib import Path

from md_to_word.config import get_csl_dir, get_presets_dir
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.spec.parser import parse_format
from md_to_word.template.checks import _check_required_fields
from md_to_word.transform.citations import CitationEngine
from md_to_word.csl.model import _ThreadLocalList

BIB = r"""
@article{a,
  author = {Alpha, Ann},
  title = {First Article},
  journal = {Journal of Testing},
  year = {2020},
  volume = {1},
  pages = {1--2}
}

@article{b,
  author = {Beta, Bob},
  title = {Second Article},
  journal = {Journal of Testing},
  year = {2021},
  volume = {2},
  pages = {3--4}
}
"""


def _render_citations(style_name: str, lang: str) -> tuple[str, tuple[str, ...]]:
    engine = CitationEngine(BIB, get_csl_dir() / style_name, lang=lang)
    inline = "".join(text for text, _ in engine.cite([("a", "3"), ("b", "")]))
    bibliography = tuple("".join(text for text, _ in segs)
                         for _, segs in engine.bibliography_entries())
    return inline, bibliography


def test_csl_frame_stack_is_per_thread_and_rendering_matches_serial() -> None:
    """两种样式并发渲染，结果必须与各自串行渲染逐字一致。"""
    styles = (
        ("apa.csl", "en"),
        ("chinese-gb7714-2015-numeric.csl", "zh"),
    )
    expected = {style: _render_citations(style, lang) for style, lang in styles}

    results: list[tuple[str, tuple[str, tuple[str, ...]]]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def worker(style: str, lang: str) -> None:
        try:
            barrier.wait(timeout=10)
            for _ in range(3):
                results.append((style, _render_citations(style, lang)))
        except BaseException as exc:  # 线程里的异常不能悄悄消失
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=item) for item in styles for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    assert len(results) == 12
    for style, rendered in results:
        assert rendered == expected[style], f"{style} 在并发渲染时串味了"


def test_thread_local_list_keeps_threads_apart() -> None:
    frames = _ThreadLocalList()
    barrier = threading.Barrier(2)
    seen: dict[str, list] = {}

    def worker(name: str) -> None:
        frames.append([name])
        barrier.wait(timeout=10)
        seen[name] = [frames[0][0]]

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert seen == {"a": ["a"], "b": ["b"]}
    assert len(frames) == 0, "主线程不该看到工作线程的帧"


def test_required_field_details_go_only_to_the_callers_sink() -> None:
    """模板检查靠返回值带明细，不靠劫持全局 logger。

    旧实现会临时抬高 logger 级别、挂 handler；并发导出时，A 请求会收到 B 请求的明细。
    现在每条消息只写进调用方自己传进来的列表。
    """
    presets = get_presets_dir()
    zh_text = (presets / "zh-academic.txt").read_text(encoding="utf-8")
    en_text = (presets / "en-nature.txt").read_text(encoding="utf-8")
    zh_missing = "\n".join(
        line for line in zh_text.splitlines() if not line.startswith("文档标题："))
    en_missing = "\n".join(
        line for line in en_text.splitlines() if not line.startswith("Heading 1:"))

    def check(text: str, lang: str) -> tuple[bool, list[str]]:
        spec = parse_format(text, lang=lang)
        sink: list[str] = []
        has_errors, _ = _check_required_fields(spec, lang, text, sink=sink)
        return has_errors, sink

    zh_errors, zh_expected = check(zh_missing, "zh")
    en_errors, en_expected = check(en_missing, "en")
    assert zh_errors and en_errors
    assert any("文档标题" in line for line in zh_expected)
    assert any("Heading 1" in line for line in en_expected)

    results: dict[str, list[list[str]]] = {"zh": [], "en": []}
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker(name: str, text: str, lang: str) -> None:
        try:
            barrier.wait(timeout=10)
            for _ in range(5):
                _, sink = check(text, lang)
                results[name].append(sink)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("zh", zh_missing, "zh")),
        threading.Thread(target=worker, args=("en", en_missing, "en")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    assert all(sink == zh_expected for sink in results["zh"])
    assert all(sink == en_expected for sink in results["en"])


def test_pdf_staging_file_lives_next_to_the_output(tmp_path: Path, monkeypatch) -> None:
    """PDF 先写同盘临时文件再替换：跨挂载卷时 `os.replace` 不能抛 EXDEV。"""
    import md_to_word.pipeline as pipeline

    manuscript = tmp_path / "paper.md"
    manuscript.write_text("# 一\n\n正文。\n", encoding="utf-8")
    seen: dict[str, Path] = {}

    def fake_render(_src, dst):
        seen["parent"] = Path(dst).parent
        Path(dst).write_bytes(b"%PDF-1.4\n")
        return True, None

    monkeypatch.setattr(pipeline, "render_pdf_via_word", fake_render)
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "paper.docx",
        preset="zh-academic",
        make_pdf=True,
    ))

    assert result.ok, result.errors
    assert seen["parent"] == tmp_path.resolve()
    assert result.output_pdf is not None and result.output_pdf.is_file()
    assert not list(tmp_path.glob(".md-to-word-pdf-*")), "临时 PDF 必须被替换或清理"


def test_pdf_render_failure_leaves_no_hidden_temp_file(tmp_path: Path, monkeypatch) -> None:
    import md_to_word.pipeline as pipeline

    manuscript = tmp_path / "paper.md"
    manuscript.write_text("# 一\n\n正文。\n", encoding="utf-8")
    monkeypatch.setattr(pipeline, "render_pdf_via_word", lambda *_a, **_k: (False, "no-word"))

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "paper.docx",
        preset="zh-academic",
        make_pdf=True,
    ))

    assert result.returncode == 3
    assert not list(tmp_path.glob(".md-to-word-pdf-*"))
