# BGE-M3 + Meilisearch 三语游戏名语义搜索

用 CPU 版 BGE-M3 生成向量，将 `games.txt` 的行写入 Meilisearch，并提供命令行交互搜索（中/日/英均可）。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

默认会读取当前目录的 `config.json`（示例见 `config.example.json`），其中可写 Meilisearch 连接信息和常用参数；CLI 与环境变量可覆盖文件配置。可用 `-c/--config` 指定其他路径。

常用字段（config.json / 环境变量 / CLI 均可设置）：

- `meili_url` / `MEILI_URL`：Meilisearch 地址（默认 `http://127.0.0.1:7700`）
- `meili_api_key` / `MEILI_API_KEY`：API Key（默认 `masterKey`）
- `meili_index_uid` / `MEILI_INDEX_UID`：索引名（默认 `games`）
- `mode` / `MODE`：
  - `rebuild`（默认）：删除目标索引后，基于文件重建该索引
  - `append`：在现有目标索引上追加文件中的新 name（会与现有 name 去重，id 从当前最大值+1 开始）
  - `refine`：从目标索引拉取全部 name→去重→删除该索引→重建（不依赖文件）
- 其他：`bge_model_name`、`bge_use_fp16`、`encode_batch_size`、`index_batch_size`、`top_k`、`txt_path`、`debug`

## 准备数据

创建 `games.txt`，每行一个条目，允许混合多语言：

```
明日方舟 / アークナイツ / Arknights
CLANNAD -クラナド-
Steins;Gate / シュタインズ・ゲート / 命运石之门
```

## 构建索引

```bash
python bin/build_games_index.py --txt-path ./games.txt
```

常用参数：

- `--meili-url`、`--meili-api-key`、`--index-uid`
- `--mode {rebuild|append|refine}`：删除目标索引后重建 / 追加 / 从现有索引拉取→去重→删除→重建
- `--encode-batch-size`、`--index-batch-size`
- `--bge-model-name`、`--bge-use-fp16` / `--bge-use-fp32`
- `--debug`：输出调试日志

## 交互搜索

```bash
python bin/search_games.py --top-k 10
```

启动后输入查询文本并回车查看相似结果；空行或 Ctrl+C 退出。
- `--debug`：输出调试日志

## 相似度去重 / 近似重复提醒

用 BGE-M3 + Meilisearch 对任意 txt/json 或文件夹扫描结果做模糊分组，阈值内的条目会分组打印到控制台。

```bash
# 1) 从 txt 读取名称重建索引并按阈值 0.88 分组
python bin/dedupe_items.py --input list.txt --mode rebuild --threshold 0.88

# 2) 递归扫描目录，输出扫描结果为 JSON，再按时间+大小综合判定近似重复
python bin/dedupe_items.py --fs /path/to/folder --output-json scan.json --check-time --check-size --index-uid files

# 3) 使用 json 输入并追加模式，最多检索 15 个近邻
python bin/dedupe_items.py --input scan.json --mode append --top-k 15 --check-ctime
```

参数要点：
- 输入来源：`--input path`（txt 或 json）；`--fs path` 递归扫描文件，默认写出 `fs_scan.json`（可用 `--output-json` 覆盖）
- 模式：`--mode {rebuild|append}`，对应索引重建或追加（跳过同名）
- 阈值与邻居：`--threshold`（默认 0.85）、`--top-k`（默认跟随 config.top_k）
- 元数据判定开关：`--check-time`（ctime+mtime）、`--check-ctime`、`--check-mtime`、`--check-size`；时间相似度窗口由 `--time-window`（秒，默认 900）控制
- 其他通用参数：`--meili-url`、`--meili-api-key`、`--index-uid`、`--bge-model-name`、`--bge-use-fp16/--bge-use-fp32`、`--encode-batch-size`、`--index-batch-size`、`--debug`

## 目录速览

- `game_semantic/`：配置、向量生成、Meilisearch 封装、索引构建与搜索 REPL 逻辑
- `bin/`：命令行入口脚本（构建索引、交互搜索、相似度去重）
- `tests/manual.md`：手动验证步骤
- `plan-bge-m3-meili-games.md`：实现计划与设计说明
