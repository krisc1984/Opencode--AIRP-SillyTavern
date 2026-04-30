#!/usr/bin/env python3
"""extract-img.py — 从 RP 输出中提取 [img: ...] 提示词，输出为 NovelAI 兼容格式。
支持自动调用 NovelAI API 生成图片 (--generate)。

用法:
    python extract-img.py <输入文件>
    python extract-img.py <输入文件> --output queue.txt
    python extract-img.py <输入文件> --latest     # 只输出最新一条
    python extract-img.py <输入文件> --generate    # 提取后直接生成图片
    python extract-img.py <输入文件> -g -s 1216x832  # 生成横版图片
    echo "正文文本..." | python extract-img.py -   # 从 stdin 读取
"""

import re
import sys
import os
import subprocess
from pathlib import Path

IMG_PATTERN = re.compile(r'\[img:\s*(.+?)\]')


def extract_prompts(text: str) -> list[tuple[int, str]]:
    """提取所有 [img: ...] 行，返回 (行号, prompt内容) 列表。"""
    results = []
    for i, line in enumerate(text.split('\n'), 1):
        m = IMG_PATTERN.search(line)
        if m:
            prompt = m.group(1).strip()
            if prompt:
                results.append((i, prompt))
    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description='从 RP 输出中提取 [img: ...] 提示词')
    parser.add_argument('input', help='输入文件路径，或 - 表示从 stdin 读取')
    parser.add_argument('-o', '--output', default='image-queue.txt', help='输出文件路径 (默认: image-queue.txt)')
    parser.add_argument('-l', '--latest', action='store_true', help='只输出最新一条提示词')
    parser.add_argument('-n', '--line-numbers', action='store_true', help='输出时附带行号')
    parser.add_argument('-c', '--count', action='store_true', help='只输出提示词数量')
    parser.add_argument('-g', '--generate', action='store_true', help='提取后自动调用 NovelAI API 生成图片')
    parser.add_argument('-s', '--size', default='832x1216', help='图片尺寸 (需 --generate)')
    parser.add_argument('-m', '--model', default='nai-diffusion-4-5-curated', help='模型 (需 --generate)')
    parser.add_argument('--steps', type=int, default=28, help='采样步数')
    parser.add_argument('--scale', type=float, default=5, help='CFG Scale')
    parser.add_argument('--latest-only', action='store_true', help='--generate 时只生成最新一张')

    args = parser.parse_args()

    # 读取输入
    if args.input == '-':
        text = sys.stdin.read()
    else:
        path = Path(args.input)
        if not path.exists():
            print(f'错误: 文件不存在 — {args.input}', file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding='utf-8')

    # 提取
    prompts = extract_prompts(text)

    if args.count:
        print(f'找到 {len(prompts)} 条提示词')
        return

    if not prompts:
        print('未找到 [img: ...] 提示词', file=sys.stderr)
        sys.exit(0)

    if args.latest_only and args.generate:
        prompts = [prompts[-1]]
    elif args.latest:
        prompts = [prompts[-1]]
    
    # 先保存提取结果
    lines = []
    for line_no, prompt in prompts:
        if args.line_numbers:
            lines.append(f'[行{line_no}] {prompt}')
        else:
            lines.append(prompt)

    output_text = '\n'.join(lines)
    out_path = Path(args.output)
    out_path.write_text(output_text + '\n', encoding='utf-8')
    
    prefix = '最新 ' if args.latest else ''
    print(f'{prefix}提取到 {len(prompts)} 条提示词 → {out_path.resolve()}')
    
    if not args.generate:
        for line in lines:
            print(f'  {line}')
        return

    # 自动调用 NovelAI 生成
    print(f'\n{"="*50}')
    print('自动生成图片...')
    
    script_dir = Path(__file__).resolve().parent
    gen_script = script_dir / 'novelai-generate.py'
    
    if not gen_script.exists():
        print(f'错误: 未找到 novelai-generate.py ({gen_script})', file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable, str(gen_script),
        '-q', str(out_path.resolve()),
        '-s', args.size,
        '-m', args.model,
        '-o', str(script_dir.parent / 'generated'),
        '--steps', str(args.steps),
        '--scale', str(args.scale),
    ]
    
    result = subprocess.run(cmd, cwd=str(script_dir.parent))
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
