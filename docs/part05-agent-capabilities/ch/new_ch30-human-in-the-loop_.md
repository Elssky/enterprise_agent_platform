# 第30章 Human-in-the-loop 与长任务

---

HITL（Human-in-the-loop）不是“模型不够好，所以找个人兜底”，而是把组织责任放回真正有权承担的人。生成报告草稿、查询数据和提出建议可以自动完成；发布报告、导出客户明细、修改主数据、发送外部邮件则代表业务承诺，需要由 Policy 和人工节点决定是否执行。

长任务和 HITL 经常同时出现。一份季度分析可能先跑几十分钟 SQL/Python，再等待经理数小时审批。用户可以关闭页面，服务可能重启，但任务仍应在同一个 `run_id` 上继续。把超时调大、让 SSE 一直挂着，无法解决这类问题。

**HITL 的本质是责任交接，长任务的本质是状态持久化。两者都要求 Runtime 能明确表达“为什么暂停、正在等谁、已发生什么、恢复后还能做什么”。**

## 30.1 `waiting_human`：人工审批必须成为 Runtime 状态

人工介入与普通澄清不同。澄清是补充输入，审批是授权某个动作或产物继续进入业务流程。

*表30-1：HITL 的主要目标。来源：本书整理。*

| 目标 | 人工承担什么 | 缺失后的风险 |
|---|---|---|
| 授权 | 高风险动作由有权限的人确认 | 越权自动化 |
| 质量 | 关键 Artifact 被复核 | 事实/品牌错误 |
| 合规 | 敏感数据、外发、行业要求有责任人 | 无法证明监督 |
| 学习 | 拒绝和修改沉淀为反馈样本 | 同类问题重复 |

第22章将 `waiting_human` 作为 Run 六态之一。进入该状态时，Runtime 需要同时：

- 写引擎检查点；
- 保存待审批对象和 Artifact hash；
- 推送 `approval_request`；
- 创建可幂等的审批待办；
- 停止未经批准的后续副作用。

审批通过后在**同一个 `run_id`** 恢复，而不是重新创建任务。

**一个前端“确认”按钮如果没有对应后端状态迁移、权限校验和审批记录，只是交互装饰，不是 HITL。**

## 30.2 风险分层：不是所有动作都值得打断用户

HITL 过多会把自动化重新变成人工队列；HITL 太少又会把组织责任交给模型。更合理的是按动作后果分层。

*表30-2：典型风险与人工介入方式。来源：本书整理。*

| 场景 | 推荐方式 |
|---|---|
| 只读查询、内部预览 | 自动执行 |
| 草稿生成、低风险配置 | 自动 + 可撤销 |
| 内部发布、数据导出 | 用户确认或审批 |
| 主数据修改、外部发送、高金额动作 | 正式审批链 |
| 极高风险/不可逆动作 | 默认人工执行或禁止自动化 |

常见审批模式包括：

- **前置审批**：工具执行前确认，适合付款、删除、主数据修改；
- **后置审批**：先生成草稿 Artifact，再批准发布，适合报告和邮件；
- **分级审批**：经理、法务、合规等串联/会签；
- **Reviewer Agent + 人**：自动筛低风险，高风险升级人工。

成熟系统应努力减少低价值审批，把人放在真正需要承担责任的节点。

## 30.3 审批对象：批准的是具体版本，不是一句“继续”

审批必须绑定明确对象。报告在等待期间可能被重写，数据版本也可能更新。如果审批只保存 `approved=true`，系统可能出现“批准 A、执行 B”。

一个审批请求至少应包含：

```json
{
  "approval_id": "ap-001",
  "run_id": "run-8f3a",
  "action": "publish_report",
  "artifact_ref": "mem://run-8f3a/report-v4",
  "artifact_sha256": "...",
  "policy_reason": "external_publish",
  "risk_level": "high",
  "requested_by": "report-agent",
  "expires_at": "..."
}
```

审批页应展示足够证据：影响对象、关键参数、数据来源、风险说明、允许动作、拒绝后的结果。审批人不能只看到一段模型生成的“建议说明”。

审批回调也需要校验：当前 Run 是否仍在 `waiting_human`、`approval_id` 是否匹配、审批人是否具备角色权限、Artifact hash 是否未变化。

**人工确认的是一个具体动作 + 一组具体证据 + 一个具体版本；内容变化后，旧授权原则上不能自动沿用。**

## 30.4 审批事件、幂等与恢复

SSE/事件流可以这样表达：

```text
event: state
data: {"run_id":"run-8f3a","state":"waiting_human"}

event: approval_request
data: {"approval_id":"ap-001","artifact_ref":"..."}

event: approval_result
data: {"approval_id":"ap-001","decision":"approved"}
```

审批接口示例：

```http
POST /runs/{run_id}/approvals/{approval_id}

{
  "decision": "approved",
  "comment": "口径已确认",
  "approver_id": "u-director-001"
}
```

同一 `approval_id` 的重复回调必须幂等。Runtime 重启后，如果检查点显示仍在等待，只能恢复待办，不能自动越过审批。

拒绝、取消和暂存也要有明确语义：

*表30-3：人工节点常见动作。来源：本书整理。*

| 动作 | Runtime 结果 | 说明 |
|---|---|---|
| `approved` | `waiting_human → executing` | 同一 Run 恢复 |
| `rejected` | 失败、replan 或要求修改 | 必须记录原因 |
| `cancel` | 终止未执行动作 | 已产生副作用需另做补偿 |
| `hold` | 继续 `waiting_human` | 等补充材料/转派 |

**审批恢复的核心是“继续原任务”，而不是把原任务的结果复制到一个新请求里。**

## 30.5 长任务：队列负责工作，Runtime 负责状态

超过分钟级的 SQL、Python、报告渲染或外部 A2A Task 不应长期占用同步 Worker。Runtime 可以把 Tool Call 提交到队列，Worker 只处理具体工作；RunLoop 仍然是状态机的唯一拥有者。

一个典型时间线：

```text
T0    create Run
T1    submit async SQL
T20m  SQL result ready
T23m  report artifact ready
T24m  waiting_human
T8h   approval callback
T8h+  publish report
```

SSE 可以在 T1 后断开，用户第二天重新打开页面仍能查询同一 Run。

不要为了每种等待原因不断新增 Run 状态。等待队列、等待外部 Agent 可以继续属于 `executing`，细节写在 Tool Call/Trace；只有需要人类动作时进入 `waiting_human`。这样对外生命周期保持稳定。

长任务至少区分三类时间：

- Tool 执行超时；
- Run 总预算/超时；
- 审批 SLA。

三者不能用同一个 timeout 表示。SQL 40 分钟可能异常，审批 40 分钟可能完全正常。

## 30.6 双检查点：执行恢复与业务展示服务不同读者

![图30-1：双检查点关系](../../images/part5/ch/p5-11-dual-checkpoint.png)

*图30-1：双检查点关系。来源：本书自绘。Alt text：图中并列展示引擎检查点和业务检查点；前者保存 Runtime 状态、工具结果和 Memory 引用，后者保存报告草稿、审批里程碑和展示状态，二者通过同一个 run_id 对齐。*

*表30-4：两类检查点。来源：本书整理。*

| 类型 | 主要读者 | 保存内容 | 作用 |
|---|---|---|---|
| 引擎检查点 | Runtime | state、step、tool calls、memory refs、handoff、pending approval | 崩溃恢复 |
| 业务检查点 | Console、业务、合规 | milestone、artifact、审批状态、展示摘要 | 进度、SLA、业务回放 |

只做业务里程碑，Runtime 重启后可能无法恢复；只做引擎 checkpoint，用户又不知道任务在业务上完成到了哪里。

**长任务可恢复，不等于“数据库里有个状态字段”。真正恢复的是执行上下文、Artifact、审批和外部副作用的完整位置。**

## 30.7 取消、超时、转派和替补：人工等待不能成为黑洞

用户取消任务时，Runtime 要停止未开始动作，尽力取消外部任务，并标记哪些副作用已发生。已经发送的邮件、已写入的数据不会因为 Run cancelled 自动回滚。

审批超时则由 Policy 决定：提醒、转派、升级、自动拒绝或保持等待。高风险动作不能因为无人审批就默认放行。

生产 HITL 还需要替补机制。审批人休假、离职或组织变化时，待办不能永久挂起。轮值/替补配置至少包含：角色、主责人、替补、SLA、通知渠道、升级规则。转派前仍要重新校验新审批人的权限和可见数据。

跨企业微信、飞书、Slack、邮件或工单系统的通知只是入口，真正审批结果仍必须回写同一 `approval_id`。需要记录通知已发送、回执、失败和转派，而不是把“消息送达”当成“审批完成”。

## 30.8 回放包与反馈闭环：人类判断必须留下可复用证据

高风险任务需要回答：谁批准、基于什么证据、批准了哪一版、批准后执行了什么。

业务回放包可以包含：

```json
{
  "run_id": "run-8f3a",
  "milestones": [],
  "approvals": [],
  "tool_calls": [],
  "artifacts": [{"ref": "...", "sha256": "..."}],
  "data_lineage": [],
  "policy_decisions": []
}
```

不必永久存储完整模型内部推理，真正需要长期保存的是结构化动作、参数、证据、版本、人工判断和结果。

人工拒绝、修改和补证据也是高质量评测信号，但不能简单把所有人工意见当成“模型标准答案”。一次拒绝可能来自模型错误，也可能来自策略变化、权限限制或一次性业务判断。回流样本要保留原因和适用范围。

HITL 的运营指标至少包括审批等待、超时、拒绝、转派、审批后失败和重复审批。长期稳定通过的低风险节点可以降低打断；长期被拒的动作应前移到 Planner/Policy 阶段阻断。

**人工节点不是静态安全开关，而是一条需要通过运行数据持续校准的责任流程。**

## 30.9 mini-platform 与生产验收

`projects/multi-agent-workflow/` 的基础链路应验证报告生成后进入 `waiting_human`，批准后在同一 Run 恢复：

```bash
cd mini-platform
python3 projects/multi-agent-workflow/run.py start
python3 projects/multi-agent-workflow/run.py approve
pytest tests/test_multi_agent_workflow_run.py tests/test_runtime.py -q
```

上线前至少验证：

1. 审批通过后只执行一次发布；
2. 审批拒绝有结构化原因；
3. `waiting_human` 重启后不会自动放行；
4. Artifact 改变会使旧审批失效；
5. 重复回调幂等；
6. 审批人权限变化可被发现；
7. 超时可提醒/转派/关闭；
8. 用户取消后不再启动新副作用；
9. 长任务脱离前端连接仍能恢复。

## 本章小结

HITL 是高风险 Agent 的责任机制，而不是给模型错误增加一个人工补丁。审批必须进入 Runtime 的 `waiting_human`，绑定具体动作、证据和 Artifact 版本，并在同一 `run_id` 上恢复。

长任务通过异步执行、引擎检查点和业务检查点维持连续性；取消、超时、转派和重复回调都必须有确定语义。人工反馈还应进入评测和策略校准，但不能被无差别固化成模型知识。

**一个成熟的 HITL 系统，不看有多少“确认按钮”，而看每个高风险动作能否证明：谁在什么时候、看到什么证据、以什么权限批准了哪一个版本，以及批准后系统究竟执行了什么。**

## 参考文献

Amershi, S., et al. (2014). Power to the people: The role of humans in interactive machine learning. *AI Magazine*, 35(4), 105–120.

Mosqueira-Rey, E., et al. (2023). Human-in-the-loop machine learning: A state of the art. *Artificial Intelligence Review*, 56, 3005–3054.

EU AI Act. (2024). *Regulation (EU) 2024/1689*.

NIST. (2023). *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*.

Shneiderman, B. (2022). *Human-Centered AI*. Oxford University Press.

LangChain. (n.d.). *LangGraph Human-in-the-loop*.

Temporal. (n.d.). *Workflow Persistence*.
