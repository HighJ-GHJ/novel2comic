# novel2comic 变更日志（CHANGELOG）

本文档记录项目的重大变更，便于版本控制与思路演进追溯。每次大改动请在此追加条目。

---

## 变更记录格式说明

每次变更请按以下结构书写：

```markdown
## [日期] 变更标题

### 背景 / 动机
（为何要做这次变更）

### 变更内容
（具体改了哪些文件、逻辑）

### 影响范围
（对现有功能、下游模块的影响）

### 后续待办
（如有）
```

---

## [2026-02-28] 架构重构：依赖修正、CLI 增强、Segment 接入

### 背景 / 动机

架构审查发现若干问题：
1. **依赖方向错误**：`core/split_baseline.py` 依赖 `skills/refine_shot_split/schema.Shot`，基础层依赖业务层，违反依赖倒置
2. **CLI 硬编码**：`novel_id` 固定为 `"novel_001"`，多书场景不便
3. **流水线断裂**：`split_novel_to_chapters` 输出与 ChapterPack 之间无自动化衔接，需手动复制
4. **Refine 约束过严**：短章（如 1700 字）baseline 仅 15–20 shot，无法满足 min_shots=60，导致 refine 必然回退
5. **Segment 占位**：只写出空 shots，未接入 baseline + refine
6. **依赖缺失**：`python-dotenv` 未在 pyproject.toml 声明

### 变更内容

| 模块 | 变更 |
|------|------|
| **core/schemas/** | 新建 `core/schemas/shot.py`，定义 `Shot` 数据结构；core 定义，skills 使用 |
| **core/split_baseline.py** | 改为 `from novel2comic.core.schemas import Shot`，移除对 skills 的依赖 |
| **skills/refine_shot_split/schema.py** | `Shot` 改为从 `novel2comic.core.schemas` 导入；保留 `Constraints`、`Patch` |
| **skills/refine_shot_split/validator.py** | `validate_count_range` 新增 `effective_min`、`effective_max` 参数，支持短章放宽约束 |
| **skills/refine_shot_split/skill.py** | 计算 `effective_min = min(c.min_shots, len(base_shots))`，传入 validator |
| **pyproject.toml** | 添加 `python-dotenv>=1.0`；新增 `[project.optional-dependencies] dev = ["pytest>=7.0"]` |
| **cli.py** | `run` 增加 `--novel_id`，缺省从 `chapter_dir` 父目录推断；新增 `prepare` 子命令 |
| **stages/segment.py** | 接入 `split_baseline` + `RefineShotSplitSkill`；LLM 不可用时回退 baseline；输出真实 shots 到 shotscript.json |
| **tests/** | 新建 `test_core.py`、`test_skills.py`、`test_pipeline.py`，共 10 个用例 |

### 影响范围

- **向后兼容**：`skills` 内 `from .schema import Shot` 仍可用（schema 重新导出）
- **debug_refine_split.py**：无需修改，继续使用 `schema.Shot`、`schema.Constraints`
- **新增命令**：`novel2comic prepare --chapters_dir ... [--chapter ch_0001]` 可从 chapters 批量创建 ChapterPack

### 后续待办

- plan / tts / align / image / render / export 各阶段实现
- 考虑为 LLM Provider 定义 Protocol 抽象

---

## [历史] 项目初始化与前期实现

（根据 `docs/ARCHITECTURE.md` 第 7 节「当前实现状态」整理）

### 已完成

- 项目目录架构、CLI（init/run）、pipeline 框架
- 输入编码：GB18030 → UTF-8
- 章节切分：`split_novel_to_chapters.py`，按章节号命名 ch_0001.txt 等
- 章节缩进规范化：`normalize_chapter_indent.py`
- baseline split + refine_shot_split skill（含 SiliconFlow LLM 接入）
- IngestStage、SegmentStage（占位版）

### 脚本与输出

- `scripts/normalize_to_utf8.py`：任意编码 → UTF-8
- `scripts/split_novel_to_chapters.py`：整本 → chapters
- `scripts/normalize_chapter_indent.py`：段首缩进统一
- `scripts/debug_refine_split.py`：调试 baseline + refine
- 输出：`output/<book_id>/chapters/ch_*.txt`、`chapters_index.json`

---

---

## [2026-02-28] 目录与命名约定统一

### 背景 / 动机

架构审查发现 data/output、book_id/novel_id 混用，文档与实现不一致。

### 变更内容

| 项目 | 变更 |
|------|------|
| **configs/** | 新建目录，README 说明预留用途 |
| **scripts/split_novel_to_chapters.py** | `--book_id` 改为 `--novel_id`，默认 `novel_demo` |
| **docs/NAMING_CONVENTIONS.md** | 新建，统一目录结构、标识符、路径约定 |
| **docs/CONFIG_REFERENCE.md** | 统一 output/<novel_id>/ 路径；normalize_to_utf8 示例更新 |
| **scripts/normalize_to_utf8.py** | 示例路径改为 output/<novel_id>/utf8 |
| **tests/test_scripts.py** | 新增 split_novel_to_chapters --novel_id 测试 |

### 影响范围

- **向后不兼容**：`--book_id` 已移除，旧脚本需改为 `--novel_id`
- 文档与实现一致

### 后续待办

- 无

---

*后续变更请在此文件末尾追加新条目。*
