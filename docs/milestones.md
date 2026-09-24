# Project milestones

These ranges follow the real, immutable commit order. An earlier maintenance pass landed the
first compare/evidence implementations before the later contract-completion commits; the ranges
below preserve that history instead of rewriting it. The commit that maintains this mapping is
administrative metadata and intentionally sits after the final functional milestone boundary.

## Milestone 1 — Reproducible Task Evaluation Foundation

- Start: `41620eb97a88f0e67a60571a629b0378348248b0`
- End: `c1e5204fd1690c162b66cbc91ef41ab8b9f7d873`
- 中文目标：建立可运行的 RepoGym MVP，完成任务规范校验、公私测试注入、参考补丁验证、候选评分、Terminal/JSON/HTML 报告，以及两个原创 Python 任务。
- 验收命令：`repogym list`；对两个任务执行 `repogym validate` 和 `repogym verify`；分别评分正确与错误 submission。
- Commits:
  - `41620eb97a88f0e67a60571a629b0378348248b0` — initial runnable toolkit
  - `c1e5204fd1690c162b66cbc91ef41ab8b9f7d873` — public repository metadata

## Milestone 2 — Task Reproducibility and Diagnostics

- Start: `83a3c0fc67baf9d8dc4c9170e7617d1fba8b9754`
- End: `ccea59b44bf0ff7aa5efee1146899d6547fe94f9`
- 中文目标：增加稳定任务指纹与环境诊断入口，使任务内容、运行环境、测试发现和依赖能够在候选执行前检查。
- 验收命令：`pytest tests/test_reproducibility.py tests/test_doctor.py`；对两个任务执行 `repogym doctor`。
- Commits:
  - `83a3c0fc67baf9d8dc4c9170e7617d1fba8b9754` — initial task fingerprints
  - `ccea59b44bf0ff7aa5efee1146899d6547fe94f9` — initial environment diagnostics

## Milestone 3 — Structured Evidence and Run Comparison

- Start: `4ca636b854cb8b80a913278a3f87ad228dc19780`
- End: `8af40b8936c68f23c452bfb81c15f2d7c9d4728d`
- 中文目标：持久化可审计的结构化执行证据，并完成两个运行结果的确定性比较；同时补齐指纹、诊断、旧结果兼容、任务一致性和指纹告警契约。
- 验收命令：`pytest tests/test_comparison.py tests/test_workflows_reports_cli.py`；执行 `repogym compare RUN_A RUN_B` 及 JSON 输出。
- Commits:
  - `4ca636b854cb8b80a913278a3f87ad228dc19780` — initial deterministic comparison
  - `38f70b291a428685c4bd07922accb2847a64b013` — initial structured evidence
  - `4f940adeb14606046a7147edcd47b52ddb79b0f5` — initial workflow documentation
  - `a665c8fbe9157b5a8ae25e0026f9bcbf91944bed` — complete task input fingerprint
  - `129e3e9f39908af88c2936926037ea267f58908c` — complete doctor diagnostics
  - `c058235ca37df8f1463f17f24e0f2e4de99522a9` — complete evidence schema
  - `8af40b8936c68f23c452bfb81c15f2d7c9d4728d` — complete comparison contract

## Milestone 4 — Security Hardening and Release Readiness

- Start: `7fcbdd805a5845bf0077763263c9809f2f98d715`
- End: `3dd6511cbed6bbb34c14fd18dfbb0da5b20391e2`
- 中文目标：加强 submission 预检、跨平台进程树终止、持久化路径脱敏与 HTML 安全，并使 README、架构、安全文档和 CI 与实现保持一致。确保任务测试使用运行 RepoGym 的同一 Python 解释器，避免环境诊断与实际执行不一致。
- 验收命令：完整执行 `ruff check .`、`ruff format --check .`、`mypy src/repogym`、覆盖率测试、解释器绑定相关测试、两个任务的 validate/verify/doctor、两个示例任务 verify、好坏 submission 比较与 HTML 报告检查，并确认正确 submission 获得 100 分。
- Commits:
  - `7fcbdd805a5845bf0077763263c9809f2f98d715` — submission preflight auditing
  - `765cc69586253478adbc2d9bacf32e509ad326cb` — process-tree timeout cleanup
  - `526514009a9c44af82d6a189aa7147454d84b4ed` — unified redaction and escaping
  - `bc931cfa725dc12c34e5d9d8b869d60e2075595d` — documentation and CI alignment
  - `674a0e1ea40312c8330a151c80c7c27c036a7d06` — scoring and milestone acceptance details
  - `285167fd6b70551b40e23d4ab1ae5608d85cbdad` — Windows workspace-root redaction fix
  - `3dd6511cbed6bbb34c14fd18dfbb0da5b20391e2` — bind generic Python task commands to the active interpreter and align doctor diagnostics
