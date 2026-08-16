# HEARTBEAT.md

> HEARTBEAT 是 **OpenClaw runtime 监控清单**，不是开发任务清单。

每日心跳检查项（轻量，按需轮询）：

- [ ] 今日市场数据是否成功下载入库
- [ ] 数据缺口：`data/` 有无缺失/异常
- [ ] API failure / 数据源告警
- [ ] cron / systemd timer 状态
- [ ] pending important events（待处理重要事件）
- [ ] alert backlog（告警积压）
- [ ] data freshness（数据新鲜度）
- [ ] database health（数据库健康）
- [ ] disk space（磁盘空间）

信息去向规则：

- 异常运行信息 → 写 `memory/YYYY-MM-DD.md`
- 程序原始日志 → 写 `logs/`
- 项目架构变化 → **不写这里**，写 `PROJECT_PROGRESS_LOG.md`

安静时段（23:00–08:00）除非紧急，否则保持静默。
