# 预设管理系统开发任务清单

> 基于 `docs/preset-manager-design.md` 拆解，总计约 7-9 个工作日。

---

## Phase 1：后端基础（1-2 天）

### Task-01：创建 `preset_scanner.py` — 预设扫描器
- **优先级**：P0
- **预估工时**：4h
- **交付物**：`web-frontend/preset_scanner.py`
- **验收标准**：
  - 能递归扫描 `presets/` 目录下所有 `.json` 文件
  - 能正确解析 SillyTavern 预设格式（`prompts` 数组、`temperature`、`top_p` 等）
  - 自动过滤正则/快速回复类辅助文件（路径包含 `regex`、`quickreply`、`QR`、`快速回复`）
  - 输出 `PresetMeta` 列表，每个条目包含 `id`、`name`、`entries[]`、`params`
  - 对损坏的 JSON 文件有容错，不阻断整个扫描流程
- **依赖**：无

### Task-02：创建 `preset_config.py` — 配置管理
- **优先级**：P0
- **预估工时**：3h
- **交付物**：`web-frontend/preset_config.py`
- **验收标准**：
  - 能读写 `web-frontend/preset-config.json`
  - 支持 `load()` / `save()` / `toggle_entry()` / `reorder_entries()`
  - 配置缺失时能自动合并扫描结果作为默认值
  - 数据结构符合设计文档 3.1 节
- **依赖**：Task-01

### Task-03：改造 `airp_context.py` — 上下文组装器集成预设
- **优先级**：P0
- **预估工时**：4h
- **交付物**：修改 `web-frontend/airp_context.py`
- **验收标准**：
  - `build_context()` 中集成 `PresetScanner` 和 `PresetConfigManager`
  - 当前激活预设的 `enabled: true` 条目按 `injection_order` 排序后注入 system prompt
  - 注入位置：`memory/project.md` 之后、`memory/story_plan.md` 之前
  - 保留原有 style markdown 作为 fallback（当无激活预设时）
  - 切换预设后调用 `rebuild_context_snapshot()` 实时生效
- **依赖**：Task-01, Task-02

---

## Phase 2：API 与前端（2-3 天）

### Task-04：扩展 `server.py` 路由 — 预设 API
- **优先级**：P0
- **预估工时**：4h
- **交付物**：修改 `web-frontend/server.py`
- **验收标准**：
  - `GET /api/presets`：返回所有预设元数据 + 条目启用状态 + 当前激活预设 ID
  - `POST /api/presets/select`：切换激活预设，参数 `{ preset_id: string }`
  - `POST /api/presets/toggle`：切换条目开关，参数 `{ preset_id, entry_id, enabled }`
  - `POST /api/presets/reorder`：重排条目，参数 `{ preset_id, entry_ids: string[] }`
  - `POST /api/presets/save`：持久化当前配置到 `preset-config.json`
  - 所有 API 有基础错误处理，返回统一 JSON 格式
- **依赖**：Task-01, Task-02

### Task-05：创建 `preset-manager.html` — 管理页面
- **优先级**：P0
- **预估工时**：6h
- **交付物**：`web-frontend/preset-manager.html`
- **验收标准**：
  - 顶部：预设选择下拉/标签页，显示当前激活预设
  - 中部：条目卡片列表，每项包含：
    - Toggle 开关（启用/关闭）
    - 条目名称
    - 角色标签（System/User/Assistant）
    - 注入位置标签
    - 内容预览（折叠/展开）
    - 拖拽排序手柄（可选，Phase 2 可降级为上下移动按钮）
  - 底部：保存按钮 + 重置按钮
  - 样式复用现有 CSS 变量（`--blue`、`--bg`、`--border` 等）
  - 移动端适配（375px 宽度可用）
- **依赖**：Task-04

---

## Phase 3：集成与测试（1 天）

### Task-06：ChatView 集成 — 添加预设管理入口
- **优先级**：P1
- **预估工时**：2h
- **交付物**：修改 `app/src/views/ChatView.vue`（或对应 Web 前端入口）
- **验收标准**：
  - 聊天页面顶部或更多菜单中添加"预设管理"入口
  - 点击后跳转到 `preset-manager.html`
  - 预设切换后实时反映在对话中（无需刷新页面）
- **依赖**：Task-05

### Task-07：测试与调试
- **优先级**：P0
- **预估工时**：4h
- **交付物**：测试报告 + bug fix
- **验收标准**：
  - 扫描 100+ 预设文件耗时 < 2s（可加内存缓存优化）
  - 条目开关后，system prompt 组装结果正确
  - 与现有角色卡、世界书、记忆模块兼容（不破坏现有对话流程）
  - 边界情况测试：
    - 预设文件损坏/格式异常
    - 空 presets 目录
    - 所有条目关闭时的 fallback 行为
    - 切换预设后 context snapshot 正确重建
- **依赖**：Task-03, Task-06

---

## 可选增强（Phase 4）

### Task-08：性能优化 — 扫描结果缓存
- **优先级**：P2
- **预估工时**：2h
- **内容**：
  - 对 `preset_scanner.py` 结果做内存缓存 + 文件 mtime 校验
  - 仅当 `presets/` 目录下文件修改时间变化时重新扫描

### Task-09：Token 预算可视化
- **优先级**：P2
- **预估工时**：3h
- **内容**：
  - 在前端显示每个条目占用的 token 数量
  - 总 preset 块 token 数超过 context limit 时给出警告

---

## 任务依赖图

```
Task-01 (preset_scanner.py)
    ├── Task-02 (preset_config.py)
    │       └── Task-03 (airp_context.py 改造)
    │               └── Task-07 (测试)
    │
    └── Task-04 (server.py API)
            └── Task-05 (preset-manager.html)
                    └── Task-06 (ChatView 集成)
                            └── Task-07 (测试)

Task-08, Task-09 (可选增强)
```

---

## 当前建议执行顺序

1. **Task-01** → 先有扫描器，才能有配置和 API
2. **Task-02** → 配置管理独立，可与 Task-01 并行
3. **Task-03** → 核心改造，验证预设条目能否正确注入 system prompt
4. **Task-04** → API 层，为前端铺路
5. **Task-05** → 管理页面，可视化操作
6. **Task-06** → 集成到对话流程
7. **Task-07** → 全链路测试

---

## 关键决策点

| 决策 | 选项 | 建议 |
|------|------|------|
| 前端框架 | 原生 HTML/JS vs Vue 3 | 保持原生，与现有 `preset-manager.html` 风格一致 |
| 扫描缓存 | 每次请求扫描 vs 文件缓存 | 先实现每次扫描，Task-08 再加缓存 |
| 拖拽排序 | 原生 Drag API vs 上下按钮 | Phase 2 先用上下按钮，降低实现成本 |
| 多预设组合 | 单选 vs 多选 | 设计文档建议先单选，Task-11 后续扩展多选 |
