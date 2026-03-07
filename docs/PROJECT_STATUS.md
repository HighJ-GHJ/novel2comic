# novel2comic 项目状态与推进计划

本文档专门用于记录项目当前状态、已知问题、下一步执行顺序，以及隔几天后重新开始工作时的恢复入口。

建议每次在以下场景更新本文件：
- 完成一轮阶段性改造后
- 发现新的阻塞问题后
- 调整优先级或计划顺序后

---

## 1. 当前状态快照

更新时间：2026-03-08

当前代码中的真实主链路，以 `src/novel2comic/pipeline/orchestrator.py` 为准：

```text
ingest -> segment -> plan -> director_review -> anchors -> image -> tts -> align -> render -> export
```

当前实现状态：

| 阶段 | 状态 | 说明 |
|------|------|------|
| ingest | 已实现 | 初始化 ChapterPack、校验输入、写入 manifest |
| segment | 已实现 | baseline split + refine，产出 `shotscript.json` |
| plan | 已实现 | 生成 `speech` 规划 |
| director_review | 已实现 | patch-only 导演审阅，产出 `shotscript.directed.json` |
| anchors | 已实现 | 角色锚点 / 风格锚点生成 |
| image | 已实现 | 出图、链式编辑、可选 review |
| tts | 已实现 | 逐 shot / segment 合成并汇总 `chapter.wav` |
| align | 已实现 | 生成 `chapter.ass` / `chapter.srt` |
| render | 已实现 | 生成 `video/preview.mp4` |
| export | 未实现 | 调度器里预留了阶段名，但还没有实际实现 |

当前 CLI 能力：
- `novel2comic init`
- `novel2comic prepare`
- `novel2comic run --until <stage>`
- `novel2comic run --from_stage <stage> --until <stage>`

当前可移植性状态：
- 项目根目录已支持自动发现，不再依赖硬编码绝对路径
- `.env` 已支持自动发现，也支持显式覆盖
- 本地 Windows 和云服务器可以共用同一套代码


今天的本地验证结论（2026-03-08）：
- 已在 `output/validation_20260307_run1/ch_0001` 做过一次独立的 Windows 本地冒烟验证，限制前 3 个 shot
- 已实际跑通：`prepare -> segment -> plan -> director_review -> anchors -> image -> tts -> align`
- 已生成：`shotscript.json`、`shotscript.directed.json`、`audio/chapter.wav`、`subtitles/chapter.ass`、`subtitles/chapter.srt`、`images/anchors/*`、`images/shots/*`
- `image` 阶段出现 1 个质量告警：`ch_0001_shot_0002` 的 `qc_fail:size_mismatch:1368x760_expected_1664x928`
- `render` 未通过，当前阻塞点是 Windows 本地 `ffmpeg` 可执行文件在不同 shell / 子进程环境中的调用路径不一致
- 当前已确认的 Windows 本机 `ffmpeg` 路径：`C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe`
- 本次验证日志：`output/validation_20260307_run1/run.log`

核心参考文件：
- `src/novel2comic/pipeline/orchestrator.py`
- `src/novel2comic/cli.py`
- `src/novel2comic/core/io.py`
- `src/novel2comic/core/config_loader.py`

---

## 2. 已完成的关键改造

### 2.1 路径去硬编码

已经完成：
- 新增 `find_project_root()`
- 新增 `find_env_file()`
- provider / config loader / smoke 脚本已改成跟随项目上下文解析路径
- 支持环境变量覆盖：
  - `NOVEL2COMIC_PROJECT_ROOT`
  - `NOVEL2COMIC_ENV_FILE`

当前意义：
- 仓库从服务器迁移到本地 Windows 后，不需要再改死路径才能运行
- 后续换目录、换磁盘、换机器时，改动成本明显下降

### 2.2 依赖安装入口补齐

已经完成：
- 保留 `pyproject.toml` 作为主依赖声明
- 新增 `requirements.txt` 作为快速安装入口

当前意义：
- 可以继续用 `pip install -e ".[dev]"` 做标准开发安装
- 也可以用 `pip install -r requirements.txt` 快速装运行依赖

### 2.3 文档主干已与代码基本对齐

已经同步过的主文档：
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/CODE_STRUCTURE.md`
- `docs/CONFIG_REFERENCE.md`
- `docs/CHANGELOG.md`

---

## 3. 当前已知问题与风险

下面区分“明确问题”和“当前风险”，避免后面回看时混在一起。

### 3.1 明确问题

#### 问题 1：`export` 阶段尚未实现

现状：
- `src/novel2comic/pipeline/orchestrator.py` 中的 `STAGE_ORDER` 已包含 `export`
- 但调度器遇到 `export` 时会直接提示未实现并停止

影响：
- 当前完整链路实际上只能稳定跑到 `render`
- 如果后续要导出 CapCut Draft、工程包或正式长视频，还需要补一个明确的 export 方案

建议优先级：中

#### 问题 2：部分代码顶部说明已经过期

现状：
- `src/novel2comic/pipeline/orchestrator.py` 顶部注释仍写着“仅实现 ingest/segment”
- `src/novel2comic/cli.py` 顶部注释也仍是旧状态

影响：
- 新回到项目时容易被旧注释误导
- 代码真实状态与注释状态不一致

建议优先级：中

#### 问题 3：README 仍有少量文档漂移

现状：
- README 已大体整理完成
- 但快速开始部分仍保留“音频流水线”的旧表述
- 文档入口还需要持续收口

影响：
- 第一次打开仓库时，入口理解仍然可能和真实链路有轻微偏差

建议优先级：中


#### 问题 4：Windows 本地 `render` 阶段的 `ffmpeg` 调用方式还不够稳健

现状：
- 2026-03-08 的本地验证已经跑到 `render`
- 用户在自己手工打开的 PowerShell 里可以直接执行 `ffmpeg -version`
- 已确认该 PowerShell 中的可执行文件路径是：`C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe`
- 但自动化验证子进程没有继承到同一份可执行路径
- 临时定位到的 conda 缓存版 `ffmpeg.exe` 也无法稳定运行，导致 `render` 阶段失败

影响：
- 当前 Windows 本地环境下，前面的大部分 stage 已经能跑通，但 `preview.mp4` 的最后一跳仍不稳定
- `render.py` 目前依赖直接调用 `ffmpeg`，缺少更明确的可执行路径配置或预检查

建议优先级：高

### 3.2 当前风险

#### 风险 1：本地完整链路尚未完成一次成功的 `render` 验证

现状：
- 路径改造已经完成
- 2026-03-08 已用真实章节完成一次 3-shot 冒烟验证
- 当前已经确认 `prepare -> segment -> plan -> director_review -> anchors -> image -> tts -> align` 能在本地 Windows 跑通
- 剩余阻塞集中在 `render` 的 `ffmpeg` 调用链路

风险：
- 目前最后的风险主要落在 Windows 下的 `ffmpeg` 路径解析、子进程继承环境和渲染前预检查

建议优先级：高

#### 风险 2：外部 provider 的失败恢复策略还需要继续固化

现状：
- 当前已经有 manifest 和 `--from_stage` 断点续跑能力
- 但 image / tts / vlm 这类外部依赖阶段，后续仍值得补更明确的失败分类和恢复手册

风险：
- 长链路跑到中后段时，一旦失败，定位和恢复可能不够标准化

建议优先级：中

#### 风险 3：Conda 环境复现方式还不够完整

现状：
- 当前已有 `requirements.txt`
- 但还没有 `environment.yml`

风险：
- 未来换机器或重新搭环境时，仍然要手动补齐 conda 侧依赖

建议优先级：低到中

---

## 4. 下一步执行顺序

建议按下面顺序推进，不要并行分散。

### 第一步：补完本地 `render` 验证

目标：
- 基于已经产出的验证目录，把 `preview.mp4` 真正补跑出来
- 把本地 Windows 的 `ffmpeg` 可执行路径问题收口成一个可复用的运行方式

建议动作：
- 已确认 Windows 本机 `ffmpeg` 的绝对路径：`C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe`
- 让自动化运行显式使用该路径，而不是依赖 PATH 猜测
- 直接基于现有验证目录补跑：
  - `novel2comic run --chapter_dir output/validation_20260307_run1/ch_0001 --from_stage render --until render`
- 如果需要，再补一层 `render` 前的可执行路径预检查

完成标志：
- 产出 `video/preview.mp4`
- 现有验证目录可以作为本地 Windows 的标准回归样例保留下来

优先级：最高

### 第二步：清理注释与文档漂移

目标：
- 让“第一次回来看项目时”的入口信息和真实代码状态一致

建议动作：
- 修正 `orchestrator.py` 顶部说明
- 修正 `cli.py` 顶部说明
- 继续收口 README 中的旧表述
- 如有必要，补一张 “CLI -> orchestrator -> stages -> providers” 简图

完成标志：
- 顶部注释不再出现“只实现 ingest/segment”的旧描述
- README 的阶段说明和真实链路一致

优先级：高

### 第三步：梳理失败恢复和断点续跑策略

目标：
- 把“出错后如何恢复”从经验操作，变成标准操作

建议动作：
- 明确 manifest 中哪些字段是恢复判断依据
- 明确 `effective_shotscript()` 何时读取 `shotscript.directed.json`
- 为 image / tts / render 补一份恢复手册
- 评估是否需要把“可安全重跑 / 不可直接重跑”的阶段列出来

完成标志：
- 出现 provider 失败时，有固定恢复步骤
- 重跑策略不需要临场推断

优先级：中高

### 第四步：决定 `export` 阶段的真实范围

目标：
- 明确 `export` 到底要解决什么问题，而不是只保留一个占位阶段名

候选方向：
- 导出 CapCut Draft
- 导出正式发布视频
- 导出工程包 / 元数据包
- 暂时删除该阶段，只保留到 `render`

完成标志：
- `export` 要么被实现
- 要么被明确下线，不再误导

优先级：中

### 第五步：补 `environment.yml`

目标：
- 把 conda 环境复现纳入仓库，而不是只靠口头说明

完成标志：
- 新机器可以一条命令拉起 conda 环境

优先级：中

---

## 5. 隔几天后恢复工作时的检查清单

每次重新开始前，按下面顺序检查：

1. 先看本文件，确认上次停在“哪个问题”和“哪一步计划”
2. 再看 `docs/CHANGELOG.md`，确认最近一次实际改动是什么
3. 进入 conda 环境：
   - `conda activate novel2comic`
4. 检查基础命令：
   - `python --version`
   - `ffmpeg -version`
   - `pytest --version`
5. 检查 `.env` 是否存在且关键 key 已配置
6. 检查目标章节目录是否已经有历史产物：
   - `manifest.json`
   - `shotscript.json`
   - `shotscript.directed.json`
   - `audio/`
   - `subtitles/`
   - `video/`
7. 决定本次是：
   - 从头跑
   - 还是从某个阶段断点续跑
8. 工作结束后，至少同步两处：
   - 本文件
   - `docs/CHANGELOG.md`

---

## 6. 当前推荐的工作入口

如果你下一次回来想最快恢复节奏，建议优先从下面两个入口开始。

### 入口 A：排查本地运行问题

适用场景：
- 刚换机器
- 刚换环境
- 不确定本地是否能稳定跑

建议顺序：
1. 先跑到 `segment`
2. 再跑到 `render`
3. 失败后记录错误和停止阶段
4. 回填到本文档第 3 节

### 入口 B：继续工程化收口

适用场景：
- 本地链路已经基本跑通
- 下一步重点不是算法，而是维护性和可持续开发

建议顺序：
1. 清理旧注释
2. 继续补文档漂移
3. 补 `environment.yml`
4. 再决定 `export`

---

## 7. 维护规则

为了让这份文档长期有用，建议遵守下面规则：

- “当前状态”只写已经确认的事实，不写猜测
- “已知问题”只写明确问题
- “风险”单独列，不和问题混写
- “下一步执行顺序”保持最多 5 步，避免失控
- 每次完成一个重要改造后，更新时间和优先级

---


## 8. [2026-03-08] 状态更新

### 本次完成
- 在 `output/validation_20260307_run1/ch_0001` 完成了一次本地 Windows 冒烟验证
- 已确认 `prepare -> segment -> plan -> director_review -> anchors -> image -> tts -> align` 可运行
- 已落盘音频、字幕、锚点图、分镜图和验证日志

### 新发现问题
- `render` 仍卡在 `ffmpeg` 可执行文件调用链路
- `image` 阶段出现 1 个尺寸质量告警：`qc_fail:size_mismatch:1368x760_expected_1664x928`

### 计划调整
- 不再把“本地最小验证”视为完全未开始
- 下一步优先解决 `render` 的 `ffmpeg` 路径问题，并直接在现有验证目录上补跑

### 下次从哪里继续
- 从 `output/validation_20260307_run1/ch_0001` 继续
- 直接使用已确认的 `ffmpeg.exe` 路径：`C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe`
- 然后从 `render` 阶段单独重跑

---

## 9. 下次更新建议模板

可直接复制下面模板继续维护：

```markdown
## [YYYY-MM-DD] 状态更新

### 本次完成
- 

### 新发现问题
- 

### 计划调整
- 

### 下次从哪里继续
- 
```
