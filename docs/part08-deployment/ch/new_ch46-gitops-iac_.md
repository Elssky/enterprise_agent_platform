# 第46章 GitOps、IaC 与边缘推理

---

一次生产故障排查结束后，运维人员忘了撤回临时 `kubectl edit`。几天后，staging 与 prod 的网关配置已经不一致：模型 backend、租户白名单和灰度比例都发生漂移。测试环境通过的发布，到了生产却表现不同，复盘时也找不到对应 PR。

**手工部署最大的风险不是慢，而是状态不可复现：谁改了什么、何时生效、现在与期望状态是否一致，说不清。** GitOps 和 IaC 的目标，是把 GPU 节点池、模型服务、网关策略、密钥引用和边缘模型都放进声明式变更链路，让 Promotion、漂移检测、回滚和审计拥有同一版本锚点。

第43章提供算力，第44章提供模型服务，第45章提供统一调用入口，本章回答这些能力如何进入 dev、staging、prod 和边缘节点，并在长期运行中保持可复现。

---

## 46.1 GitOps：生产状态由 Git 声明，而不是由操作历史决定

企业 Agent 平台常经历三阶段：

1. SSH 到 GPU 机器手工启动服务；
2. Kubernetes + Helm，但仍由人执行 `kubectl apply`；
3. Git 声明期望状态，控制器持续 reconcile，生产变更通过 PR 和受控 Sync 进入集群。

![图46-1：GitOps 把部署从「操作机器」变成「合并 PR」](../../images/part8/ch/ch46-01.png)

*图46-1：GitOps 把部署从「操作机器」变成「合并 PR」。来源：本书自绘。Alt text：左侧"手工部署"直接 SSH 改配置无记录，右侧"GitOps"通过 PR 变更声明式配置、CI 校验后自动同步，对比凸显部署从操作变为代码审查。*

GitOps 的核心可以概括为四条：

- **声明式**：期望状态由 YAML/HCL 等描述；
- **Git 为 SSOT**：长期有效的生产配置必须能在 Git 中找到；
- **持续 reconcile**：控制器比较期望状态与实际状态；
- **漂移可见**：OutOfSync 是运行信号，不是普通噪音。

**把 YAML 放进 Git 但仍手工部署，不算完成 GitOps。** 如果集群状态仍取决于谁最后执行了一次命令，Git 只是备份，不是控制面。

### GitOps 与 IaC 不同

GitOps 关注“Git 中期望状态怎样持续落到运行环境”；IaC 关注“基础设施怎样由代码声明和创建”。二者配合而非互斥。

一个典型仓库结构可以是：

```text
agent-platform-gitops/
├── terraform/
├── helm/
│   ├── model-serving/
│   ├── llm-gateway/
│   └── observability/
├── kustomize/
│   ├── overlays/dev/
│   ├── overlays/staging/
│   └── overlays/prod/
└── argocd/apps/
```

同一发布 tag 应成为跨层版本锚点，使模型 URI、网关策略、节点池与观测配置能在事故时回到同一时点。

---

## 46.2 Terraform、Helm、Kustomize 与 ArgoCD 各管一层

**声明式工具越多，越要明确责任边界；否则“全部代码化”会变成另一种配置混乱。**

*表46-1：Part VIII 的 IaC/GitOps 工具分工。来源：本书整理。*

| 工具 | 主要职责 | 典型对象 |
|---|---|---|
| Terraform | 云资源生命周期 | VPC、GPU 节点池、OSS、IAM |
| Helm | Kubernetes 应用打包 | KServe、LiteLLM、Runtime |
| Kustomize | 环境差异 | dev/staging/prod patch |
| ArgoCD | Git → Cluster reconcile | Application、Sync、Drift |

![图46-2：Terraform 管云，Helm 管应用，ArgoCD 管 Git 到集群的 reconcile](../../images/part8/ch/ch46-02.png)

*图46-2：Terraform 管云，Helm 管应用，ArgoCD 管 Git 到集群的 reconcile。来源：本书自绘。Alt text：三层分工，Terraform 管云基础设施资源、Helm Chart 管 Kubernetes 应用配置、ArgoCD 持续比对 Git 与集群实际状态并自动修正，三者协作覆盖从云到应用的全部声明式交付。*

不建议用 Terraform 硬写所有 Deployment，也不建议用 Helm 负责创建 VPC。判断标准应是管理对象和状态语义，而不是团队更熟悉哪个工具。

### 自底向上的交付顺序

*表46-2：平台各层与交付方式。来源：本书整理。*

| 层级 | 对象 | 工具 | 上游依赖 |
|---|---|---|---|
| L0 | VPC、子网、安全组 | Terraform | 无 |
| L1 | GPU 节点池 | Terraform | L0 |
| L2 | 模型桶、PVC、IAM | Terraform | L0 |
| L3 | KServe 模型服务 | Helm | L1/L2 |
| L4 | LLM 网关 | Helm | L3 |
| L5 | Agent Runtime/DataAgent | Helm/Kustomize | L4 |
| L6 | OTel/Langfuse/告警 | Helm | 全链路 |

上层依赖下层的资源名、服务名和 Secret。第44章的 InferenceService 没 Ready 时，第45章网关不应提前切到该 backend；可以用 ArgoCD sync wave、PreSync/health check 等机制表达顺序。

### Terraform 输出要进入上层配置，而不是靠复制粘贴

节点池名称、模型桶、IAM Role、网络信息应通过稳定输出或参数注入到 Helm values。否则同一个概念会在 HCL、YAML 和 Wiki 中各维护一份，最终漂移。

```hcl
resource "cloud_kubernetes_node_pool" "gpu_inference" {
  name          = "gpu-inference"
  min_size      = 4
  max_size      = 20
  instance_type = "gpu.a100.80g.8xlarge"

  labels = {
    nodepool = "gpu-inference"
    workload = "online-infer"
  }

  taint {
    key    = "workload"
    value  = "online-infer"
    effect = "NoSchedule"
  }
}
```

Terraform state 必须使用远程 backend 与锁，生产禁止本地随意 `apply`。多人同时改 state，比单次 YAML 错误更难恢复。

---

## 46.3 环境与 Promotion：dev 可以快，prod 必须可证明

三个环境的差异不应只体现在副本数。GPU 型号、模型权重、外部 API、配额和同步策略都需要显式表达。

*表46-3：dev、staging、prod 的典型差异。来源：本书整理。*

| 维度 | dev | staging | prod |
|---|---|---|---|
| GPU | 可共享/低规格 | 尽量同生产规格 | 生产节点池 |
| 权重 | 可用小模型快速开发 | 关键发布使用同生产权重 | 不可变生产权重 |
| 副本 | 1 | 1–2 | 按 SLO 配置 |
| 外部模型 | 宽松 | 有限额 | 按租户合规策略 |
| Sync | 自动 | 自动 + 集成门禁 | 人工批准/分批 Sync |

![图46-3：生产 Promotion 必须有人工门禁，不能依赖与 dev 相同的自动 sync](../../images/part8/ch/ch46-03.png)

*图46-3：生产 Promotion 必须有人工门禁，不能依赖与 dev 相同的自动 sync。来源：本书自绘。Alt text：dev 和 staging 可自动同步，但 prod 入口处标有人工审批门禁，箭头表示只有通过审批才能触发生产 sync，体现生产与低环境差异化的发布节奏。*

### Staging 的任务是验证生产路径，不只是验证功能

如果 prod 要发布 32B 权重，而 staging 只用 7B 模型做通用 ping，冷启动、显存、readiness 和长上下文问题仍会第一次发生在生产。Staging 可以少副本，但关键 Revision 应尽量使用同权重、同 Runtime、同探针和同服务名。

### Promotion 要晋升一组关联状态

Agent 平台一次发布经常同时涉及：

- 模型权重 URI；
- KServe Canary；
- LLM 网关 backend/tenant policy；
- GPU 节点池容量；
- Eval 证据；
- Trace/告警字段。

只晋升镜像 tag 而遗漏网关或模型 values，会造成“每个组件各自正确，组合以后错误”。**Promotion 的对象应是平台行为所依赖的一组版本，而不是一个容器镜像。**

生产 Application 应指向固定 tag，而不是 floating `main`：

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: llm-gateway-prod
spec:
  source:
    repoURL: https://git.example.com/agent-platform-gitops.git
    targetRevision: prod-v1.2.0
    path: helm/llm-gateway
  destination:
    namespace: llm-gateway
  syncPolicy:
    automated: null
```

prod 使用 Manual Sync 并不意味着所有动作都靠人完成，而是把“是否进入生产”的决定保留为显式门禁。

### 密钥绝不进入 Git

LiteLLM master key、供应商 API Key、模型桶凭证等应通过 Vault/KMS + External Secrets 注入：

```text
Git: secretRef -> vault/path/openai-key
Vault/KMS: 真正密钥
K8s: 运行时 Secret
```

对于 finance 等禁止云端的租户，可以在 Vault 路径层就不提供云端密钥，再叠加第45章模型白名单，形成双层约束。

---

## 46.4 CI 与发布证据：不仅检查 YAML 能不能解析

一条完整交付链路至少应留下四类证据：

1. Terraform plan：云资源会怎样变化；
2. Helm/Kustomize render：K8s 对象最终长什么样；
3. ArgoCD diff/Sync：哪个 revision 何时进入哪个环境；
4. Staging/Prod smoke：关键业务链路是否成立。

```bash
terraform plan -out=tfplan
helm template llm-gateway ./helm/llm-gateway -f values-prod.yaml \
  | kubectl apply --dry-run=client -f -
argocd app diff llm-gateway-prod
```

**配置语法正确，不等于配置语义正确。** CI 还应检查：

- 网关 backend 是否能在模型服务目录找到；
- `model_name` 是否与 InferenceService 名一致；
- finance 是否出现了云端 backend；
- GPU 节点池标签是否和模型 affinity 一致；
- fallback 是否成环；
- model URI 是否是不可变版本；
- 评测证据是否存在。

### Staging Smoke 要覆盖关键治理路径

不能只 `ping` 默认模型。至少应验证：

- 通用对话 backend；
- NL2SQL 代码模型；
- finance 请求云端 → 被拒绝；
- backend 故障 → fallback/异步按规则工作；
- Trace、tenant、成本字段不断链；
- 回滚到上一 tag 能恢复。

一次模型发布 PR 的说明最好直接列出：权重 URI、评测链接、Canary 计划、网关影响、GPU 容量、回滚 tag 和发布窗口。PR 本身就是发布证据的一部分。

### 三联审计

*表46-4：GitOps 变更的三个主要审计来源。来源：本书整理。*

| 系统 | 关键字段 | 回答的问题 |
|---|---|---|
| Git PR | author、paths、tag、approval | 谁改了什么 |
| ArgoCD | revision、initiator、diff、sync time | 何时进入集群 |
| Terraform | workspace、run_id、resource diff | 云资源怎样变化 |

这些记录应继续和第38章运行 Trace 关联。事故发生时，团队可以从异常 `run_id` 找到命中的模型/网关策略，再追到对应 Git revision，而不是在聊天群里问“那天谁改过配置”。

---

## 46.5 漂移、紧急变更与回滚

GitOps 不意味着生产环境永远禁止应急操作。严重事故中，SRE 可能需要临时扩大副本、摘除 backend 或调整配额。关键是**应急动作不能成为新的永久事实源**。

一个合格 break-glass 过程至少要有：

```text
incident_id
operator
resource/path
before/after
reason
expiry_time
follow-up PR
rollback / retain decision
```

没有 incident ID 的 OutOfSync 应视为违规漂移；有 incident ID 但超过时限未回写 Git，同样应升级处理。

### prod 是否自动 self-heal

开发环境可以积极自愈；生产环境要更谨慎。事故处理中，控制器如果立即覆盖合法热修，反而会影响恢复。生产可以先告警和冻结，确认变更背景后再 reconcile。**漂移必须被发现，但是否立刻覆盖，需要按风险和资源类型决定。**

*表46-5：高频 GitOps/IaC 故障。来源：本书整理。*

| 故障 | 典型原因 | 恢复 |
|---|---|---|
| ArgoCD OutOfSync | 手工 `kubectl edit` | 补 PR 或显式回滚 |
| Terraform state 冲突 | 无远程锁、多人 apply | Remote state + lock |
| Helm 资源争用 | 多 Chart 管同一资源 | 单 owner + 依赖锁 |
| Git revert 后仍不可用 | 旧制品/Secret 已不可访问 | 固定制品保留窗口 |
| prod 自动同步误上线 | 复制 dev 策略 | 固定 tag + Manual Sync |

**`git revert` 只恢复声明，不保证业务状态能回滚。** 模型权重、索引、数据库 schema、边缘制品和 Secret 都可能已经变化。每类资源都要说明回滚是否真正可逆。

回滚演练应确认：旧镜像可拉取、旧权重存在、旧 Helm values 仍兼容集群、网关策略能识别当前 tenant、Terraform state 没有不可逆变更。

---

## 46.6 边缘推理：同一治理模型，另一种同步方式

门店、工厂、物流手持设备的网络、算力和隐私条件与中心云不同，但它们不应该成为人工维护的“模型孤岛”。**边缘是 GitOps 的特殊 overlay，不是 GitOps 的例外。**

*表46-6：三类边缘场景。来源：本书整理。*

| 场景 | 约束 | 模型形态 | 更新方式 |
|---|---|---|---|
| 门店导购 | 弱网、离线可用 | llama.cpp 3B–7B 量化 | 夜间 OTA |
| 工厂质检 | 内网、低延迟 | ONNX/视觉小模型 | 工单/维护窗口 |
| 物流手持 | 移动网络 | MLC 小模型 | 分区域 CDN/OTA |

![图46-4：边缘节点是 GitOps 的特殊 overlay，不是脱离治理的孤岛](../../images/part8/ch/ch46-04.png)

*图46-4：边缘节点是 GitOps 的特殊 overlay，不是脱离治理的孤岛。来源：本书自绘。Alt text：云端 Git 仓库通过 overlay 覆盖边缘节点的特殊配置（低端模型、离线缓存），边缘节点仍在 GitOps 同步框架内而非手工维护的孤岛。*

### 边缘与中心的职责分工

简单、稳定、低风险任务在边缘完成；复杂推理、跨域数据和高风险任务回中心网关。

| 请求 | 边缘 | 回中心条件 |
|---|---|---|
| FAQ、基础库存/政策 | 小模型 | 低置信度/复杂问法 |
| 工厂视觉初判 | ONNX/VLM 小模型 | 边界样本、需大模型复核 |
| 运单基础查询 | 移动端模型/规则 | 理赔、多轮复杂任务 |
| 企业 DataAgent NL2SQL | 不建议边缘 | 始终走中心网关 |

边缘回传应携带 `edge_site_id`、`edge_model_version` 和 manifest tag，中心才能判断一次用户投诉来自哪个边缘版本。

### OTA 必须支持原子切换

弱网下最危险的不是“下载失败”，而是**半下载文件被当作有效模型加载**。一个安全 OTA 流程是：

```text
下载到 .staging
  ↓
校验 sha256 / size / manifest
  ↓
运行最小 smoke
  ↓
atomic rename / 切 active symlink
  ↓
保留 previous version
```

中心 inventory 需要持续知道每个节点的当前版本、最后同步时间和失败原因。发布完成不等于所有边缘节点已经升级；边缘分布式环境天然需要接受版本窗口，但必须知道窗口在哪里。

---

## 46.7 生产治理：变更窗口、安全审计与业务可读摘要

GitOps 成熟度最终体现在生产变更是否可审阅、可解释、可恢复，而不在仓库里有多少 YAML。

### 变更窗口

模型大版本、网关策略、GPU 节点池和边缘制品不应在大促、月末关账、监管报送等关键窗口随意发布。高风险变更要提前说明：影响租户、流量、成本、回滚路径和观察 owner。

### 配置安全审计

声明式配置本身就是安全边界。CI/Policy 应检查：

- Secret 泄漏；
- 过宽 IAM；
- 公网 LoadBalancer；
- 不受控 egress；
- finance 云端模型路径；
- 审计关闭；
- 高风险应用绕过网关；
- 边缘制品来源与校验。

Git 中只保存 Secret 引用，不保存明文，是底线而不是最佳实践。

### 业务可读变更摘要

业务 owner 不需要理解每行 YAML，但需要知道：

```text
变更了什么能力
影响哪些租户/任务
成本或容量怎样变化
是否改变模型/路由/权限
观察哪些指标
如何回滚
谁负责确认
```

一个 `canaryTrafficPercent: 5 -> 20` 是技术字段，但其业务含义是“更多真实请求开始命中新模型”。一个 `tenant_quota` 变化，是资源承诺变化。把这些 diff 转成业务语言，能显著提升跨团队审批质量。

### 定期复盘的重点

平台不需要给每个小改动写长报告，但应定期检查：

- 哪些组件最常出现 OutOfSync；
- 哪些临时变更长期未收束；
- 哪些网关策略频繁热修；
- 哪些 GPU 节点池经常临时扩容；
- 哪些边缘节点长期落后版本；
- 哪些回滚路径从未演练。

**GitOps 的最终验收标准是：任意生产行为变化，都能找到对应声明、审批、Sync、运行证据和恢复路径。**

## 本章小结

GitOps 与 IaC 把 Agent 平台从“谁会操作机器”转向“谁能通过受控声明改变期望状态”。Terraform 管云资源，Helm 管 Kubernetes 应用，Kustomize 管环境差异，ArgoCD 负责持续 reconcile；它们各司其职。dev/staging/prod 的 Promotion 要显式管理模型权重、网关策略、GPU 容量和评测证据，生产应追固定 tag 并保留人工门禁。OutOfSync 是漂移信号，应急修改可以存在，但必须有 incident、到期时间和回写 PR。回滚需要验证旧制品和依赖真正可用，不能把 `git revert` 当作完整恢复。边缘推理沿用同一声明式治理模型，只把同步方式改成 OTA，并通过 checksum、原子切换和 inventory 管理弱网与版本碎片化。GitOps 的价值最终不在自动化部署速度，而在让平台状态可复现、变更可审计、故障可回退。

## 参考文献

HashiCorp. (n.d.). [Terraform documentation](https://developer.hashicorp.com/terraform/docs).

Helm. (n.d.). [Documentation](https://helm.sh/docs/).

Argo CD. (n.d.). [Documentation](https://argo-cd.readthedocs.io/).

ONNX Runtime. (n.d.). [Documentation](https://onnxruntime.ai/docs/).
