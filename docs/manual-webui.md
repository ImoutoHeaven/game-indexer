# WebUI 手动验证清单

以下步骤在仓库根目录执行，默认使用 `./data/` 保存 SQLite 与日志。

## 前置条件

- Python 3.11 已安装
- 依赖已安装：`pip install -r requirements.txt`
- Meilisearch 已启动（见下方启动方式）

## 快速启动

启动 Meilisearch（任选一种）：

```bash
docker run --rm -p 7700:7700 -e MEILI_MASTER_KEY=masterKey getmeili/meilisearch:v1.7
```

```bash
meilisearch --master-key masterKey --http-addr 127.0.0.1:7700
```

启动 WebUI：

```bash
python bin/web_ui.py --reload
```

打开 `http://127.0.0.1:8000/setup` 完成初始化。

## 手动验证清单

- 管理员初始化：访问 `/setup`，设置密码后跳转至 `/login`，登录成功后进入 `/libraries`。
- 退出登录：点击导航的 `Logout`，会话清除并跳转回 `/login`。
- Settings 保存：访问 `/settings`，填写 Meili URL / API Key，提交后刷新页面仍可看到已保存值。
- Library 创建：在 `/libraries` 创建 library（name + index uid），列表中可见该条目。
- Library 详情：进入 `/libraries/{id}`，确认默认 profile `bge_m3` 存在。
- Profile 追加：新增一个 profile，返回详情页能看到新增项。
- 数据集上传：在 library 详情页上传 `games.txt`，返回后在 `/jobs` 可看到一条 `build` job（状态为 queued）。
- 运行 job：在 `/jobs` 点击运行队列，job 状态从 queued -> running -> done，详情页可查看日志。
- 搜索验证：进入 `/search`，选择 library/profile，输入关键词后能看到 hits 列表。
- 数据落盘：确认 `./data/app.db` 存在；上传文件位于 `./data/uploads/<library_id>/`；日志位于 `./data/logs/jobs/`。

备注：首次运行 build job 可能会下载 BGE-M3 模型，需要等待一段时间。
