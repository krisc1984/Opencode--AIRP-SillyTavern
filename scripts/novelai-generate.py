#!/usr/bin/env python3
"""novelai-generate.py — 调用 NovelAI API 生成图片。支持 V4.5/V4/V3 全系列。

用法:
    python novelai-generate.py "提示词文本"
    python novelai-generate.py --file prompts.txt
    python novelai-generate.py --extract story.txt
    python novelai-generate.py --prompt "1girl, ..."
    python novelai-generate.py --queue image-queue.txt
    python novelai-generate.py -                           # stdin
    python novelai-generate.py --furry "wolf girl"
    python novelai-generate.py --background "forest"
    python novelai-generate.py -m nai-diffusion-4-5-curated -p "..."
    python novelai-generate.py --list-models

环境变量:
    NOVELAI_API_KEY  — NovelAI API 密钥 (必须)
"""

import os, sys, json, time, base64, io, re, zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# === 配置 ===
API_URL = "https://image.novelai.net/ai/generate-image"

# V3 预设参数
V3_DEFAULT_PARAMS = {
    "width": 832, "height": 1216,
    "scale": 5, "steps": 28,
    "sampler": "k_euler_ancestral", "n_samples": 1,
    "ucPreset": 0, "qualityToggle": True,
    "sm": False, "sm_dyn": False,
    "noise_schedule": "native", "cfg_rescale": 0, "seed": 0,
}

DEFAULT_NEGATIVE = (
    "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, "
    "bad anatomy, bad hands, worst quality, bad quality, jpeg artifacts, "
    "very displeasing, chromatic aberration, halftone, multiple views, logo, "
    "too many watermarks, mismatched pupils, glowing eyes, negative space, "
    "blank page, low quality, sketch, censor"
)

# 默认模型 — V4.5 Curated
MODEL = "nai-diffusion-4-5-curated"

# === 模型分类 (来自 nai-main 实测) ===
V4_MODELS = {
    "nai-diffusion-4-5-curated",       # V4.5 Curated — 最新精选
    "nai-diffusion-4-5-full",          # V4.5 Full — 最新完整
    "nai-diffusion-4-curated-preview", # V4 Curated Preview
    "nai-diffusion-4-full",            # V4 Full
}
V3_MODELS = {
    "nai-diffusion-3",                 # V3 Anime
    "nai-diffusion-furry-3",           # V3 Furry
}

AVAILABLE_MODELS = {
    "v4.5-curated":  "nai-diffusion-4-5-curated",
    "v4.5-full":     "nai-diffusion-4-5-full",
    "v4-curated":    "nai-diffusion-4-curated-preview",
    "v4-full":       "nai-diffusion-4-full",
    "v3":            "nai-diffusion-3",
    "furry":         "nai-diffusion-furry-3",
}


# ============================================================
#  参数构建器
# ============================================================

def build_v4_params(prompt: str, negative_prompt: str, params: dict, char_prompts: list = None) -> dict:
    """构建 V4/V4.5 专用的参数结构。

    V4 与 V3 完全不同:
    - 必须包含 params_version=3 和 v4_prompt 对象
    - noise_schedule 为 karras (非 native)
    - ucPreset 为 2 (非 0)
    - 支持 char_captions 多人角色
    """
    w = params.get("width", 832)
    h = params.get("height", 1216)

    return {
        "params_version": 3,
        "width": w, "height": h,
        "scale": params.get("scale", 3),
        "sampler": params.get("sampler", "k_euler_ancestral"),
        "steps": params.get("steps", 28),
        "n_samples": 1,
        "ucPreset": 2,
        "qualityToggle": True,
        "autoSmea": params.get("sm", False),
        "dynamic_thresholding": False,
        "controlnet_strength": 1,
        "legacy": False,
        "add_original_image": True,
        "cfg_rescale": params.get("cfg_rescale", 0),
        "noise_schedule": "karras",
        "legacy_v3_extend": False,
        "skip_cfg_above_sigma": None,
        "use_coords": True,
        "normalize_reference_strength_multiple": True,
        "inpaintImg2ImgStrength": 1,
        "v4_prompt": {
            "caption": {
                "base_caption": prompt,
                "char_captions": char_prompts or [],
            },
            "use_coords": True,
            "use_order": True,
        },
        "v4_negative_prompt": {
            "caption": {
                "base_caption": negative_prompt,
                "char_captions": [],
            },
            "legacy_uc": False,
        },
        "legacy_uc": False,
        "seed": params.get("seed", 0),
        "characterPrompts": char_prompts or [],
        "negative_prompt": negative_prompt,
        "deliberate_euler_ancestral_bug": False,
        "prefer_brownian": True,
        "image_format": "png",
    }


def build_v3_params(prompt: str, negative_prompt: str, params: dict) -> dict:
    """构建 V3 参数 (简单归一化)。"""
    return {
        "width": params.get("width", 832),
        "height": params.get("height", 1216),
        "scale": params.get("scale", 5),
        "sampler": params.get("sampler", "k_euler_ancestral"),
        "steps": params.get("steps", 28),
        "n_samples": 1,
        "ucPreset": params.get("ucPreset", 0),
        "qualityToggle": True,
        "sm": params.get("sm", False),
        "sm_dyn": params.get("sm_dyn", False),
        "dynamic_thresholding": False,
        "controlnet_strength": 1,
        "legacy": False,
        "add_original_image": False,
        "cfg_rescale": params.get("cfg_rescale", 0),
        "noise_schedule": "native",
        "seed": params.get("seed", 0),
        "negative_prompt": negative_prompt,
    }


def is_v4_model(model: str) -> bool:
    return model in V4_MODELS


# ============================================================
#  核心函数
# ============================================================

def load_api_key() -> str:
    key = os.environ.get("NOVELAI_API_KEY", "")
    if key:
        return key
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("NOVELAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    os.environ["NOVELAI_API_KEY"] = key
                    return key
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        for line in cwd_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("NOVELAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    os.environ["NOVELAI_API_KEY"] = key
                    return key
    return ""


def generate_image(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    model: str = MODEL,
    output_dir: str = "generated",
    char_prompts: list = None,
    **overrides
) -> Optional[Path]:
    """调用 NovelAI API 生成一张图片。自动按模型选择 V3/V4 参数结构。"""
    api_key = load_api_key()
    if not api_key:
        print("错误: 未设置 NOVELAI_API_KEY 环境变量", file=sys.stderr)
        print('  set NOVELAI_API_KEY=your_key (Windows)', file=sys.stderr)
        return None

    # 合并覆盖参数
    user_params = {**overrides}

    # 根据模型构建不同的参数结构
    if is_v4_model(model):
        parameters = build_v4_params(prompt, negative_prompt, user_params, char_prompts)
        param_label = "V4"
    else:
        parameters = build_v3_params(prompt, negative_prompt, user_params)
        param_label = "V3"

    body = {
        "input": prompt,
        "model": model,
        "parameters": parameters,
    }

    p_len = len(prompt)
    print(f'[NAI] [{param_label}] {model} | {parameters["width"]}x{parameters["height"]} | prompt {p_len} chars')

    data = json.dumps(body).encode("utf-8")
    req = Request(
        API_URL, data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://novelai.net",
            "Referer": "https://novelai.net/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )

    try:
        resp = urlopen(req, timeout=120)
    except HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"[NAI] HTTP {e.code}: {msg[:300]}", file=sys.stderr)
        if e.code == 401:
            print("[NAI] API Key 无效", file=sys.stderr)
        elif e.code == 402:
            print("[NAI] 余额/订阅不足", file=sys.stderr)
        elif e.code == 400:
            print(f"[NAI] 参数错误 — 可能需要调整 model 或 parameters", file=sys.stderr)
        return None
    except URLError as e:
        print(f"[NAI] 网络错误: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[NAI] 请求失败: {e}", file=sys.stderr)
        return None

    raw = resp.read()

    # 解析图片数据
    image_data = None
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        for name in zf.namelist():
            if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                image_data = zf.read(name)
                break
        if image_data:
            print(f"[NAI] ZIP 提取 ({len(image_data)} bytes)")
    except (zipfile.BadZipFile, Exception):
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    b = base64.b64decode(line[5:].strip())
                    if len(b) > 100:
                        image_data = b
                        break
                except Exception:
                    continue

    if not image_data and len(raw) > 100:
        image_data = raw

    if not image_data:
        print("[NAI] 未提取到图片", file=sys.stderr)
        return None

    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[\\/*?:"<>|\s]', '_', prompt[:50])[:40]
    fp = Path(output_dir) / f"nai_{ts}_{safe}.png"
    fp.write_bytes(image_data)
    print(f"[NAI] 保存: {fp.resolve()}")
    return fp


def extract_prompts(text: str) -> list[str]:
    pattern = re.compile(r'\[img:\s*(.+?)\]')
    return [m.group(1).strip() for line in text.splitlines() for m in [pattern.search(line)] if m]


# ============================================================
#  CLI
# ============================================================

def main():
    import argparse

    p = argparse.ArgumentParser(
        description="NovelAI 图片生成 — 支持 V4.5/V4/V3 全系列",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               '  python novelai-generate.py -p "1girl, school uniform"\n'
               '  python novelai-generate.py -m nai-diffusion-4-5-curated -p "...\"\n'
               "  python novelai-generate.py --furry -p \"wolf girl\"\n"
               "  python novelai-generate.py --list-models",
    )
    p.add_argument("input", nargs="?", default=None, help="提示词，或 - 表示 stdin")
    p.add_argument("-p", "--prompt", help="直接指定提示词")
    p.add_argument("-f", "--file", help="从文件读取提示词 (每行一个)")
    p.add_argument("-e", "--extract", help="从故事文件中提取 [img:...] 并生成")
    p.add_argument("-q", "--queue", help="从 image-queue.txt 读取队列")
    p.add_argument("-n", "--negative", default=DEFAULT_NEGATIVE, help="负面提示词")
    p.add_argument("-m", "--model", default=MODEL, help=f"模型 (默认: {MODEL})")
    p.add_argument("-o", "--output-dir", default="generated", help="输出目录")
    p.add_argument("-s", "--size", default="832x1216", help="尺寸 (WxH)")
    p.add_argument("--steps", type=int, default=28, help="采样步数")
    p.add_argument("--scale", type=float, default=5, help="CFG Scale")
    p.add_argument("--sampler", default="k_euler_ancestral", help="采样器")
    p.add_argument("--seed", type=int, default=0, help="种子 (0=随机)")
    p.add_argument("--no-uc", action="store_true", help="不用负面提示词")
    p.add_argument("--furry", action="store_true", help="Furry 模型 + fur dataset")
    p.add_argument("--bg", "--background", dest="background", action="store_true", help="纯场景 + background dataset")
    p.add_argument("--list-models", action="store_true", help="列出所有可用模型")
    p.add_argument("--char", "--char-prompt", dest="char_prompt", action="append", default=None,
                   help="多人角色提示词 (可多次使用, 仅 V4)")

    args = p.parse_args()

    if args.list_models:
        print("NovelAI 可用模型:")
        for name, mid in AVAILABLE_MODELS.items():
            v = "V4" if mid in V4_MODELS else "V3"
            print(f"  {name:16s} [{v}] {mid}")
        print(f"\n默认: {MODEL}")
        return

    model = args.model
    if args.furry:
        model = AVAILABLE_MODELS["furry"]

    # 尺寸
    if "x" in args.size:
        w, h = args.size.split("x")
        width, height = int(w), int(h)
    else:
        width, height = 832, 1216

    # 提示词
    prompts = []
    if args.prompt:
        prompts = [args.prompt]
    elif args.extract:
        fp = Path(args.extract)
        if not fp.exists():
            print(f"错误: {args.extract} 不存在", file=sys.stderr); sys.exit(1)
        prompts = extract_prompts(fp.read_text(encoding="utf-8"))
        print(f"提取 {len(prompts)} 条 → {args.extract}")
    elif args.queue:
        fp = Path(args.queue)
        if not fp.exists():
            print(f"错误: {args.queue} 不存在", file=sys.stderr); sys.exit(1)
        prompts = [l.strip() for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"错误: {args.file} 不存在", file=sys.stderr); sys.exit(1)
        prompts = [l.strip() for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.input == "-" or args.input is None:
        prompts = [sys.stdin.read().strip()]
    else:
        prompts = [args.input]

    if not prompts:
        print("错误: 无提示词", file=sys.stderr); sys.exit(1)

    # 前缀
    prefix = ""
    if args.furry:
        prefix = "fur dataset, "
    elif args.background:
        prefix = "background dataset, "

    negative = "" if args.no_uc else args.negative

    # char_prompts: 仅 V4 有效
    char_prompts = args.char_prompt if is_v4_model(model) else None
    if char_prompts:
        print(f"[NAI] 多人角色: {len(char_prompts)} prompts")

    results = []
    for i, prompt in enumerate(prompts, 1):
        if not prompt:
            continue
        if len(prompts) > 1:
            print(f"\n--- [{i}/{len(prompts)}] ---")
        resp = generate_image(
            prefix + prompt,
            negative_prompt=negative, model=model,
            output_dir=args.output_dir,
            char_prompts=char_prompts,
            width=width, height=height,
            steps=args.steps, scale=args.scale,
            sampler=args.sampler, seed=args.seed,
        )
        results.append((prompt, str(resp.resolve()) if resp else "FAILED"))
        if len(prompts) > 1:
            time.sleep(0.5)

    ok = sum(1 for _, r in results if r != "FAILED")
    print(f"\n{'='*50}")
    print(f"完成: {ok}/{len(results)}")
    for prompt, path in results:
        s = "OK" if path != "FAILED" else "FAIL"
        print(f"  [{s}] {prompt[:60]}... → {path}")


if __name__ == "__main__":
    main()
