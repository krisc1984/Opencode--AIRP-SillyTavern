#!/usr/bin/env python3
"""agnes-generate.py — 调用 Agnes Image 2.1 Flash API 生成图片。

用法:
    python agnes-generate.py "提示词文本"
    python agnes-generate.py --file prompts.txt
    python agnes-generate.py -q image-queue.txt
    python agnes-generate.py -                           # stdin

环境变量:
    AGNES_API_KEY  — Agnes API 密钥 (必须)
"""

import os, sys, json, time, base64, re
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# === 配置 ===
API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
MODEL = "agnes-image-2.1-flash"

DEFAULT_SIZE = "1024x768"
DEFAULT_OUTPUT_DIR = "generated"


# ============================================================
#  核心函数
# ============================================================

def load_api_key() -> str:
    key = os.environ.get("AGNES_API_KEY", "")
    if key:
        return key
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("AGNES_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    os.environ["AGNES_API_KEY"] = key
                    return key
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        for line in cwd_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("AGNES_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    os.environ["AGNES_API_KEY"] = key
                    return key
    return ""


def build_t2i_body(prompt: str, size: str, return_base64: bool = True) -> dict:
    """构建文生图请求体。"""
    body = {
        "model": MODEL,
        "prompt": prompt,
        "size": size,
    }
    if return_base64:
        body["return_base64"] = True
    return body


def generate_image(
    prompt: str,
    size: str = DEFAULT_SIZE,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> Optional[Path]:
    """调用 Agnes Image 2.1 Flash API 生成一张图片。"""
    api_key = load_api_key()
    if not api_key:
        print("错误: 未设置 AGNES_API_KEY 环境变量", file=sys.stderr)
        print('  set AGNES_API_KEY=your_key (Windows)', file=sys.stderr)
        return None

    body = build_t2i_body(prompt, size, return_base64=True)

    print(f"[Agnes] {MODEL} | {size} | prompt {len(prompt)} chars")

    data = json.dumps(body).encode("utf-8")
    req = Request(
        API_URL, data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        },
        method="POST",
    )

    try:
        resp = urlopen(req, timeout=120)
    except HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"[Agnes] HTTP {e.code}: {msg[:300]}", file=sys.stderr)
        if e.code == 401:
            print("[Agnes] API Key 无效", file=sys.stderr)
        elif e.code == 402:
            print("[Agnes] 余额/订阅不足", file=sys.stderr)
        elif e.code == 400:
            print(f"[Agnes] 参数错误 — 检查 model/size/extra_body", file=sys.stderr)
        return None
    except URLError as e:
        print(f"[Agnes] 网络错误: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[Agnes] 请求失败: {e}", file=sys.stderr)
        return None

    raw = resp.read()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[Agnes] 响应解析失败: {raw[:200]}", file=sys.stderr)
        return None

    # 解析图片数据
    image_data = None
    data_list = result.get("data", [])
    if data_list:
        item = data_list[0]
        b64 = item.get("b64_json")
        if b64:
            try:
                image_data = base64.b64decode(b64)
            except Exception as e:
                print(f"[Agnes] Base64 解码失败: {e}", file=sys.stderr)
        url = item.get("url")
        if url and not image_data:
            try:
                req2 = Request(url, method="GET")
                with urlopen(req2, timeout=60) as resp2:
                    image_data = resp2.read()
            except Exception as e:
                print(f"[Agnes] URL 下载失败: {e}", file=sys.stderr)

    if not image_data:
        print("[Agnes] 未提取到图片", file=sys.stderr)
        return None

    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[\\/*?:"<>|\s]', '_', prompt[:50])[:40]
    fp = Path(output_dir) / f"agnes_{ts}_{safe}.png"
    fp.write_bytes(image_data)
    print(f"[Agnes] 保存: {fp.resolve()} ({len(image_data)} bytes)")
    return fp


def extract_prompts(text: str) -> list[str]:
    import re
    pattern = re.compile(r'\[img:\s*(.+?)\]')
    return [m.group(1).strip() for line in text.splitlines() for m in [pattern.search(line)] if m]


# ============================================================
#  CLI
# ============================================================

def main():
    import argparse
    import re

    p = argparse.ArgumentParser(
        description="Agnes Image 2.1 Flash 图片生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               '  python agnes-generate.py "1girl, school uniform, classroom"\n'
               '  python agnes-generate.py -f prompts.txt\n'
               '  python agnes-generate.py -q image-queue.txt',
    )
    p.add_argument("input", nargs="?", default=None, help="提示词，或 - 表示 stdin")
    p.add_argument("-p", "--prompt", help="直接指定提示词")
    p.add_argument("-f", "--file", help="从文件读取提示词 (每行一个)")
    p.add_argument("-q", "--queue", help="从 image-queue.txt 读取队列")
    p.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    p.add_argument("-s", "--size", default=DEFAULT_SIZE, help="尺寸 (WxH)")

    args = p.parse_args()

    prompts = []
    if args.prompt:
        prompts = [args.prompt]
    elif args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"错误: {args.file} 不存在", file=sys.stderr); sys.exit(1)
        prompts = [l.strip() for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.queue:
        fp = Path(args.queue)
        if not fp.exists():
            print(f"错误: {args.queue} 不存在", file=sys.stderr); sys.exit(1)
        prompts = [l.strip() for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.input == "-" or args.input is None:
        prompts = [sys.stdin.read().strip()]
    else:
        prompts = [args.input]

    if not prompts or not prompts[0]:
        print("错误: 无提示词", file=sys.stderr); sys.exit(1)

    results = []
    for i, prompt in enumerate(prompts, 1):
        if not prompt:
            continue
        if len(prompts) > 1:
            print(f"\n--- [{i}/{len(prompts)}] ---")
        resp = generate_image(prompt, size=args.size, output_dir=args.output_dir)
        results.append((prompt, str(resp.resolve()) if resp else "FAILED"))
        if len(prompts) > 1:
            time.sleep(0.5)

    ok = sum(1 for _, r in results if r != "FAILED")
    print(f"\n{'='*50}")
    print(f"完成: {ok}/{len(results)}")
    for prompt, path in results:
        s = "OK" if path != "FAILED" else "FAIL"
        print(f"  [{s}] {prompt[:60]}... → {path}")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
