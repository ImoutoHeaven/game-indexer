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

## WebUI 快速启动

1) 启动 Meilisearch（任选一种）：

```bash
docker run --rm -p 7700:7700 -e MEILI_MASTER_KEY=masterKey getmeili/meilisearch:v1.7
```

```bash
meilisearch --master-key masterKey --http-addr 127.0.0.1:7700
```

2) 启动 WebUI：

```bash
python bin/web_ui.py --reload
```

3) 打开 `http://127.0.0.1:8000/setup`，设置管理员密码后登录。
4) 先进入 `Settings` 填写 Meili URL / API Key（默认 `http://127.0.0.1:7700` / `masterKey`）。保存时会直接检查连通性；如果配置已保存但连接失败，页面会明确提示这一状态。
5) 登录后的默认工作台是 `Libraries`。创建 Library（name + index uid）后，进入对应的 Library Detail 页面。
6) 在 Library Detail 页面按这个顺序完成主流程：
   - `Search Configuration`：确认当前 active search configuration（model name / use FP16 / max length）
   - `Dataset & Build`：上传 `games.txt`。上传成功后会留在当前 Library Detail 页面，并显示 `Build job queued`
   - `Recent Build`：立即查看最新 build 状态，或从当前页直接触发 `Run next queued job`
7) 队列执行是手动的，不会自动在后台消费。你可以在 Library Detail 页面直接运行队列，也可以进入 `Jobs` 页面点击 `Run next queued job`。
8) 只有状态为 `Searchable` 的 libraries 才会出现在 `Search` 页面。构建失败、仍在排队、正在构建、配置无效或 Meilisearch 不可达的 library 都不会出现在搜索下拉框里。
9) 进入 `Search` 后只需选择 library 并输入 query。WebUI 不再暴露 profile/embedder 选择，查询会自动使用该 library 当前的 active search configuration。

### WebUI Operator Notes

- 推荐操作顺序：`Settings -> Libraries -> Library Detail -> Jobs -> Search`
- 上传数据集只会创建 queued build job，不会自动执行队列
- 如果最近一次 build 失败，相关 library 不会出现在 Search 页面；先到 Library Detail 或 Jobs 查看错误摘要和日志
- 当前 MVA 仅支持未经过 Cloudflare 代理的自托管 Meilisearch。Cloudflare-proxied Meilisearch 不在这个范围内

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
- `game_web/`：Web UI 路由、模板、服务与本地数据逻辑
- `docs/manual-webui.md`：WebUI 手动验证清单
- `docs/plans/2026-02-02-webui-basic-usable.md`：WebUI 实现计划与设计说明
