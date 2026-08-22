# Migration Runner Specification v1

> Market Monitor schema migration runner 规格 —— R1B 交付物
> 日期：2026-08-22 ｜ **Status: SPECIFICATION — NOT IMPLEMENTED**
> 依据：R1A v2 FROZEN（Berlin approved 2026-08-22）+ DB-D029/DB-D030
> 本轮只写规格，不实现、不执行。

---

## 1. 目标

用 **Python 标准库 sqlite3** 实现可审计、幂等、可回滚的 schema migration runner：

- 不引入 Alembic / SQLAlchemy migration framework（项目零第三方依赖原则）
- migration 文件按序执行
- 每个 migration 在事务中执行
- `schema_migrations` 表记录已执行迁移
- checksum（SHA-256）校验：已执行的 migration 文件被修改 → 报错
- 已执行 migration 不重复执行
- core.db / private.db 分开运行、独立 migration history
- dry-run / plan mode
- backup gate（应用迁移前必须已有备份）
- failure rollback（事务回滚）

---

## 2. Migration 文件布局

```
docs/database/sql/migrations/
├── core/
│   ├── C0001_initial_core_schema.sql      # canonical executable source
│   └── C0002_xxx.sql                      # 未来
└── private/
    ├── P0001_initial_private_schema.sql
    └── P0002_xxx.sql                      # 未来
```

- 命名：`<DB前缀><4位序号>_<snake_case_name>.sql`
  - core → 前缀 `C`（C0001, C0002, ...）
  - private → 前缀 `P`（P0001, P0002, ...）
- 文件按 `migration_id`（去掉 `.sql` 的文件名）字典序执行。
- **Migration files are canonical executable source（DB-D029）**；
  consolidated schema（`docs/database/sql/core_schema_v1.sql` / `private_schema_v1.sql`）是
  review snapshot，由 migration 文件生成/人工核对，不反向编辑。

---

## 3. schema_migrations 表（两库各自独立，DB-D030）

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,        -- 'C0001' / 'P0001'
    checksum     TEXT    NOT NULL CHECK (length(checksum) = 64),  -- SHA-256
    applied_at   TEXT    NOT NULL,        -- UTC ISO-8601（runner 写入）
    description  TEXT,
    execution_ms INTEGER                  -- 可选：执行耗时
);
```

- core.db 与 private.db 各自拥有独立 `schema_migrations`，history 互不混淆（DB-D030）。
- `migration_id` 只含文件名主干（不含 `.sql`、不含路径）。

---

## 4. Runner 行为规格

### 4.1 连接与 PRAGMA

- 每个数据库一个 sqlite3 连接。
- 连接时执行：
  - `PRAGMA foreign_keys = ON;`（必须）
  - `PRAGMA journal_mode = WAL;`（推荐，runtime 层）
  - `PRAGMA synchronous = NORMAL;`（推荐，runtime 层）
- **runtime PRAGMA 与 schema DDL 分开记录**：PRAGMA 不进 migration 文件，由 runner 连接时设置。

### 4.2 执行流程（per database）

```
1. 打开连接，设置 PRAGMA（foreign_keys=ON; journal_mode=WAL; synchronous=NORMAL）
2. ensure schema_migrations 表存在（CREATE TABLE IF NOT EXISTS）
3. 扫描 migrations/<prefix>/ 目录，收集 *.sql，按 migration_id 排序
4. 读取已应用集合：SELECT migration_id, checksum FROM schema_migrations
5. 对每个 migration 文件：
   a. 计算 SHA-256(content)
   b. 若 migration_id 已应用：
      - checksum 一致 → SKIP（不重复执行）
      - checksum 不一致 → ERROR（已执行 migration 被修改，禁止静默重放）
   c. 若未应用：
      - dry-run/plan mode → 仅输出计划，不执行
      - 正常模式 → 进入 6（事务执行契约，见 §4.2.1）
6. 完成后输出每个 migration 的 PASS/FAIL/SKIP 汇总
```

### 4.2.1 Transaction Execution Contract（S1 修正，本轮引入）

**不变量：一个 migration 的 DDL + schema_migrations record 必须要么全部成功、要么全部不存在。严禁部分 CREATE TABLE 成功但 record 没写，或 record 已写但部分 DDL 失败。**

Python stdlib `sqlite3.executescript()` 的事务行为**不能被假定**——它会在执行脚本前隐式提交任何 pending transaction，且不会自动包裹脚本为原子事务。因此必须显式控制事务边界。

最终执行模型（唯一允许的实现方式）：

```python
# migration_sql = 从文件读取的原始内容（不含 BEGIN/COMMIT，见 §4.3）
migration_script = "BEGIN IMMEDIATE;\n" + migration_sql

# 1) BEGIN IMMEDIATE 进入 executescript；migration 文件本身不含 COMMIT
#    executescript 成功后，事务保持 open（BEGIN IMMEDIATE 由脚本内执行）
conn.executescript(migration_script)

# 2) migration record 在同一事务中写入，用 parameterized execute()
conn.execute(
    "INSERT INTO schema_migrations(migration_id, checksum, applied_at, description, execution_ms)"
    " VALUES (?, ?, ?, ?, ?)",
    (migration_id, sha256_hex, now_utc_iso, description, elapsed_ms),
)

# 3) 应用层显式 commit
conn.commit()
```

异常路径（任何一步抛错）：

```python
try:
    conn.executescript("BEGIN IMMEDIATE;\n" + migration_sql)
    conn.execute("INSERT INTO schema_migrations(...) VALUES (...)", (...))
    conn.commit()
except Exception:
    conn.rollback()
    # failure 后必须验证：
    #   a) schema_migrations 中无该 migration_id 记录
    #   b) 该 migration 创建的表/索引均不存在（查 sqlite_master）
    raise
```

事务边界说明：

| 环节 | 责任方 | 说明 |
|------|--------|------|
| 事务开始 | runner | `BEGIN IMMEDIATE` 作为 executescript 脚本前缀；文件内无 BEGIN |
| DDL 执行 | executescript | 在显式事务内执行；executescript 前无 pending transaction，故不会隐式提交破坏事务 |
| record 写入 | parameterized `execute()` | 同一事务内；用 execute 而非 executescript（避免再次隐式提交） |
| 提交 | runner `conn.commit()` | 唯一提交点 |
| 回滚 | runner `conn.rollback()` | 唯一回滚点；回滚后验证无 record、无部分 schema |

关键约束：

1. **migration 文件不得包含 COMMIT**（§4.3）——否则 DDL 中途提交，后续 DDL 与 record 脱离同一事务。
2. `executescript` 前不得存在 pending transaction（每次循环后事务已 COMMIT/ROLLBACK）。
3. 不用 `conn.execute("BEGIN")` 显式开事务（executescript 自带隐式提交语义会干扰）；
   BEGIN IMMEDIATE 必须作为脚本一部分传入 executescript。

### 4.3 Migration 文件要求（S1 复核）

- C0001 / P0001 **不含** BEGIN / COMMIT（已复核确认，符合）。
- migration 文件只包含 schema statements；**事务完全由 runner 包装**（§4.2.1）。
- 若未来 migration 文件被加入 COMMIT → runner 应在预检中检测并报错（或文档明确禁止），
  不得出现 runner 与 SQL 文件两套事务控制互相打架。

### 4.4 Checksum 语义

- checksum = SHA-256(完整文件字节)。
- 已应用 migration 的 checksum 必须与文件当前 checksum 一致；不一致 = 有人改过已应用的迁移 → **硬错误**（防止"修改历史迁移掩盖变更"）。
- 变更 schema 的正确方式：新增下一个 migration 文件（如 C0002），不改 C0001。

### 4.5 dry-run / plan mode

- 输出将执行/已执行的 migration 清单（含 checksum、状态），不触碰数据库写入。
- 用于 Berlin 审查"将要发生什么"。

### 4.6 backup gate

- 应用任何 migration 前，runner 检查备份门：
  - core.db：存在最近备份（`data/backup/core_*.db`）且通过校验（sha256 记录存在）
  - private.db：存在最近备份
- 无有效备份 → 拒绝执行（除非显式 `--no-backup-gate` 且仅用于首次建库场景，需明确授权）。
- 备份方式：`sqlite3 .backup`（在线安全）或文件级快照（需确保一致性）。

### 4.7 failure rollback

- 单个 migration 全程包在事务中；失败即 ROLLBACK。
- 事务外只有：连接 PRAGMA、schema_migrations 的 ensure（幂等）。
- 回滚后 schema_migrations 不记录该 migration（事务原子性）。

### 4.8 core/private 分开运行

- 两个命令目标：`--db core` / `--db private`（或 `--db all`）。
- 各自独立扫描目录、独立 schema_migrations、独立备份门。
- 不允许用一个连接同时迁移两库（物理分库原则）。

---

## 5. CLI 形状（规格，非实现）

```
python3 -m scripts.migrate --db core --plan        # dry-run
python3 -m scripts.migrate --db core               # 执行 core
python3 -m scripts.migrate --db private            # 执行 private
python3 -m scripts.migrate --db all --plan
python3 -m scripts.migrate --status                # 两库状态一览
```

参数：
- `--db {core,private,all}`
- `--plan`（dry-run）
- `--migrations-dir`（覆盖默认 `docs/database/sql/migrations`）
- `--db-path`（覆盖默认 `data/runtime/core.db` / `data/private/private.db`）

退出码：0 = 全部成功/无待执行；1 = 有失败；2 = checksum 冲突/配置错误。

---

## 6. 验证函数（应用层跨库校验规格，非实现）

private.db 写 core uid 引用前，应用层必须校验存在性：

| 函数 | input | query（core.db 只读） | success | failure |
|------|-------|----------------------|---------|---------|
| `ensure_entity_uid(uid)` | entity_uid TEXT(36) | `SELECT 1 FROM entities WHERE entity_uid=?` | 返回 True | 返回 False / 抛 `CrossDbReferenceError` |
| `ensure_instrument_uid(uid)` | instrument_uid TEXT(36) | `SELECT 1 FROM instruments WHERE instrument_uid=?` | True | False / error |
| `ensure_event_uid(uid)` | event_uid TEXT(36) | `SELECT 1 FROM events WHERE event_uid=?` | True | False / error |
| `ensure_analysis_uid(uid)` | analysis_uid TEXT(36) | `SELECT 1 FROM event_analysis WHERE analysis_uid=?` | True | False / error |

行为约定：
- 失败应抛出明确错误类型（如 `CrossDbReferenceError(uid, table)`），**不允许静默写入孤儿引用**。
- 格式校验（UUID regex）在此层完成；DB 只做 `CHECK(length=36)`。
- 定期孤儿检查脚本（R1 手工/脚本触发）：对比 private 引用 vs core 存在性，输出报告。

---

## 7. 测试要点（详见 r1b_test_plan_v1.md）

- 顺序执行、幂等（重复运行 SKIP）
- checksum 修改 → 报错
- 中途失败 → 回滚，schema_migrations 无记录
- dry-run 不写库
- core/private 独立 history

---

## 8. Not Done（本轮）

- ❌ 未实现 runner 代码
- ❌ 未创建任何数据库
- ❌ 未执行任何 migration
