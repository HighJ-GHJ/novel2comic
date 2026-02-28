# novel2comic 目录与命名约定

本文档统一约定项目中的目录结构、标识符命名与路径规范。

---

## 1. 根目录结构

```
novel2comic/
├── configs/          # 配置模板（providers、render_profile 等，当前预留）
├── data/             # 可选，用户自建，存放原始输入（与 output 分离时使用）
├── output/           # 所有 pipeline 产物的统一根目录
├── docs/             # 文档
├── scripts/          # 独立脚本（预处理、调试）
├── src/novel2comic/  # 核心包
└── tests/            # 测试
```

### data/ 与 output/ 的职责

| 目录 | 用途 | 说明 |
|------|------|------|
| **data/** | 原始输入（可选） | 用户可自行组织，如 data/<novel_id>/raw/*.txt；非强制 |
| **output/** | 所有输出 | 脚本与 pipeline 的**唯一**输出根目录 |

建议：单本小说全流程统一使用 `output/<novel_id>/`，其下再分子目录（utf8、chapters、ch_0001 等）。

---

## 2. 标识符命名

| 标识符 | 含义 | 示例 |
|--------|------|------|
| **novel_id** | 小说唯一标识 | xuanjianxianzu、novel_demo |
| **chapter_id** | 章节标识 | ch_0001、ch_1097 |
| **shot_id** | 镜头标识 | ch_0001_shot_0000 |

**统一使用 novel_id**，不再使用 book_id。

---

## 3. output 目录结构（单本小说）

```
output/<novel_id>/
├── utf8/                    # 可选，normalize_to_utf8 输出
│   └── <原文件名>.txt
├── chapters/                # split_novel_to_chapters 输出
│   ├── front_matter.txt
│   ├── ch_0001.txt
│   ├── ch_0002.txt
│   ├── ...
│   └── chapters_index.json
├── ch_0001/                 # ChapterPack（单章）
│   ├── manifest.json
│   ├── shotscript.json
│   ├── text/
│   │   └── chapter_clean.txt
│   ├── audio/
│   ├── subtitles/
│   ├── images/
│   ├── video/
│   ├── draft/
│   └── logs/
├── ch_0002/
└── ...
```

---

## 4. 文件命名

| 类型 | 格式 | 示例 |
|------|------|------|
| 章节文件 | ch_<no>.txt，no 为 4 位数字 | ch_0001.txt、ch_1097.txt |
| 重复章节 | ch_<no>_dup<N>.txt | ch_1097_dup1.txt |
| 清洗文本 | chapter_clean.txt | ChapterPack/text/ 下 |
| 镜头脚本 | shotscript.json | ChapterPack 根目录 |

---

## 5. 脚本参数与 pipeline 一致性

| 脚本/命令 | 参数 | 说明 |
|-----------|------|------|
| split_novel_to_chapters | --novel_id | 输出到 output/<novel_id>/chapters/ |
| normalize_to_utf8 | --out_dir | 建议 output/<novel_id>/utf8 |
| prepare | --chapters_dir | output/<novel_id>/chapters |
| run | --chapter_dir | output/<novel_id>/ch_0001 |
| run | --novel_id | 可选，缺省从 chapter_dir 父目录推断 |
