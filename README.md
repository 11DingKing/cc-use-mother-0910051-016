# 文化遗产开放日排班服务

本项目是使用 Python、FastAPI 与 SQLite 实现的服务端应用，覆盖活动、场次、讲解员、主题、排班、评价、变更、预警和统计。它可在单个 Linux 应用容器内完成安装、测试、编译和接口验收，不依赖浏览器、外部数据库、缓存、消息队列或额外运行服务。

讲解词内容以**版本**管理（`app/routers/content.py`、`app/crud_content.py`）：

- 主题内容只能以版本发布，版本含**适用年龄、必讲段落、生效区间与内容哈希**；已发布版本不可修改，只能发布新版本或撤回。
- 学校确认场次时**冻结一份可核验的内容清单**（快照 JSON + SHA-256 哈希），历史冻结行只追加不改写，事后可证明每场实际讲了什么。
- 紧急勘误挂在版本上形成**勘误链**（同段新勘误取代旧勘误）：未开始场次必须逐条回应（应用/拒绝），**已结束场次证据锁定**，不再产生待办、不可改写。
- 场次改期（待审核→通过/驳回）、内容版本撤回（待重新确认）、讲解员临时替换（留痕链）、学校拒绝新版本，均有确定状态：
  已确认 / 改期待审核 / 版本撤回待重新确认 / 新版本待确认 / 学校拒绝新版本 / 勘误待回应 / 已结束证据锁定。
- 接口既能展示主题当前可用内容（`GET /api/themes/{id}/current-version`），也能按场次还原冻结清单与后续勘误链（`GET /api/sessions/{id}/content/replay`）。

## 安装

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
```

## 测试

```bash
python3 -m pytest -q
```

## 编译

```bash
python3 -m compileall -q .
```

## 接口验收

```bash
python3 -c "from app.main import app; assert len(app.routes) > 5; print(len(app.routes))"
```

## 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
