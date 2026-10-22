#!/usr/bin/env python3
"""生成两套 demo 的配图。所有数据都是**实跑出来的**，不是编的。

用法: python3 demo/make_demo_figures.py

产出:
  demo/01_chinese_thesis/figures/qa_pipeline.png    质量门禁流程（结构图，无数据）
  demo/02_modern_report/figures/export_timing.png   端到端导出耗时实测（现跑现测）

耗时数据由本脚本直接调用 scripts/export.sh 测出（连续 5 次，取每次的墙钟时间），
所以重跑出来的图可能与仓库里那份略有出入——这正是它想说明的事：秒级、可复现。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
DEMO01 = ROOT / "demo" / "01_chinese_thesis"
DEMO02 = ROOT / "demo" / "02_modern_report"
DEMO03 = ROOT / "demo" / "03_english_paper"

# 中文字体：优先宋体，退到 Arial Unicode MS
plt.rcParams["font.sans-serif"] = ["Songti SC", "Arial Unicode MS", "Heiti SC"]
plt.rcParams["axes.unicode_minus"] = False

RUNS = 5


def measure_runs(demo_dir: Path, stem: str) -> list[float]:
    """实跑 export.sh，返回每次的墙钟秒数。"""
    times = []
    for i in range(RUNS):
        t0 = time.perf_counter()
        subprocess.run(
            ["bash", str(ROOT / "scripts" / "export.sh"),
             f"{stem}.md", "-r", "requirements.txt", "-o", f"/tmp/_demo_fig_{stem}.docx"],
            cwd=demo_dir, check=True, capture_output=True,
        )
        times.append(time.perf_counter() - t0)
        print(f"  {stem} 第 {i + 1}/{RUNS} 次: {times[-1]:.2f}s", file=sys.stderr)
    return times


_PIPELINE_LABELS = {
    "zh": {
        "row1": [
            ("稿件.md\n+ 格式要求.txt", "输入"),
            ("导前预检\n契约与语法", "门禁 ①"),
            ("样式模板\n要求 → styles.xml", "排版"),
            ("文档模型\nMarkdown → 节点树", "解析"),
        ],
        "row2": [
            ("原生写出器\n模型 → OOXML", "导出"),
            ("数值完整性检查\n防丢数", "门禁 ②"),
            ("逐条对账\n产物与要求", "门禁 ③"),
            ("交付 .docx", "输出"),
        ],
        "abort": "任一道门禁不通过即中止导出并指出行号，退回改稿",
    },
    "en": {
        "row1": [
            ("manuscript.md\n+ requirements.txt", "input"),
            ("Pre-flight check\ncontract and syntax", "gate 1"),
            ("Style template\nrequirements → styles.xml", "typeset"),
            ("Document model\nMarkdown → node tree", "parse"),
        ],
        "row2": [
            ("Native writer\nmodel → OOXML", "emit"),
            ("Numeric integrity\nno lost values", "gate 2"),
            ("Requirement audit\nproduct vs. spec", "gate 3"),
            ("Deliver .docx", "output"),
        ],
        "abort": "Any failing gate aborts the export and reports the line number",
    },
}

_GATE_COLORS = {"门禁 ①": "#d6e4c8", "门禁 ②": "#d6e4c8", "门禁 ③": "#d6e4c8",
                "gate 1": "#d6e4c8", "gate 2": "#d6e4c8", "gate 3": "#d6e4c8"}


def _pipeline_color(tag: str) -> str:
    if tag in _GATE_COLORS:
        return _GATE_COLORS[tag]
    return "#f7e8d6" if tag in ("输出", "output") else "#e8eef7"


def fig_qa_pipeline(out: Path, lang: str = "zh") -> None:
    """质量门禁流程示意图。结构图，不涉及任何数据。"""
    labels = _PIPELINE_LABELS[lang]
    row1 = [(text, tag, _pipeline_color(tag)) for text, tag in labels["row1"]]
    row2 = [(text, tag, _pipeline_color(tag)) for text, tag in labels["row2"]]

    BW, BH, GAP = 8.4, 4.0, 1.6
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.set_xlim(0, 4 * (BW + GAP))
    ax.set_ylim(0, 13.5)
    ax.axis("off")

    def draw_row(stages, y, x0):
        for i, (label, tag, color) in enumerate(stages):
            x = x0 + i * (BW + GAP)
            ax.add_patch(FancyBboxPatch(
                (x, y), BW, BH, boxstyle="round,pad=0.22,rounding_size=0.6",
                facecolor=color, edgecolor="#5b6b7c", linewidth=1.1,
            ))
            ax.text(x + BW / 2, y + BH * 0.62, label, ha="center", va="center",
                    fontsize=9.6, linespacing=1.5)
            ax.text(x + BW / 2, y + BH * 0.2, tag, ha="center", va="center", fontsize=9,
                    color="#2f5d3a" if tag.startswith("门禁") else "#4a5a6a")
            if i < len(stages) - 1:
                ax.add_patch(FancyArrowPatch(
                    (x + BW + 0.15, y + BH / 2), (x + BW + GAP - 0.15, y + BH / 2),
                    arrowstyle="-|>", mutation_scale=13, color="#5b6b7c", linewidth=1.2,
                ))

    draw_row(row1, 8.4, 0.6)
    draw_row(row2, 2.6, 0.6)

    # 第一行末尾折到第二行开头：走两行之间的空档，不压任何方块
    end_x = 0.6 + 3 * (BW + GAP) + BW / 2
    start_x = 0.6 + BW / 2
    ax.plot([end_x, end_x, start_x], [8.3, 7.5, 7.5],
            color="#5b6b7c", linewidth=1.2, solid_capstyle="round")
    ax.add_patch(FancyArrowPatch(
        (start_x, 7.5), (start_x, 6.72),
        arrowstyle="-|>", mutation_scale=13, color="#5b6b7c", linewidth=1.2,
    ))

    # 门禁不通过 → 退回改稿。走最底下一整行，不压任何方块。
    ax.annotate(
        "", xy=(0.9, 1.5), xytext=(3 * (BW + GAP), 1.5),
        arrowprops=dict(arrowstyle="-|>", color="#a8432f", linewidth=1.1, linestyle="--"),
    )
    ax.text(4 * (BW + GAP) / 2, 1.5, labels["abort"],
            ha="center", va="center", fontsize=9.2, color="#a8432f",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="none"))

    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)


def fig_system_architecture(out: Path) -> None:
    """五段式总体架构图（demo/01 的图 1）。结构图，不涉及任何数据。"""
    columns = [
        ("1. 规范输入与声明", "#0b7dc0", [
            "纯文本 Markdown 稿件",
            "requirements.txt 声明式规则",
            "references.bib 学术文献库",
        ]),
        ("2. 导前预检与建模", "#1f8a70", [
            "check_md 语法严格预检",
            "文档模型：块与内联节点",
            "目录域 / 分节切分",
        ]),
        ("3. 原生写出器", "#4b47d6", [
            "模型 → OOXML，无外部引擎",
            "Word 365 纯净底模映射",
            "中西文字体独立绑定",
        ]),
        ("4. OOXML 组织与编号", "#7b3fe4", [
            "三线表边框",
            "公式居中 + 编号靠右",
            "清除主题字体污染",
        ]),
        ("5. 确定性质量门禁", "#d2481f", [
            "防丢数：数值逐条对账",
            "样式审计：产物与要求",
            "规则项逐项合规验证",
        ]),
    ]

    fig, ax = plt.subplots(figsize=(13.0, 5.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(4, 86)
    ax.axis("off")

    n, gap = len(columns), 1.6
    width = (100 - 4 - gap * (n - 1)) / n
    top, head_h, body_h = 82.0, 12.0, 50.0

    for i, (title, color, bullets) in enumerate(columns):
        x = 2 + i * (width + gap)
        ax.add_patch(Rectangle((x, top - head_h), width, head_h,
                               facecolor=color, edgecolor=color, linewidth=1.4))
        ax.text(x + width / 2, top - head_h / 2, title, ha="center", va="center",
                fontsize=10.5, color="white", fontweight="bold")
        ax.add_patch(Rectangle((x, top - head_h - body_h), width, body_h,
                               facecolor="#f7f9fc", edgecolor=color, linewidth=1.4))
        for j, text in enumerate(bullets):
            ax.text(x + 0.9, top - head_h - 8.5 - j * 13, "\u00b7 " + text,
                    ha="left", va="center", fontsize=8.6, color="#243746")
        if i < n - 1:
            ax.add_patch(FancyArrowPatch(
                (x + width + 0.2, top - head_h - body_h / 2),
                (x + width + gap - 0.2, top - head_h - body_h / 2),
                arrowstyle="-|>", mutation_scale=15, color="#5b6b7c", linewidth=1.5,
            ))

    ax.add_patch(Rectangle((2, 8), 96, 10, facecolor="#eef7ee",
                           edgecolor="#3f9f7f", linewidth=1.3))
    ax.text(50, 13,
            "最终产物：规范学术 Word 文档（双线章名页眉 / 独立小写罗马页码 / 三线表 / 居中公式 / 国标参考文献）",
            ha="center", va="center", fontsize=9.6, color="#24503a")

    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)


def fig_export_timing(out: Path, thesis: list[float], report: list[float]) -> None:
    """端到端导出耗时实测：两条样例各连续跑 5 次。"""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    xs = range(1, RUNS + 1)
    ax.plot(xs, thesis, "o-", color="#2f6fbf", linewidth=2, label="学位论文样例（7 页）")
    ax.plot(xs, report, "s-", color="#3f9f7f", linewidth=2, label="技术白皮书样例（3 页）")

    for name, ys, color in (("论文", thesis, "#2f6fbf"), ("报告", report, "#3f9f7f")):
        for x, y in zip(xs, ys):
            ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=9, color=color)

    ax.set_xlabel("连续导出次序（同一份稿件，未改任何内容）")
    ax.set_ylabel("端到端耗时（秒）")
    ax.set_xticks(list(xs))
    ax.set_ylim(0, max(thesis + report) * 1.35)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)


def main() -> None:
    print("实跑测量（每条 5 次）…", file=sys.stderr)
    thesis = measure_runs(DEMO01, "thesis_sample")
    report = measure_runs(DEMO02, "report_sample")

    fig_qa_pipeline(DEMO01 / "figures" / "qa_pipeline.png")
    fig_qa_pipeline(DEMO03 / "figures" / "pipeline.png", lang="en")
    fig_system_architecture(DEMO01 / "figures" / "system_architecture.png")
    fig_export_timing(DEMO02 / "figures" / "export_timing.png", thesis, report)

    print(
        f"论文样例 中位 {sorted(thesis)[RUNS // 2]:.2f}s ｜ 报告样例 中位 "
        f"{sorted(report)[RUNS // 2]:.2f}s",
        file=sys.stderr,
    )
    print("已写出 qa_pipeline.png 与 export_timing.png", file=sys.stderr)


if __name__ == "__main__":
    main()
