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
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
DEMO01 = ROOT / "demo" / "01_chinese_thesis"
DEMO02 = ROOT / "demo" / "02_modern_report"

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


def fig_qa_pipeline(out: Path) -> None:
    """质量门禁流程示意图。结构图，不涉及任何数据。"""
    row1 = [
        ("稿件.md\n+ requirements.txt", "输入", "#e8eef7"),
        ("导前预检\ncheck_md.py", "门禁 ①", "#d6e4c8"),
        ("生成临时模板\n+ Quarto 编译", "排版", "#e8eef7"),
        ("公式居中/编号靠右\n+ 主题属性净化", "后处理", "#e8eef7"),
    ]
    row2 = [
        ("防丢数检查\npost_flight_check.py", "门禁 ②", "#d6e4c8"),
        ("产物逐条对账\naudit_export.py", "门禁 ③", "#d6e4c8"),
        ("交付 .docx", "输出", "#f7e8d6"),
    ]

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
    ax.text(4 * (BW + GAP) / 2, 1.5, "任一道门禁不通过即中止导出并指出行号，退回改稿",
            ha="center", va="center", fontsize=9.2, color="#a8432f",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="none"))

    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)


def fig_export_timing(out: Path, thesis: list[float], report: list[float]) -> None:
    """端到端导出耗时实测：两条样例各连续跑 5 次。"""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    xs = range(1, RUNS + 1)
    ax.plot(xs, thesis, "o-", color="#2f6fbf", linewidth=2, label="学位论文样例（5 页）")
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
    fig_export_timing(DEMO02 / "figures" / "export_timing.png", thesis, report)

    print(
        f"论文样例 中位 {sorted(thesis)[RUNS // 2]:.2f}s ｜ 报告样例 中位 "
        f"{sorted(report)[RUNS // 2]:.2f}s",
        file=sys.stderr,
    )
    print("已写出 qa_pipeline.png 与 export_timing.png", file=sys.stderr)


if __name__ == "__main__":
    main()
