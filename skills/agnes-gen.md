# === Agnes Image 2.1 Flash 生图指令 ===

## 你是 Agnes Image 2.1 Flash 图片生成调度器

当用户在 RP 过程中想要生成图片时，你负责：

### 1. 识别生图请求
- 用户说 "/img 生成" → 从最近的 [img: ...] 提取提示词
- 用户说 "/img 横版" → 横版 1216x832 生成
- 用户说 "/img 生成 N 张" → 批量生成 N 张
- 用户说 "/gen 提示词" → 直接用给定提示词生成

### 2. 提示词构建 (Agnes 最佳实践)

Agnes Image 2.1 Flash 更适合自然语言描述，推荐结构：

```
[主体] + [场景 / 环境] + [风格] + [光照] + [构图] + [质量要求]
```

#### 文生图提示词示例
```
日出时分薄雾峡谷上方的发光浮空城市，电影级写实风格，广角构图，丰富的建筑细节，柔和的金色光线，高视觉密度
```

#### 高信息密度图像
为复杂场景添加更多视觉层次：
```
建在悬崖上的大型奇幻港口城市，数百艘小船，层叠的石桥，发光的窗户，远山，多云的日落天空，电影级奇幻写实风格，广角构图，丰富的建筑细节，高视觉密度
```

### 3. 调用生图

使用 Bash 工具运行:
```
python scripts/agnes-generate.py -p "提示词文本"
python scripts/agnes-generate.py -p "提示词文本" -s 1216x832
python scripts/agnes-generate.py -q image-queue.txt
```

示例:
```
python scripts/agnes-generate.py -p "A luminous floating city above a misty canyon at sunrise, cinematic realism"
python scripts/agnes-generate.py -s 1216x832 -p "landscape prompt"
python scripts/agnes-generate.py -q image-queue.txt
```

### 4. 提取 + 生成（一键）

```
python scripts/extract-img.py story.txt -g
```

`extract-img.py` 默认调用 NovelAI。使用 Agnes 时，请直接调用 `agnes-generate.py` 或修改 `extract-img.py` 的生成脚本路径。

### 5. 批量生成

```
python scripts/agnes-generate.py -q image-queue.txt
```

### 6. 图生图 (支持)

Agnes 支持图生图。如需基于现有图像生成：

```
python scripts/agnes-generate.py --image-url "https://example.com/input.png" -p "Transform the scene into cyberpunk style"
```

当前脚本默认使用文生图（Base64 输出）。图生图需要在 `extra_body` 中传递 `image` 数组。

## 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-p TEXT` | - | 提示词文本 |
| `-s WxH` | `1024x768` | 尺寸 |
| `-o DIR` | `generated` | 输出目录 |
| `-q FILE` | - | 从队列文件读取提示词 |
| `-f FILE` | - | 从文件读取提示词 (每行一个) |
| `--image-url URL` | - | 图生图输入图像 URL |
| `--image-data URI` | - | 图生图输入图像 Data URI |

## 常用尺寸
- 默认: `1024x768`
- 横版风景: `1216x832` (`-s 1216x832`)
- 方形: `1024x1024` (`-s 1024x1024`)

## 提示词最佳实践

### 结构
```
[主体] + [场景 / 环境] + [风格] + [光照] + [构图] + [质量要求]
```

### 示例
- 简单场景: `A 12-year-old boy with black hair looking up at his mother, warm kitchen light, mother wearing apron, gentle smile, cozy atmosphere`
- 复杂场景: `A bustling futuristic city market filled with flying vehicles, holographic signs, dense crowds, neon lights, cinematic photorealistic style, ultra detailed, high visual density composition`
- 图生图: `Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition`

## 生成后处理
图片保存在 `generated/` 目录。
生成成功后:
1. 告知用户文件路径和文件名
2. 告知图片尺寸 (bytes)
3. 提醒用户可以手动将图片插入到正文中
4. 记录图片路径到 memory/project.md 供后续引用

## 完整工作流水线

### 标签生成 (AI 端 — 每轮自动)
```
AI 写叙事正文
    ↓
AI 回扫正文 → 提取视觉要素 → 构建自然语言提示词 ( Agnes 风格 )
    ↓
输出 [img: prompt text...]
    ↓
(无画面感的轮次跳过)
```

### 图片生成 (用户触发)
```
RP 生成含 [img: ...] 的正文
    ↓
用户: "/img 生成"
    ↓
Bash: python scripts/agnes-generate.py -p "prompt text"
    ↓
图片保存到 generated/
    ↓
用户手动插入图片到正文
```

## 常见错误与故障排除

### 1. 顶层放置 response_format 会导致错误
Agnes API 不接受顶层的 `response_format`。

错误写法:
```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "A futuristic city",
  "size": "1024x768",
  "response_format": "url"
}
```

正确写法:
```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "A futuristic city",
  "size": "1024x768",
  "return_base64": true
}
```

### 2. 图生图不需要 tags
请勿传递:
```json
{
  "tags": ["img2img"]
}
```

### 3. 图生图缺少 image 参数
图生图时 `image` 数组为必填项，需放在 `extra_body` 中。

### 4. 输入图像 URL 无法访问
如果服务器无法访问输入图像 URL，请求可能会失败。推荐使用公共 HTTPS 图像 URL，或使用 Data URI Base64 输入。

### 5. 请求超时
根据提示词复杂度、图像尺寸和服务器负载情况，图像生成可能需要几秒到几十秒不等。推荐的客户端超时时间: 60s 到 360s。
