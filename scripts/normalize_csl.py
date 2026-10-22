#!/usr/bin/env python3
"""
normalize_csl.py — 规范化 CSL 文件：去掉 direct formatting 属性

功能：
  去掉 CSL <bibliography> 标签上的 hanging-indent / second-field-align / line-spacing 属性。
  这些属性会被 Pandoc 写入段落 direct formatting，覆盖模板样式，导致同一 requirements.txt
  在不同 CSL 下行为不一致（违反确定性原则）。

  规范化后，段落格式（悬挂缩进/行距/段间距）统一由模板 Bibliography 样式控制。

用法：
  python3 normalize_csl.py csl/apa.csl # 原地修改
  python3 normalize_csl.py csl/apa.csl -o out.csl # 输出到指定文件
  python3 normalize_csl.py csl/ # 批量处理目录下所有 .csl
  python3 normalize_csl.py csl/apa.csl --check # 只检查不修改，有问题返回非零

依赖：
  无（纯标准库）
"""

import argparse
import os
import re
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from md_to_word.utils.skill_utils import configure_logging, get_logger  # noqa: E402
logger = get_logger(__name__)

# 需要去掉的 direct formatting 属性
DIRECT_FORMAT_ATTRS = {'hanging-indent', 'second-field-align', 'line-spacing'}


def normalize_csl(input_path, output_path=None, check_only=False):
    """规范化单个 CSL 文件

    返回 (changed, removed_attrs)：
      changed: True=有修改 / False=已规范化无需改 / **None=未识别到 `<bibliography>`**，
               即这不是 CSL。「不是 CSL」与「已规范化」必须分开报——混同会把
               "没看懂这个文件"打印成 "✓ 无需修改"，调用方据此认为已核查通过。
      removed_attrs: 被去掉的属性列表
    """
    if output_path is None:
        output_path = input_path

    # 保留 XML 声明和命名空间，用文本处理更可靠
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 找 <bibliography ...> 标签
    pattern = r'(<bibliography)([^>]*)(>)'
    m = re.search(pattern, content)
    if not m:
        return None, []

    attrs_str = m.group(2)
    removed = []

    # 逐个去掉 direct formatting 属性
    new_attrs = attrs_str
    for attr in DIRECT_FORMAT_ATTRS:
        # 匹配 attr="value" 或 attr='value'
        attr_pattern = rf'\s+{re.escape(attr)}\s*=\s*["\'][^"\']*["\']'
        if re.search(attr_pattern, new_attrs):
            removed.append(attr)
            new_attrs = re.sub(attr_pattern, '', new_attrs)

    if not removed:
        return False, []

    if check_only:
        return True, removed

    # 重组标签
    new_tag = m.group(1) + new_attrs + m.group(3)
    new_content = content[:m.start()] + new_tag + content[m.end():]

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True, removed


def main():
    parser = argparse.ArgumentParser(description='规范化 CSL：去掉 direct formatting 属性')
    parser.add_argument('path', help='CSL 文件或目录路径')
    parser.add_argument('-o', '--output', help='输出文件路径（仅单文件时有效）')
    parser.add_argument('--check', action='store_true', help='只检查不修改')
    args = parser.parse_args()
    configure_logging()

    if os.path.isdir(args.path):
        # 批量处理目录
        csl_files = sorted([f for f in os.listdir(args.path) if f.endswith('.csl')])
        if not csl_files:
            logger.info(f'目录 {args.path} 下无 .csl 文件')
            sys.exit(0)

        logger.info(f'{"检查" if args.check else "处理"} {len(csl_files)} 个 CSL 文件')
        logger.info('=' * 60)
        has_issues = False
        unrecognized = []
        for fname in csl_files:
            fpath = os.path.join(args.path, fname)
            changed, removed = normalize_csl(fpath, check_only=args.check)
            if changed is None:
                unrecognized.append(fname)
                print(f' ⚠ {fname}（未找到 <bibliography>，不是 CSL？未判定，未核查）')
            elif changed:
                has_issues = True
                status = '需处理' if args.check else '已修改'
                print(f' {status}: {fname}（去掉 {", ".join(removed)}）')
            else:
                print(f' ✓ {fname}（无需修改）')
        if unrecognized:
            print(f'\n⚠️ {len(unrecognized)} 个文件未识别为 CSL（未找到 <bibliography>），'
                  f'本次**未核查**：{", ".join(unrecognized)}')
        if args.check and has_issues:
            print('\n⚠️ 发现需要规范化的 CSL，运行去掉 --check 参数执行修改')
            sys.exit(1)
        logger.info('\n完成')
    else:
        # 单文件
        if not os.path.exists(args.path):
            logger.error(f'错误: 文件不存在 {args.path}')
            sys.exit(2)
        if not args.path.endswith('.csl'):
            logger.error('错误: 不是 .csl 文件')
            sys.exit(2)

        changed, removed = normalize_csl(args.path, args.output, args.check)
        if changed is None:
            print(f'⚠ 未找到 <bibliography>，不是 CSL？未判定、未核查: {args.path}')
            sys.exit(2)
        elif changed:
            if args.check:
                print(f'需处理: {args.path}（去掉 {", ".join(removed)}）')
                sys.exit(1)
            else:
                out = args.output or args.path
                print(f'已修改: {out}（去掉 {", ".join(removed)}）')
        else:
            print(f'✓ 无需修改: {args.path}')


if __name__ == '__main__':
    main()
