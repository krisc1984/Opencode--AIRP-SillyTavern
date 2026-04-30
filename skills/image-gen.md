# 文生图规则详情

## 核心原则: 标签从原文提取，不是脑补

每轮叙事完成后，回扫正文，从描写中提取视觉要素翻译为 NAI 标签。

## 标签提取流程

### 第一步: 回扫正文，提取要素
写完叙事段落后，逐句扫描:
- **谁** → 出场人物的人数/性别/年龄 → `1girl`, `1boy`, `1woman`, `2characters`
- **外貌** → 发色/瞳色/体型/特征 → `black hair`, `brown eyes`, `mature`
- **衣着** → 穿什么/穿没穿 → `school uniform`, `apron`, `naked`, `lingerie`
- **动作** → 在做什么/体位 → `sitting`, `holding`, `missionary`, `doggystyle`
- **表情** → 神态/情绪 → `embarrassed`, `crying`, `moaning`, `ahegao`
- **环境** → 地点/光线/氛围 → `classroom`, `morning light`, `warm atmosphere`
- **尺度** → 是否有 NSFW → `nsfw`, `sex`

### 第二步: 翻译为英文标签
将提取的中文描写翻译为英文逗号分隔标签，按优先级排列:
```
人数 → 外貌 → 衣着 → 动作 → 表情 → 环境 → 画质
```

### 第三步: 输出
```
[img: tag1, tag2, tag3, ...]
```

### 粒度判断 (AI 自行判断)
- **简单场景** (单人肖像/简单动作): 5-8 个标签
- **复杂场景** (多人互动/NSFW 细节): 10-15 个标签
- **无人物场景**: 省略人物标签，写 `no humans` 或直接用 `background dataset` 前缀

### 触发判断
- 有画面冲击力的时刻 → 输出 [img: ...]
- 平淡叙事/纯对话 → 不输出
- 最多 2 帧 (2 行 [img: ...])

### 提取示例
```
原文: 苏晚晴解开围裙，成熟身体在晨光下泛着柔光。她蹲下身，
      手指握住那根巨大的肉棒，龟头已渗出透明前列腺液。

提取:
  人物: 1boy, 1woman, mature
  动作: squatting, holding penis
  细节: big penis, precum dripping
  氛围: morning light
  尺度: nsfw, sex

输出: [img: 1boy, 1woman, mature woman squatting, holding big penis, 
       precum dripping, morning light through window, gentle expression, 
       nsfw, sex, masterpiece, best quality]
```

## Tag 优先级 (从高到低)
1. 人数/主体: 1girl, 2girls, 1boy, 1girl1boy, solo, etc.
2. 种族/年龄: 12 years old, mature, old woman, etc.
3. 外貌: black hair, black eyes, glasses, big breasts, etc.
4. 衣着: school uniform, naked, apron, lingerie, etc.
5. 动作: sitting, standing, looking back, biting lip, etc.
6. 表情: embarrassed, angry, crying, moaning, ahegao, etc.
7. 背景/场景: classroom, bedroom, bathroom, school, etc.
8. 氛围/光线: morning light, evening, candlelight, dark, etc.
9. 画质: masterpiece, best quality, highres, detailed, etc.
10. 风格: nai4 style, realistic, anime, etc.

## NovelAI 兼容风格关键词
### 当前模型 (按推荐优先级)
| 模型 | API ID | 类型 |
|------|--------|------|
| V4.5 Curated ★ | `nai-diffusion-4-5-curated` | V4 — 最新精选，默认推荐 |
| V4.5 Full | `nai-diffusion-4-5-full` | V4 — 最新完整 |
| V4 Curated | `nai-diffusion-4-curated-preview` | V4 — 预览版精选 |
| V4 Full | `nai-diffusion-4-full` | V4 — 完整版 |
| V3 Anime | `nai-diffusion-3` | V3 — SDXL 基础 (兼容) |
| V3 Furry | `nai-diffusion-furry-3` | V3 — 毛毛风格 |

默认使用 V4.5 Curated。切换模型: `-m <API_ID>`

### 画质提升 (必有)
masterpiece, best quality, highres, absurdres, detailed

### 风格 (选1-2个)
nai4 style, anime style, anime screencap, photorealistic, semi-realistic

### 光线 (选1-2个)
morning light, sunset, golden hour, from above, from side, cinematic lighting, soft lighting

### NSFW 专属 (需要时)
nsfw, sex, from behind, from front, cowboy position, missionary, standing sex, blowjob, paizuri, cum, cum on body, cum on face, ahegao, tears, blush, sweat, wet, spread legs, looking at viewer, x-ray, see-through, internal view

## 负面提示词 (需要时告知用户)
lowres, bad anatomy, bad hands, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, deformed, disfigured, ugly, poorly drawn, fused fingers

## 多图场景
每行一个 [img: ...]，可描述同一场景的不同角度或不同角色:
```
[img: 1girl, 12 years old, black hair, school uniform, embarrassed, classroom]
[img: 1girl, 35 years old, mature, apron, worried expression, looking at boy]
```

## Tag 与自然语言双模 (V3/V4 均适用)

NovelAI 支持两种提示词模式，根据场景复杂度选择：

### Tag 模式 — 简单场景 (推荐首选)
```
[img: 1girl, black hair, school uniform, classroom, masterpiece, best quality]
```
- 逗号分隔，5-12 个 tag
- 干净、精确、token 效率高
- 适用于单人、简单场景

### 自然语言模式 — 复杂多人场景
```
[img: a 12-year-old boy with black hair looking up at his mother, warm kitchen light, mother wearing apron, gentle smile, boy holding school bag, cozy atmosphere, masterpiece, best quality]
```
- 用完整句子描述画面
- 适用于多角色、复杂构图、需要精确空间关系时
- 可以 tag + 自然语言混合

### 多人场景专用格式
```
[img: two characters, 12-year-old boy and 35-year-old woman, boy looking up, woman smiling down, warm living room, evening light through curtains, gentle atmosphere, masterpiece, best quality]
```
- 开头的数量标签用 `two characters` / `three girls` 等
- 用介词描述空间关系: looking at, sitting next to, standing behind

### 选择指南
| 场景类型 | 推荐模式 | 示例 |
|---------|---------|------|
| 单人肖像 | Tag | `1girl, school uniform, classroom` |
| 单人 + 环境 | Tag + 氛围词组 | `1girl, classroom, morning sunlight, dust particles` |
| 两人互动 | 自然语言 | `a boy talking to his teacher, classroom desk, ...` |
| 三人以上 | 自然语言 | `three women in a living room, family gathering, ...` |
| NSFW 场景 | Tag (精确) + 自然语言补充 | `nsfw, sex, 1girl, ...从后方进入的姿势...` |

## 特殊风格模式

### Furry 模式 (毛毛/兽人)
在 prompt 最前面加 `fur dataset, `:
```
[img: fur dataset, 1girl, wolf ears, tail, school uniform, ...]
```
生成时加 `--furry` 标志会自动切换模型并添加前缀。

### Background 模式 (纯场景/风景)
在 prompt 最前面加 `background dataset, `:
```
[img: background dataset, classroom interior, morning sunlight, desks, blackboard, ...]  
```
生成时加 `--background` 标志会自动添加前缀。
适用于不需要人物的场景描写、定场镜头。

## 性爱场景特殊要求
- 必须使用 nsfw 和 sex tag
- 达成透视效果: 使用 x-ray, see-through, internal view
- 性器官详细刻画: penis, big penis, veins, testicles, pussy, labia, etc.
- 体液: cum, precum, pussy juice, sweat, tears
- 体位: 具体体位名称如 missionary, doggystyle, cowgirl position 等
- 表情: ahegao, moaning, crying, blush, rolled eyes, tongue out

## Routine de travail utilisateur
1. AI 输出正文 + [img: ...] 标签
2. 保存本轮输出到文本文件 (或直接使用已有的 RP 记录)
3. 运行提取: `python scripts/extract-img.py <文本文件>`
4. 运行生成: `python scripts/novelai-generate.py -q image-queue.txt`
5. 或一键: `python scripts/extract-img.py <文本文件> -g`
6. 生成的图片保存在 `generated/` 目录
7. 将图片插入到正文对应位置

### 常用参数
```bash
# 竖版默认
python scripts/novelai-generate.py -p "prompt"

# 横版风景
python scripts/novelai-generate.py -s 1216x832 -p "prompt"

# 毛毛风格
python scripts/novelai-generate.py --furry -p "wolf girl, ..."

# 纯风景
python scripts/novelai-generate.py --background -p "sunset over ocean"

# 列出可用模型
python scripts/novelai-generate.py --list-models
```
