# 预设管理与组装系统设计文档

## 一、背景与目标

### 1.1 现状分析

当前 OpenCode AIRP SillyTavern 存在两层"预设"机制，但互不连通：

| 层级 | 位置 | 形式 | 作用 | 问题 |
|------|------|------|------|------|
| SillyTavern 预设 | `presets/*.json` | JSON | prompt 块、采样参数 | 仅 CLI  intake 时使用，Web 前端未接入 |
| 文风约束 | `skills/styles/*.md` | Markdown | 软约束 AI 输出风格 | 依赖 AI 自觉读取，无程序级保证 |

### 1.2 设计目标

1. **统一预设入口**：将 `presets/` 目录的 SillyTavern 预设接入 Web 管理页面
2. **条目级开关**：每个预设内的 prompt 块可独立启用/关闭
3. **替换文风约束**：用程序组装的预设条目替代 `skills/styles/` 软约束
4. **参考 light-tavern**：复用其成熟的 preset CRUD + toggle 交互范式

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────┐
│                   Web 前端 (Vue 3)                   │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ 预设管理页面 │  │ 对话页面     │  │ 设置页面   │  │
│  │ PresetsView │  │ ChatView     │  │ Settings   │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬─────┘  │
│         │                │                 │        │
│         └────────────────┼─────────────────┘        │
│                          │ API 调用                  │
├──────────────────────────┼──────────────────────────┤
│                  后端服务 (Python)                    │
│  ┌───────────────────────┴───────────────────────┐  │
│  │           web-frontend/server.py               │  │
│  │  ┌─────────────┐  ┌────────────────────────┐  │  │
│  │  │ 预设扫描器   │  │ 上下文组装器           │  │  │
│  │  │ preset_     │  │ context_               │  │  │
│  │  │ scanner.py  │  │ builder.py             │  │  │  │
│  │  └─────────────┘  └────────────────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────┤
│                   预设文件层                         │
│  presets/                                           │
│  ├── 预设1/                                         │
│  │   ├── 茉莉文集v0.42/                              │
│  │   │   └── 预设/*.json                            │
│  │   └── 索多玛·Peccadex V1.2.4/                    │
│  ├── 预设2/                                         │
│  └── ...                                            │
└─────────────────────────────────────────────────────┘
```

---

## 三、数据模型

### 3.1 预设条目配置（`preset-config.json`）

位于 `web-frontend/preset-config.json`，存储用户的预设启用状态：

```json
{
  "activePresetId": "preset-1-moli",
  "presets": {
    "preset-1-moli": {
      "source": "presets/预设1/茉莉文集v0.42/预设/...json",
      "enabled": true,
      "entries": {
        "prompt_main_001": {
          "enabled": true,
          "order": 1,
          "injectionPosition": 0
        },
        "prompt_nsfw_002": {
          "enabled": false,
          "order": 2,
          "injectionPosition": 0
        }
      }
    }
  },
  "globalOverrides": {
    "temperature": null,
    "maxTokens": null
  }
}
```

### 3.2 扫描得到的预设元数据（内存/缓存）

```python
@dataclass
class PresetEntry:
    id: str
    name: str
    role: str          # system / user / assistant
    content: str
    marker: bool
    enabled: bool
    injection_position: int
    injection_depth: int
    injection_order: int
    forbid_overrides: bool
    source_file: str   # 来源 JSON 路径
    preset_name: str   # 所属预设名称
```

---

## 四、核心模块设计

### 4.1 预设扫描器 (`preset_scanner.py`)

**职责**：扫描 `presets/` 目录，解析 JSON，提取可配置条目

```python
class PresetScanner:
    PRESETS_DIR = PROJECT_ROOT / "presets"

    def scan_all(self) -> list[PresetMeta]:
        """扫描所有预设文件，返回元数据列表"""
        presets = []
        for json_file in self.PRESETS_DIR.rglob("*.json"):
            # 跳过正则/快速回复类文件
            if self._is_auxiliary_file(json_file):
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                preset = self._parse_preset(data, json_file)
                presets.append(preset)
            except Exception:
                continue
        return presets

    def _parse_preset(self, data: dict, source: Path) -> PresetMeta:
        name = data.get("name") or source.stem
        entries = []
        for idx, p in enumerate(data.get("prompts", [])):
            entries.append(PresetEntry(
                id=f"{source.stem}_{idx}",
                name=p.get("name", f"Entry {idx}"),
                role=p.get("role", "system"),
                content=p.get("content", ""),
                marker=p.get("marker", False),
                enabled=True,  # 默认全启用
                injection_position=p.get("injection_position", 0),
                injection_depth=p.get("injection_depth", 4),
                injection_order=p.get("injection_order", 100),
                forbid_overrides=p.get("forbid_overrides", False),
                source_file=str(source),
                preset_name=name,
            ))
        return PresetMeta(
            id=source.stem,
            name=name,
            source=source,
            entries=entries,
            params=self._extract_params(data),
        )
```

### 4.2 预设配置管理 (`preset_config.py`)

**职责**：读写用户的启用/排序配置

```python
class PresetConfigManager:
    CONFIG_PATH = WEB_ROOT / "preset-config.json"

    def load(self) -> PresetConfig:
        """加载配置，缺失项使用扫描结果填充"""
        ...

    def save(self, config: PresetConfig) -> None:
        """保存配置"""
        ...

    def toggle_entry(self, preset_id: str, entry_id: str, enabled: bool) -> None:
        """切换单个条目状态"""
        ...

    def reorder_entries(self, preset_id: str, ordered_ids: list[str]) -> None:
        """调整条目顺序"""
        ...
```

### 4.3 上下文组装器改造 (`context_builder.py` → `airp_context.py`)

**职责**：在构建 system prompt 时，插入启用的预设条目

```python
def build_context_with_presets(
    card_id: str,
    user_message: str,
    style_content: str | None = None,
) -> dict:
    """
    新版上下文构建流程：
    1. 加载角色卡、记忆、世界书（原有逻辑）
    2. 加载 preset-config，获取当前激活预设
    3. 扫描 presets/ 目录，解析预设条目
    4. 根据配置筛选启用的条目，按 order 排序
    5. 将条目内容注入 system prompt（替代 style markdown）
    """
    # 原有逻辑
    card = get_card_payload(card_id)
    history = load_log(card_id)[-12:]
    memory = load_memory(card_id)

    # 新逻辑：加载预设条目
    config_mgr = PresetConfigManager()
    preset_config = config_mgr.load()
    scanner = PresetScanner()
    all_presets = scanner.scan_all()

    # 获取当前激活预设
    active_preset = next(
        (p for p in all_presets if p.id == preset_config.activePresetId),
        None
    )

    # 组装 preset 条目
    preset_blocks = []
    if active_preset and active_preset.enabled:
        for entry in active_preset.entries:
            entry_state = preset_config.presets.get(
                active_preset.id, {}
            ).get("entries", {}).get(entry.id, {})
            if entry_state.get("enabled", True):
                preset_blocks.append(entry.content)

    # 替换原有的 style_content 注入
    system_parts = [
        memory.get("project.md", ""),
        "\n\n".join(preset_blocks),  # ← 新：组装预设条目
        memory.get("story_plan.md", ""),
    ]

    return {
        "system": "\n\n".join(filter(None, system_parts)),
        # ... 其余字段
    }
```

### 4.4 管理页面 API (`preset_api.py`)

**职责**：为前端提供预设 CRUD + 配置接口

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

api = FastAPI()

class ToggleEntryRequest(BaseModel):
    preset_id: str
    entry_id: str
    enabled: bool

class ReorderRequest(BaseModel):
    preset_id: str
    entry_ids: list[str]

@api.get("/api/presets")
def list_presets():
    """列出所有可用预设及其条目状态"""
    scanner = PresetScanner()
    config_mgr = PresetConfigManager()
    config = config_mgr.load()
    presets = scanner.scan_all()
    # 合并配置状态
    ...

@api.post("/api/presets/select")
def select_preset(preset_id: str):
    """切换当前激活预设"""
    ...

@api.post("/api/presets/toggle")
def toggle_entry(req: ToggleEntryRequest):
    """启用/关闭单个条目"""
    ...

@api.post("/api/presets/reorder")
def reorder_entries(req: ReorderRequest):
    """调整条目顺序"""
    ...
```

---

## 五、前端页面设计

### 5.1 页面结构

```
preset-manager.html
├── 顶部导航栏
│   ├── 返回按钮
│   ├── 预设选择器（下拉/标签页）
│   └── 操作按钮（保存、重置）
├── 主内容区
│   ├── 预设卡片列表
│   │   └── 每个条目
│   │       ├── 开关 Toggle
│   │       ├── 名称
│   │       ├── 角色标签 (System/User)
│   │       ├── 注入位置标签
│   │       ├── 内容预览
│   │       └── 拖拽排序手柄
│   └── 底部操作栏
└── 底部抽屉
    └── 条目详情/编辑
```

### 5.2 交互逻辑

```javascript
// 状态管理
const state = {
  presets: [],          // 所有扫描到的预设
  activePresetId: '',   // 当前选中的预设
  entries: [],          // 当前预设的条目列表
  modified: false,      // 是否有未保存的修改
}

// 核心操作
async function loadPresets() {
  const res = await fetch('/api/presets')
  const data = await res.json()
  state.presets = data.presets
  state.activePresetId = data.activePresetId
  renderPresetTabs()
  renderEntries()
}

async function toggleEntry(entryId, enabled) {
  await fetch('/api/presets/toggle', {
    method: 'POST',
    body: JSON.stringify({ preset_id: state.activePresetId, entry_id: entryId, enabled })
  })
  state.modified = true
}

async function saveConfig() {
  await fetch('/api/presets/save', { method: 'POST' })
  state.modified = false
}
```

### 5.3 UI 组件复用 light-tavern 设计

参考 `PresetsView.vue` 的成熟组件：

| 组件 | 来源 | 用途 |
|------|------|------|
| `prompt-toggle` | PresetsView.vue | 条目开关 |
| `prompt-card` | PresetsView.vue | 条目卡片 |
| `bottom-sheet` | PresetsView.vue | 详情编辑 |
| `more-sheet` | ChatView.vue | 预设选择器 |

---

## 六、文风约束替换方案

### 6.1 替换前（当前）

```python
# web-frontend/airp_context.py
def build_context(card_id, user_message):
    settings = safe_read_json(SETTINGS_FILE, {})
    style = settings.get("style", "default")  # "双人成型"

    # 文风通过 AGENTS.md 软约束
    # AI 自行读取 skills/styles/profiles/双人成型.md
    # 无程序级保证
```

### 6.2 替换后（新方案）

```python
def build_context(card_id, user_message):
    # 1. 加载预设配置
    config = PresetConfigManager().load()
    scanner = PresetScanner()
    active_preset = scanner.get_active(config.activePresetId)

    # 2. 组装启用的条目
    preset_blocks = []
    if active_preset:
        for entry in active_preset.entries:
            if is_entry_enabled(config, entry.id):
                preset_blocks.append(entry.content)

    # 3. 注入 system prompt
    system_parts = [
        load_memory("project.md"),
        "\n\n".join(preset_blocks),  # 程序级保证
        load_memory("story_plan.md"),
    ]

    return {
        "system": "\n\n".join(filter(None, system_parts)),
        # ...
    }
```

### 6.3 映射关系

| 原方式 | 新方式 |
|--------|--------|
| `settings.json` 中 `"style": "双人成型"` | `preset-config.json` 中 `"activePresetId": "moli-v042"` |
| `skills/styles/profiles/双人成型.md` | `presets/预设1/茉莉文集v0.42/预设/*.json` 中的 prompt 块 |
| AI 自觉遵守文风规则 | 程序自动组装 prompt 块到 system prompt |

---

## 七、实现步骤

### Phase 1：后端基础（1-2 天）

1. **创建 `preset_scanner.py`**
   - 扫描 `presets/` 目录
   - 解析 JSON，提取 PresetMeta 和 PresetEntry
   - 过滤非主预设文件（正则、快速回复）

2. **创建 `preset_config.py`**
   - 读写 `preset-config.json`
   - toggle / reorder 操作

3. **改造 `airp_context.py`**
   - 集成 PresetScanner 和 PresetConfigManager
   - 在 build_context 中插入 preset blocks

### Phase 2：API 与前端（2-3 天）

4. **扩展 `server.py` 路由**
   - `GET /api/presets` - 列出预设及条目状态
   - `POST /api/presets/select` - 切换激活预设
   - `POST /api/presets/toggle` - 条目开关
   - `POST /api/presets/reorder` - 重排条目
   - `POST /api/presets/save` - 保存配置

5. **创建 `preset-manager.html`**
   - 预设选择标签页
   - 条目列表（开关、预览、排序）
   - 保存/重置按钮

### Phase 3：集成与测试（1 天）

6. **与现有流程集成**
   - 在 ChatView 添加预设管理入口
   - 确保 preset 切换实时生效

7. **测试用例**
   - 扫描 100+ 预设文件性能
   - 条目开关后 system prompt 正确性
   - 与现有角色卡、世界书兼容性

---

## 八、数据结构示例

### 8.1 原始预设 JSON（`茉莉文集v0.42.json`）

```json
{
    "temperature": 1,
    "prompts": [
        {
            "name": "(不开)┍⛓️核心预设定义✍️┑",
            "system_prompt": true,
            "role": "system",
            "content": "I will now send...\n<Molly's Biography>\n...",
            "identifier": "main",
            "injection_position": 0,
            "injection_depth": 4,
            "forbid_overrides": true,
            "injection_order": 100
        },
        {
            "name": "⚙️叙事节奏优化✒️",
            "system_prompt": true,
            "role": "system",
            "content": "Besides her delicate prose...\n<Molly's Narrative Pacing>\n...",
            "identifier": "nsfw",
            "injection_position": 0,
            "injection_depth": 4,
            "forbid_overrides": false,
            "injection_order": 100
        }
    ]
}
```

### 8.2 解析后的 PresetMeta

```python
PresetMeta(
    id="moli-v042",
    name="茉莉文集v0.42",
    source=Path("presets/预设1/茉莉文集v0.42/预设/...json"),
    entries=[
        PresetEntry(
            id="moli-v042_0",
            name="(不开)┍⛓️核心预设定义✍️┑",
            role="system",
            content="I will now send...",
            marker=False,
            enabled=True,
            injection_position=0,
            injection_depth=4,
            injection_order=100,
            forbid_overrides=True,
            source_file="presets/...",
            preset_name="茉莉文集v0.42",
        ),
        PresetEntry(
            id="moli-v042_1",
            name="⚙️叙事节奏优化✒️",
            role="system",
            content="Besides her delicate prose...",
            marker=False,
            enabled=True,
            ...
        )
    ],
    params={"temperature": 1, "top_p": 0.97, ...}
)
```

### 8.3 最终 system prompt 组装结果

```
[Memory: project.md 内容]

[Preset Entry: (不开)┍⛓️核心预设定义✍️┑]
I will now send...<Molly's Biography>...

[Preset Entry: ⚙️叙事节奏优化✒️]
Besides her delicate prose...<Molly's Narrative Pacing>...

[Memory: story_plan.md 内容]
```

---

## 九、与 light-tavern 的差异

| 维度 | light-tavern | AIRP 新方案 |
|------|--------------|-------------|
| 存储 | SQLite 数据库 | JSON 文件 + 内存 |
| 预设来源 | 用户导入/内置 | 扫描 `presets/` 目录 |
| 条目开关 | 支持 | 支持 |
| 文风约束 | 无 | 用预设条目替代 style markdown |
| 前端框架 | Vue 3 + TS | 原生 HTML/JS（可升级 Vue） |
| 上下文组装 | prompt-builder.ts | airp_context.py |

---

## 十、风险与注意事项

1. **预设文件量大**：`presets/` 目录有数百个 JSON 文件，扫描需加缓存
2. **内容安全**：预设内容直接注入 system prompt，需过滤恶意内容
3. **向后兼容**：保留 `skills/styles/` 作为 fallback，允许用户回退
4. **Token 预算**：多个 preset 条目可能超出 context limit，需做截断
5. **实时生效**：切换 preset 后应重建 context snapshot，无需重启

---

## 十一、后续扩展

- **预设组合**：允许同时启用多个预设的条目
- **条目搜索/过滤**：快速定位特定功能的 prompt 块
- **导入/导出配置**：分享预设启用配置
- **A/B 测试**：对比不同 preset 配置的生成效果
- **Token 预算可视化**：显示每个条目占用的 token 数量
