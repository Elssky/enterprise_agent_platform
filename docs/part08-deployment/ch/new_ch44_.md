# 第44章 模型部署

---

某次 NL2SQL 批量任务突然失败。排查后发现模型能力没有退化，GPU 也没有故障，而是 Agent Runtime 直接连接了 vLLM Pod 的内网 IP；HPA 缩容后 Pod 重建，地址变化，Runtime 配置却仍指向旧地址。

**模型服务层的价值，是把权重、Runtime、GPU 节点、探针、版本和发布策略收敛成稳定 API。上层 Agent 只知道服务名和契约，不应知道 Pod IP、节点位置或权重目录。**

第6章解决单机推理引擎，第43章解决算力供给，本章解决模型怎样成为可发布、可扩缩、可灰度、可回滚的生产服务；第45章再在服务之上统一做路由、租户和配额。

---

## 44.1 模型服务层：算力之上的第一个稳定 API

企业平台通常同时运行多类模型：通用 LLM、代码模型、Embedding、Rerank、视觉模型。它们的资源画像、发布频率和风险并不一样，因此不应被塞进同一个推理进程或同一套发布周期。

*表44-1：典型模型服务目录。来源：本书整理。*

| 服务名 | 引擎 | 用途 | 默认副本 |
|---|---|---|---|
| `llm-general-32b` | vLLM | 通用对话、Planner | 4 |
| `llm-code-7b` | SGLang | SQL/Python 生成 | 2 |
| `embed-bge-m3` | Triton | Embedding | 2 |
| `rerank-bge-v2` | Triton | Rerank | 1 |

这里的服务名是**发布单元和稳定契约**。每个服务拥有自己的 Runtime、权重版本、资源画像、SLO、灰度策略和回滚窗口。第45章网关只映射这些稳定服务名，不能把底层 vLLM/SGLang 进程地址暴露给 Agent。

![图44-1：模型服务层是 GPU 算力与 Agent 调用之间的稳定 API 边界](../../images/part8/ch/ch44-01.png)

*图44-1：模型服务层是 GPU 算力与 Agent 调用之间的稳定 API 边界。来源：本书自绘。Alt text：中间模型服务层向下对接 GPU 资源、向上为 Agent 提供稳定 API，箭头表示底层算力或模型变化被服务层屏蔽、不影响上层调用。*

### 在线、批、Embedding 为什么要拆服务

*表44-2：不同服务形态的负载与发布策略。来源：本书整理。*

| 服务形态 | 资源特征 | 典型场景 | 发布策略 |
|---|---|---|---|
| 在线 LLM | 长连接、KV Cache、尾延迟敏感 | 对话、DataAgent | 金丝雀 + 快速回滚 |
| 批推理 | 高吞吐、可排队 | Eval、离线报告 | 滚动或蓝绿 |
| Embedding | 高 QPS、固定输出维度 | RAG 索引 | 双版本并行后切流 |
| Rerank | 小模型、高频 | 检索排序 | 滚动发布 |

Embedding 和生成式 LLM 混在一张卡上，表面上能提高平均利用率，却容易让小 batch 的高 QPS 与长上下文生成争抢显存和 CUDA 执行资源。**服务拆分首先是资源隔离和故障隔离，其次才是组织结构。**

### 四个容易混淆的对象

- **Serving Runtime**：模型怎么运行，例如 vLLM/SGLang 镜像和启动参数；
- **Predictor**：怎样接收请求并把流量交给 Runtime；
- **模型版本**：权重 digest + Runtime 镜像 + 关键启动参数；
- **Revision**：一次可发布、可回滚的服务版本实例。

Git 里改一行 YAML 不自动等于新模型版本；只有权重、镜像与关键参数形成不可变组合，并产生新 Revision，才真正改变生产模型服务。

---

## 44.2 部署框架：按负载选，不追求一套框架包打天下

*表44-3：主流模型 Serving 框架的定位。来源：本书整理。*

| 方案 | 强项 | 适合 | 主要代价 |
|---|---|---|---|
| KServe | Kubernetes 原生、Revision、流量分割、扩缩 | 主 LLM 在线服务 | 依赖 K8s 能力 |
| BentoML | 模型打包与开发体验 | 实验到服务化 | 企业流量治理仍需补齐 |
| Triton | 动态 batching、多模型、高性能 | Embedding/Rerank | 原型迭代不如 Python 框架轻 |
| Ray Serve | Python 原生分布式编排 | 复杂分析、Ray 生态 | 运维体系更重 |

![图44-2：部署框架按负载类型选型，而非单一框架包打天下](../../images/part8/ch/ch44-02.png)

*图44-2：部署框架按负载类型选型，而非单一框架包打天下。来源：本书自绘。Alt text：在线推理、批推理、多模型并存等负载分别连向更合适的框架（KServe、BentoML、Triton），体现按负载选型而非一刀切。*

本书主路径是：LLM 在线服务使用 **KServe + vLLM/SGLang**，Embedding/Rerank 使用 Triton，重批分析按需使用 Ray Serve。选择依据不是框架热度，而是是否和第43章 GPU 调度、第45章网关、第46章 GitOps 形成统一运行边界。

### KServe 启动链路

一次模型 Pod 启动至少经历：

1. 获取不可变模型 URI；
2. 拉取权重；
3. 初始化 Runtime/CUDA/KV Cache；
4. readiness 通过；
5. Service/Revision 才开始接流量。

*表44-4：Serving 组件与典型失败。来源：本书整理。*

| 组件 | 职责 | 典型失败 |
|---|---|---|
| Storage Init | 拉取权重 | URI 404、IAM 拒绝、网络失败 |
| Serving Runtime | 加载并推理 | CUDA 不兼容、OOM |
| Predictor | 接请求 | Runtime 未 Ready 就接流量 |
| Scaler | 扩缩副本 | 冷启动期间错误判断容量 |

![图44-3：权重加载、Runtime 就绪与流量接入是三个不同控制点](../../images/part8/ch/ch44-03.png)

*图44-3：权重加载、Runtime 就绪与流量接入是三个不同控制点。来源：本书自绘。Alt text：部署流程上标出三个独立门控。权重加载完成、Runtime 健康就绪、流量正式接入，箭头表示前一步通过才进入下一步，避免未就绪即接流量。*

**进程活着、模型加载完成、应该接真实流量，是三个不同状态。** 把 liveness `/health` 当成 readiness，是大模型上线最常见的“半启动接流量”问题之一。

---

## 44.3 资源画像与服务接口契约

大模型服务的资源画像不能只写“1 张 GPU”。权重、量化、上下文长度、KV Cache、tokenizer CPU、host memory 和 tensor parallel 都会影响是否能稳定服务。

*表44-5：典型资源画像。来源：本书整理。*

| 维度 | `llm-general-32b` 示例 | 说明 |
|---|---|---|
| GPU | 1 × A100-80G | 在线整卡 |
| CPU | request 8 / limit 12 | tokenizer 与调度线程 |
| Memory | request 32Gi / limit 48Gi | 避免 host OOM |
| 权重 | AWQ | 约 20GB+，按实际模型测算 |
| KV 余量 | 至少 20% | 长上下文与并发峰值 |
| 冷启动 | 数分钟级 | 权重下载 + CUDA 初始化 |

同样权重在 4k 和 32k context 下的容量完全不同。上线前要用真实输入/输出 token 分布压测，而不是只用短 prompt 做健康检查。

### 稳定 API 契约

上层 Runtime 和网关最好只依赖一个稳定的 OpenAI 兼容子集：

```text
GET  /v1/models
GET  /health
GET  /ready
POST /v1/chat/completions

Request:
  { model, messages, stream, max_tokens, ... }

Errors:
  { error: { code, message, type }, retryable: bool }
```

`/v1/models` 返回的模型名必须和服务目录、第45章网关路由一致。错误也要区分可重试和不可重试：队列过载、临时上游失败可以退避；上下文超限、参数非法不应反复重试。

### 优雅下线

LLM 是长连接服务。滚动发布时，如果 Pod 收到 SIGTERM 立即退出，用户会看到半截流式回答。应先停止接收新连接，等待 in-flight 请求完成，再终止进程。

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 120
  periodSeconds: 10
```

`terminationGracePeriodSeconds` 应参考真实流式请求 P99 设置，而不是沿用普通 Web 服务默认值。

---

## 44.4 版本管理：Staging、Canary、蓝绿与回滚

模型发布和普通应用发布最大的差异，是**权重、Runtime 参数和模型行为都可能改变质量与资源画像**。因此，一次模型发布应绑定：

- 权重 URI/digest；
- Runtime 镜像 digest；
- 量化方式；
- TP/PP；
- `max_model_len`；
- 资源声明；
- 评测版本；
- Revision 与流量比例。

*表44-6：常见发布策略。来源：本书整理。*

| 策略 | 优势 | 代价 | 适合 |
|---|---|---|---|
| 滚动 | 简单、省资源 | 短暂混合版本 | Embedding、低风险服务 |
| 金丝雀 | 风险可控 | 需要流量和观测 | 主 LLM |
| 蓝绿 | 回滚最快 | 双倍资源 | 大版本窗口 |
| A/B | 长期比较业务 KPI | 治理复杂 | 模型实验 |

发布状态可以统一成：

```text
Draft -> Staging -> Canary -> Expanding -> Stable -> Deprecated
                     \-> Rollback -> previous Stable
```

![图44-4：金丝雀发布把“全量切换”拆成可观测、可回滚的多个门禁](../../images/part8/ch/ch44-04.png)

*图44-4：金丝雀发布把“全量切换”拆成可观测、可回滚的多个门禁。来源：本书自绘。Alt text：流量从 1%、5%、25% 到 100% 分阶段放量，每阶段设观测与回滚门禁，箭头表示指标达标才进入下一档，异常即回滚。*

**Canary 的价值不在“先放 5%”，而在于每一档都绑定明确的质量、延迟、错误率、GPU 资源和回滚条件。** 如果 5% 流量没有覆盖长上下文、高并发和关键租户，它并不能证明全量安全。

### KServe 发布示例

```yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: llm-general-32b
  namespace: model-serving
spec:
  predictor:
    minReplicas: 2
    maxReplicas: 8
    model:
      modelFormat:
        name: vllm
      storageUri: oss://agent-platform-models/llm/qwen2.5-32b-awq/v20260301/
      resources:
        limits:
          nvidia.com/gpu: "1"
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
            - matchExpressions:
                - key: nodepool
                  operator: In
                  values: ["gpu-inference"]
  canaryTrafficPercent: 5
```

权重 URI 必须不可变，禁止使用 `latest/` 覆盖上传。上一 Stable Revision 应保留明确回滚窗口，且旧权重、旧镜像和旧 Secret 在窗口内必须仍可访问。

### 回滚不是 `git revert` 的同义词

真正的回滚要验证：

1. 旧 Revision 仍存在；
2. 旧权重可拉取；
3. 旧 Runtime 与当前节点驱动兼容；
4. 网关仍能发现旧服务；
5. 旧版本的关键评测仍有效；
6. 切流能在目标时间内完成。

季度回滚演练比事故发生时第一次点击“Rollback”可靠得多。

---

## 44.5 从本地验证到生产：三阶发布链路

Docker Compose 适合本地开发，不能直接充当生产发布系统。它可以验证模型能否启动、`served-model-name` 是否一致、OpenAI 字段是否兼容，但不覆盖 K8s readiness、GPU 节点亲和、Canary 和回滚。

### 本地 Compose

```yaml
services:
  vllm-general:
    image: vllm/vllm-openai:latest
    command: >
      --model /models/qwen2.5-32b-awq
      --served-model-name llm-general-32b
      --tensor-parallel-size 1
    ports:
      - "8000:8000"
    volumes:
      - ./models:/models:ro
```

### Staging

Staging 应尽量和生产使用相同的：

- 权重 digest；
- Runtime 参数；
- readiness；
- GPU 型号；
- 网关路径；
- 模型名。

可以缩小副本数，但不应拿 7B 权重替代 32B 来验证“大模型发布链路”，否则冷启动、显存和 KV Cache 问题仍会第一次出现在生产。

### Prod Canary

生产前至少要组合三类证据：

- 离线评测：看模型质量和关键任务；
- 压测：看 TTFT、TPOT、并发、OOM、长上下文；
- Canary：看真实租户、真实路由、真实流式连接。

**模型能启动，只证明 Runtime 可运行；模型能发布，需要证明加载、流量、质量、资源、回滚和上层契约同时成立。**

Embedding 发布还有额外约束：模型版本必须和索引版本绑定。只升级 Embedding 服务却不重建索引，会造成向量空间不一致，属于最危险的静默退化之一。

---

## 44.6 生产运行：服务目录、故障降级与退役

模型服务上线后，平台需要一份机器可读的服务目录，而不是只保存 endpoint。目录至少应包含：

- 服务名、Revision、权重 URI、镜像 digest；
- 引擎、量化、TP/PP、context length；
- 支持 tool call / JSON / streaming 等能力；
- GPU/CPU/Memory 画像；
- SLO、owner、租户；
- 当前路由与 fallback；
- 发布、回滚、退役状态；
- 调用量、GPU 小时和成本。

### 能力声明必须由评测证明

服务目录声称“支持 JSON 输出”“适合 NL2SQL”“支持 32k context”，都应关联对应的评测样本和压测结果，而不是人工填写标签。第45章网关可以据此做能力路由，Runtime 可以据此判断某类任务是否允许调用。

### 高频故障

*表44-7：模型部署高频故障。来源：本书整理。*

| 故障 | 典型信号 | 处理方向 |
|---|---|---|
| 冷启动超时 | 长时间 Ready=False | 预热、调探针、加本地缓存 |
| 权重 URI 失败 | Init/Runtime 404/403 | 固定 URI + IAM 对账 |
| CUDA/驱动不匹配 | CrashLoop | 节点池版本治理 |
| Canary 样本不足 | 低流量正常、扩量 OOM | 增强离线/压力样本 |
| 流式连接被截断 | 499/502 | 优雅下线与网关排空 |
| Embedding 版本串扰 | 检索质量突然下降 | 绑定模型和索引版本 |

模型服务故障还要给第45章网关提供可执行降级信息：当前服务是否可重试、是否存在兼容备用模型、切换后有哪些能力差异、预计多久恢复。普通摘要可以降到小模型，高风险报告可以转异步或人工复核；工具调用格式不兼容的模型不能被随意当 fallback。

### 服务退役

模型目录不能只增不减。旧模型下线前应确认：

1. 网关流量已经归零；
2. 业务 Agent 不再依赖；
3. 评测与 fallback 已迁移；
4. 回滚窗口已经结束；
5. 历史 Trace 仍能解释旧版本；
6. GPU、副本、路由、监控和 Secret 已清理。

**退役是生产承诺的结束，不是简单删除 Deployment。** 长期低使用率、无人维护且存在等价替代的模型，应进入退役候选；高价值但低频模型则可以改成预热或按需启动，而不是机械清理。

## 本章小结

模型服务层屏蔽 Pod、节点、权重和推理引擎细节，为 Agent 和 LLM 网关提供稳定服务名与契约。在线 LLM、批推理、Embedding 和 Rerank 应按资源画像与发布风险拆服务。KServe 适合承载主 LLM 的 Revision、Canary 和回滚，Triton 更适合 Embedding/Rerank。liveness、readiness 与流量接入必须分开；大模型发布要同时版本化权重、镜像和关键 Runtime 参数。生产发布依赖离线评测、容量压测和线上 Canary 三类证据，回滚必须经过真实演练。服务目录则负责把能力、资源、路由、SLO、成本和退役状态变成可治理资产。

## 参考文献

KServe. (n.d.). [Documentation](https://kserve.github.io/website/latest/).

BentoML. (n.d.). [Documentation](https://docs.bentoml.com/).

NVIDIA Triton Inference Server. (n.d.). [Documentation](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/).

Ray Serve. (n.d.). [Documentation](https://docs.ray.io/en/latest/serve/).
