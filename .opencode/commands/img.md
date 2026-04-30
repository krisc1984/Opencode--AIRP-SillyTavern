# /img

生图命令。

- `/img 生成`：读取当前卡 `rp-log.txt` 中最新 `[img: ...]`，调用 `scripts/extract-img.py` 或通过 Web `/api/image-gen` 入队。
- `/img 全部`：处理所有未生成的 `[img: ...]`。
- `/img 横版`：使用横版尺寸。
- `/img furry`：使用 furry 模型。

优先使用 Web 前端气泡下方的“生成插图”按钮，因为新版 Web 已实现异步队列、loading 和失败重试。
