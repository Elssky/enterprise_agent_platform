# 第43章 GPU 调度与 Kubernetes

---

促销高峰前，客服 Agent 的在线推理 Pod 开始排队等待 GPU。监控显示集群平均利用率并不高：部分卡被批处理长期占用，部分卡因为节点标签、模型副本或拓扑约束无法被在线推理使用。业务看到的是首 token 变慢，平台看到的却是“还有余量”。

**GPU 调度的目标不是把平均利用率做高，而是把稀缺算力变成可承诺的资源池：哪类任务、以什么优先级和配额、在多长时间内能够拿到哪类 GPU。** 在线推理、微调、离线批处理和评测批跑，对延迟、运行时长、抢占和隔离的要求完全不同。把它们放进同一个默认节点池，短期省事，长期会把 SLO、成本和事故责任混在一起。

Kubernetes 提供容器与资源调度基础，但企业级 GPU 平台还需要节点池、Taint/Affinity、Gang Scheduling、队列、配额、共享策略和弹性容量。第44章的模型服务依赖本章提供可预测算力；第45章的网关也需要知道底层 backend 是否还有容量。

---

## 43.1 先按负载划分算力承诺

GPU 资源规划的第一步不是问“需要多少张卡”，而是判断负载属于哪一类。

*表43-1：四类 GPU 负载的延迟、抢占与节点池建议。来源：本书整理。*

| 负载类型 | 典型场景 | 延迟要求 | 可抢占性 | 推荐节点池 |
|---|---|---|---|---|
| 在线推理 | 客服 Agent、DataAgent 对话 | 毫秒—秒级 | 低 | `gpu-inference` |
| 微调训练 | LoRA、领域适配 | 小时—天级 | 中 | `gpu-train` |
| 离线批处理 | Embedding 重建、评测批跑 | 分钟—小时级 | 高 | `gpu-batch` |
| 弹性尖峰 | 促销、月末分析 | 突发 | 缓冲容量 | `gpu-burst` |

在线推理最关注尾延迟，通常需要独占整卡并保留余量；训练更关注多卡同时到位；批任务允许排队和断点续跑；尖峰任务则要求提前预热而不是完全依赖冷启动扩容。

![图43-1：GPU 调度层位于 Agent 平台算力底座，向上支撑模型服务与业务 Agent](../../images/part8/ch/ch43-01.png)

*图43-1：GPU 调度层位于 Agent 平台算力底座，向上支撑模型服务与业务 Agent。来源：本书自绘。Alt text：分层图最下层是 GPU 资源池与调度器，中层是模型服务，上层是业务 Agent，箭头自下而上表示算力逐层支撑应用。*

![图43-2：四类 GPU 负载的延迟、时长与优先级差异决定节点池划分](../../images/part8/ch/ch43-02.png)

*图43-2：四类 GPU 负载的延迟、时长与优先级差异决定节点池划分。来源：本书自绘。Alt text：在线推理、批量推理、训练、实验四类负载按延迟要求和运行时长落在坐标系不同区域，各自映射到独立节点池，体现按负载特征隔离资源。*

**在线推理与批处理是否分池，是 GPU 平台从试点走向生产的第一道分水岭。** 平均利用率可以解释采购效率，却不能单独证明用户体验稳定。延迟敏感负载为了 P99 预留 20% 甚至更多显存和算力，并不等于资源浪费。

接入一个新模型服务时，业务团队至少要声明：负载类型、预期并发、上下文长度、运行窗口、GPU 型号、是否要求 NVLink、是否可抢占、冷启动时间和业务优先级。平台才能据此决定节点池、队列和配额。

### 三个常见误判

第一，把 Kubernetes 等同于完整 GPU 调度能力。Device Plugin 能让调度器看到 `nvidia.com/gpu`，但默认 scheduler 并不理解多卡任务必须同时启动，也不理解事业部预算和 AI 队列语义。

第二，把 GPU 共享当作“免费翻倍”。Time-Slicing 可以提高平均利用率，却可能显著恶化在线推理尾延迟。MIG 更适合同规格、同 SLA 的共享推理；生产在线服务仍应默认独占整卡，除非压测证明共享不会破坏 SLO。

第三，把 Slurm 与 Kubernetes 设成二选一。科学计算、长时训练可以继续留在 Slurm；推理、Agent Runtime、GitOps 生命周期内的模型服务更适合 Kubernetes。关键是统一 GPU 台账和预算，而不是强行统一调度器。

---

## 43.2 Kubernetes GPU 调度：从“看见卡”到“放对位置”

Kubernetes 调度 GPU 可以拆成三步：**让调度器看见 GPU、让规则表达业务边界、让 Pod 落到正确拓扑。**

### Device Plugin：让 K8s 看见 GPU

NVIDIA Device Plugin 或云厂商等价组件以 DaemonSet 运行在 GPU 节点上，向 kubelet 注册 `nvidia.com/gpu`。

```yaml
resources:
  requests:
    nvidia.com/gpu: "1"
  limits:
    nvidia.com/gpu: "1"
```

GPU 独占场景下，`requests` 与 `limits` 通常保持一致。节点 Ready 不等于 GPU 可调度；驱动升级后 Device Plugin 失联，是典型“节点正常、GPU 容量归零”故障。

### Taint、Toleration 与 Affinity：把业务约束写进调度规则

仅声明 GPU 数量，批任务仍可能落到在线池。生产集群应同时使用：

- Taint/Toleration：控制哪些工作负载能进入节点池；
- nodeAffinity：约束 `nodepool`、GPU 型号与拓扑；
- podAntiAffinity：避免同一服务副本集中在单节点；
- topologySpreadConstraints：跨可用区或故障域分散。

*表43-2：常用 GPU 节点标签。来源：本书整理。*

| 标签键 | 示例值 | 含义 |
|---|---|---|
| `nodepool` | `gpu-inference` | 节点池归属 |
| `gpu.model` | `a100-80g` | GPU 型号 |
| `gpu.topology` | `nvlink-2` | 多卡拓扑 |
| `workload` | `online-infer` | 允许的负载类型 |

![图43-3：Pod 从资源声明到物理 GPU 绑定的五步调度链路](../../images/part8/ch/ch43-03.png)

*图43-3：Pod 从资源声明到物理 GPU 绑定的五步调度链路。来源：本书自绘。Alt text：横向五步。资源请求、调度器筛选、节点打分、绑定、设备插件分配 GPU，箭头展示一个 Pod 从声明算力到拿到物理卡的完整过程。*

生产推理池可以这样表达：

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: nodepool
              operator: In
              values: ["gpu-inference"]
tolerations:
  - key: workload
    operator: Equal
    value: online-infer
    effect: NoSchedule
resources:
  limits:
    nvidia.com/gpu: "1"
```

**节点池标签和污点是集群纪律，不是部署模板里的装饰字段。** 如果去掉 Affinity 以后批任务能够进入推理池，说明资源边界还没有真正建立。

---

## 43.3 队列、Gang Scheduling 与多租户配额

默认 kube-scheduler 擅长单 Pod 即时绑定，但 AI 作业经常需要一组 Pod 同时获得资源。70B 模型 TP=4，如果只启动 3 个 worker，第 4 个长期 Pending，前三张卡会被白白占住。

### Volcano：解决多卡任务“要么一起启动，要么一起等待”

```yaml
apiVersion: scheduling.volcano.sh/v1beta1
kind: PodGroup
metadata:
  name: llm-70b-tp4
spec:
  minMember: 4
  queue: gpu-inference
  priorityClassName: online-infer-high
```

Volcano 的核心价值是 Gang Scheduling 与批队列。它适合多卡训练、批推理和需要同时满足多 Pod 的服务。

### Kueue：把事业部 GPU 预算写成准入规则

Kueue 更适合表达跨租户配额：某事业部最多同时使用多少 GPU、哪些 Job 在额度耗尽时进入队列、临时提额何时失效。

```yaml
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: finance-gpu
spec:
  resourceGroups:
    - coveredResources: ["nvidia.com/gpu"]
      flavors:
        - name: default
          resources:
            - name: "nvidia.com/gpu"
              nominalQuota: 12
```

*表43-3：默认 Scheduler、Volcano 与 Kueue 的责任边界。来源：本书整理。*

| 组件 | 主要职责 | 适合场景 |
|---|---|---|
| kube-scheduler | 单 Pod 绑定 | 在线单卡推理 |
| Volcano | Gang + 批队列 | 多卡训练、批推理 |
| Kueue | 租户/团队准入与配额 | 跨事业部 GPU 预算 |

![图43-4：三类调度器按工作负载特征分工，而非互相替代](../../images/part8/ch/ch43-04.png)

*图43-4：三类调度器按工作负载特征分工，而非互相替代。来源：本书自绘。Alt text：默认调度器、批调度器（如 Volcano）、框架调度器（如 Ray）三者并列，各标注擅长的负载类型，箭头表示它们分管不同负载而非竞争同一职责。*

Volcano 与 Kueue 并不互斥：前者决定一组 Pod 怎样启动，后者决定某个租户是否还有额度。规模化平台可以同时使用两者，但必须为队列、配额和 PriorityClass 建立统一 owner。

### Ray 与 Kubernetes 是两层调度

Ray 解决 Pod 起来以后内部 Task/Actor 怎样调度；Kubernetes/Volcano 解决 Pod 能否拿到节点和 GPU。

![图43-5：K8s 供给节点与 Pod 边界，Ray 在集群内调度 Task](../../images/part8/ch/ch43-05.png)

*图43-5：K8s 供给节点与 Pod 边界，Ray 在集群内调度 Task。来源：本书自绘。Alt text：外层 Kubernetes 负责节点和 Pod 的生命周期，内层 Ray 在 Pod 构成的集群里调度细粒度 Task，箭头表示两层调度各管一层、嵌套协作。*

Pending 查 Kubernetes/Volcano，Task 慢查 Ray Dashboard。把两层混在一起排障，会显著增加定位时间。

---

## 43.4 GPU 共享、弹性扩缩与容量规划

GPU 平均利用率低并不自动等于资源浪费。在线推理的长上下文和 KV Cache 对显存余量要求很高，而批处理更适合把卡持续吃满。

*表43-4：GPU 共享方案的隔离与风险。来源：本书整理。*

| 方案 | 隔离强度 | 适合场景 | 主要风险 |
|---|---|---|---|
| MIG | 高 | 同 SLA 多推理服务 | 规格固定、切分不灵活 |
| Time-Slicing | 低 | dev/test、低优先级批任务 | 尾延迟抖动 |
| vGPU | 中 | 虚拟化多租户 | 许可与厂商绑定 |
| 独占整卡 | 最高 | 延迟敏感在线推理 | 利用率看起来偏低 |

**共享策略首先受 SLO 约束，其次才受利用率约束。** 线上对话与批任务混 Time-Slicing，可能让 GPU 利用率变漂亮，却把 TTFT P99 从几百毫秒推到秒级。

### HPA 扩 Pod 不等于有 GPU 可用

HPA 把副本从 4 扩到 8，如果集群只剩两张空闲 GPU，多出的 Pod 只会进入 Pending。GPU 节点的 Cluster Autoscaler 又往往需要数分钟到十几分钟完成节点创建、驱动初始化、镜像和模型加载。

可预测高峰应提前预热 `gpu-burst`，而不是把所有希望寄托在实时扩容上。第44章的 `minReplicas`、本章节点池的 `min/max_size` 和第45章的租户限流必须联合规划。

容量规划还应看：

- 模型权重与量化格式；
- 上下文长度与 KV Cache；
- 请求输入/输出 token 分布；
- tokenizer CPU；
- 模型冷启动和权重拉取；
- 流式连接时长；
- 可接受排队时间。

**GPU 张数只是容量的一维，真正能承诺多少请求取决于请求画像。**

---

## 43.5 调度故障：从 Pending、OOM 到误抢占

GPU 调度故障要先判断责任域，再决定是修节点、改队列、调配额还是调整模型资源画像。

*表43-5：调度组件的职责与典型失败。来源：本书整理。*

| 组件 | 职责 | 典型失败 |
|---|---|---|
| Device Plugin | 注册 GPU | 驱动升级后容量归零 |
| kube-scheduler | 单 Pod 调度 | GPU 碎片化、Affinity 无解 |
| Volcano | Gang + 队列 | `minMember` 永久等待 |
| Kueue | 配额准入 | 租户配额耗尽 |
| Cluster Autoscaler | 节点扩缩 | GPU 节点冷启动过慢 |

*表43-6：高频调度故障及恢复方向。来源：本书整理。*

| 失败模式 | 典型信号 | 恢复策略 |
|---|---|---|
| GPU OOM | `OOMKilled`、显存耗尽 | 降 batch、限 context、量化或拆服务 |
| Gang 永久 Pending | PodGroup Unschedulable | 扩容、调 TP/minMember |
| 抢占误伤 | 在线会话中断 | 提升 PriorityClass，禁止批任务抢占在线池 |
| 配额耗尽 | Workload 长期 Pending | 提配额或清理僵尸 Job |
| 节点漂移 | 同池 CUDA/驱动不一致 | 标准化节点池并滚动升级 |

![图43-6：五类调度失败的可检测信号与恢复动作应写入 Runbook](../../images/part8/ch/ch43-06.png)

*图43-6：五类调度失败的可检测信号与恢复动作应写入 Runbook。来源：本书自绘。Alt text：OOM、抢占、Gang 调度失败、配额耗尽、节点故障五类失败各自连到检测信号与恢复动作，汇入一份 Runbook，体现失败处理可预案化。*

典型排障顺序：

1. 节点是否 Ready，`nvidia.com/gpu` 容量是否正常；
2. Pod 的 Taint/Toleration、Affinity 是否可满足；
3. Volcano PodGroup 是否满足 `minMember`；
4. Kueue 是否因配额阻塞；
5. 节点池是否在扩容，扩容预计多久；
6. 模型自身显存画像是否超预算。

Runbook 还应写清楚资源不足时“先停谁”：默认保护在线用户流量，释放未满足 Gang 的半启动任务，拒绝或排队低优先级批任务，而不是让所有租户一起变慢。

---

## 43.6 生产治理：配额复审、网关联动与算力账本

GPU 调度上线后，资源池会逐渐积累低使用率模型、长期 Pending 的评测任务、过期临时扩容和无人认领的实验队列。平台至少应按月复审：模型副本、Kueue 配额、Volcano 队列、节点标签、临时节点池和成本归属。

复审不能只看利用率。每份长期 GPU 占用都应能映射到：

- `owner` 与成本中心；
- 模型/任务类型；
- SLO 与业务优先级；
- 当前副本/配额；
- 到期时间；
- 是否存在可替代模型或异步路径。

没有 owner 的资源不应继续扩容；临时提额必须有到期时间；长期低利用率服务可以改为弹性副本或预热池；高利用率如果来自错误重试，应先修逻辑而不是先买卡。

### 与第45章网关联动

网关应读取模型 backend 的副本数、排队长度和健康状态，再结合租户预算、任务风险和请求上下文长度决定等待、降级、拒绝或切换模型。反过来，调度层也需要网关提供真实请求画像，才能判断是扩节点、迁批任务还是限制超长 context。

监控应至少覆盖：

| 指标 | 作用 |
|---|---|
| GPU 利用率与显存 | 资源画像 |
| Pod Pending 时长 | 调度压力 |
| PodGroup/Kueue 队列 | Gang 与配额阻塞 |
| 节点 Ready/Device Plugin | 基础设施健康 |
| TTFT/P99 与请求排队 | 用户体验 |
| GPU 小时/租户/模型 | FinOps 归因 |

**GPU 调度最终交付的不是一组 Kubernetes YAML，而是一份可执行的算力契约。** 它告诉业务什么任务被优先保护，告诉 SRE 哪些节点池可以调整，告诉 FinOps 成本归到哪里，也告诉网关资源不足时该怎样降级。

## 本章小结

GPU 调度是模型服务的算力底座。Device Plugin 只负责让 Kubernetes 看见 GPU；Taint、Affinity、队列、Gang Scheduling 和配额才把业务优先级写进资源分配。在线推理、训练、批处理与尖峰流量应按 SLA 分池；Volcano 解决多 Pod 同时启动，Kueue 解决跨租户配额，Ray 则在 Pod 内继续调度 Task。MIG 与 Time-Slicing 能提升共享率，但不能以尾延迟为代价。HPA、Cluster Autoscaler、模型 `minReplicas` 和网关限流必须联合规划。生产治理的重点不是“集群还有几张卡”，而是高价值任务能否按承诺得到资源、资源不足时平台能否做出一致且可解释的取舍。

## 参考文献

Kubernetes. (n.d.). [Device Plugins documentation](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/).

NVIDIA. (n.d.). [GPU Operator documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/).

Kubernetes. (n.d.). [Kueue documentation](https://kueue.sigs.k8s.io/docs/).

Volcano. (n.d.). [Documentation](https://volcano.sh/en/docs/).
