# 第45章 LLM 网关与多租户

---

某次月度账单异常，平台监控显示自建推理 QPS 平稳，外部模型 API 费用却突然上升。排查发现，两个业务 Agent 为了“临时赶进度”绕过统一入口，直接使用个人保存的供应商 API Key；重试、限流、审计和成本归因都没有进入平台。

**LLM 网关必须成为模型调用的唯一治理入口。** 它不仅转发请求，还要识别租户、选择 backend、执行配额与限流、统一错误语义、传播 Trace、管理缓存和供应商差异。上层 Agent 只依赖统一模型 API，底层可以在自建模型、云端模型和备用服务之间持续调整。

第44章负责模型怎么部署、怎么灰度；本章负责“这条请求代表谁、能调用什么、该去哪个模型、能花多少、失败后怎么办”。

---

## 45.1 网关是模型调用的控制平面

没有统一网关时，每个 Agent 通常各自维护 API Key、重试逻辑、模型列表、缓存和限流。规模化后会产生四类问题：

- **安全**：个人密钥、直连外部 API、数据出域不可控；
- **成本**：Token 和 fallback 无法按租户、任务归因；
- **稳定性**：不同 Agent 重试策略互相放大；
- **审计**：无法回答某次 Run 实际命中了哪个模型和 backend。

![图45-1：网关是模型调用的唯一入口，也是治理策略的执行面](../../images/part8/ch/ch45-01.png)

*图45-1：网关是模型调用的唯一入口，也是治理策略的执行面。来源：本书自绘。Alt text：所有 Agent 调用集中经过 LLM 网关再抵达模型后端，网关上标注路由、限流、配额、审计四类治理策略，体现统一入口即统一治理。*

*表45-1：LLM 网关核心能力。来源：本书整理。*

| 能力 | 作用 |
|---|---|
| 统一 API | 屏蔽供应商和自建 backend 差异 |
| 模型路由 | 按任务、成本、延迟、合规选择模型 |
| 限流 | RPM、TPM、并发流式连接 |
| 配额 | 日/月 Token 与成本预算 |
| 缓存 | 低风险重复请求复用 |
| Trace | 传播 `trace_id`，记录 backend 与策略 |
| 成本归因 | tenant + agent + model + backend |
| 降级 | 主 backend 不可用时走预验证 fallback |

**网关统一的是调用治理，不是模型版本。** 同一个 `llm-general-32b` 的新旧 Revision 切流仍属于第44章 KServe Canary；网关保持稳定服务名，只决定调用哪个服务或备用模型。

### 多事业部示例

*表45-2：不同租户的模型与配额边界。来源：本书整理。*

| 租户 | 默认模型 | 特殊规则 |
|---|---|---|
| `retail` | `llm-general-32b` | 高峰可允许云端备用 |
| `mfg` | `llm-code-7b` / `llm-general-32b` | NL2SQL 与通用对话分路由 |
| `finance` | 本地 `llm-general-32b` | 禁止云端 fallback |
| `logistics` | `llm-general-32b` | 弱网可降级本地小模型 |

合规硬规则优先级必须高于客户端指定模型。finance 即使请求 `gpt-4o`，也应在网关直接返回 403，而不是把请求发到云端后再拒绝。

---

## 45.2 多租户隔离：不是“一租户一把 Key”

多租户模型治理至少有四层：

1. **认证**：谁在调用；
2. **授权**：允许调用哪些模型和能力；
3. **配额**：允许消耗多少 RPM/TPM/并发/预算；
4. **观测**：调用、费用、缓存与错误能否按 tenant 回放。

![图45-2：租户隔离是认证、授权、配额、观测四层叠加，而非单一 API Key](../../images/part8/ch/ch45-02.png)

*图45-2：租户隔离是认证、授权、配额、观测四层叠加，而非单一 API Key。来源：本书自绘。Alt text：四层由外到内。认证（谁在调）、授权（允许调什么）、配额（能调多少）、观测（调了什么），每层标注治理对象，体现多层隔离比单一 Key 更健壮。*

### tenant 只能来自可信身份映射

客户端 `X-Tenant-Id` 不能作为权威身份。更稳的做法是：

```text
API Key / OAuth / mTLS identity
        ↓
server-side registry
        ↓
tenant_id + agent_id + scopes + cost_center
```

请求 Header 可以携带租户信息用于诊断，但最终授权必须由服务端身份映射覆盖。否则攻击者只需伪造 Header 就可能绕过模型白名单。

Kubernetes Namespace 也不能替代 LLM 租户。Namespace 管容器、网络和资源配额；Token、模型白名单和供应商访问属于应用语义，需要网关或策略服务控制。

### 配额要拆成不同资源

只做 RPM 限流会同时误伤短问答、放过超长上下文。生产网关至少应区分：

- RPM：请求频率；
- TPM：Token 吞吐；
- concurrent streams：长连接占用；
- daily/monthly budget：成本上限；
- model-specific quota：昂贵模型或高风险模型额度。

业务高峰的临时提额必须有 owner、开始时间和过期时间。**没有自动回收条件的“临时配额”通常会变成永久成本。**

---

## 45.3 路由决策：先合规，再任务，再成本和延迟

路由不应退化为 `if model == ... then URL`。它更像一条带优先级的决策链：

```text
身份认证
  ↓
合规硬约束
  ↓
任务类型与能力要求
  ↓
成本 / 延迟 / 容量
  ↓
选择 backend
  ↓
显式 fallback_chain
```

![图45-3：路由是带优先级的决策链，降级是显式配置的 fallback_chain](../../images/part8/ch/ch45-03.png)

*图45-3：路由是带优先级的决策链，降级是显式配置的 fallback_chain。来源：本书自绘。Alt text：决策链按优先级检查条件，匹配则路由到目标 backend，不匹配则下移；fallback_chain 在主 backend 不可用时按序切换，体现降级路径显式预配。*

*表45-3：路由规则示例。来源：本书整理。*

| 优先级 | 条件 | 目标 |
|---|---|---|
| 1 | `compliance_zone=finance` | 本地 `llm-general-32b` |
| 2 | `task_type=code/sql` | `llm-code-7b` |
| 3 | 租户允许云端且显式请求 | 外部模型 |
| 4 | 默认 | `llm-general-32b` |
| fallback | backend 5xx/超时 | 备用本地模型、缓存或异步 |

合规规则不可被客户端 `model` 字段覆盖。任务路由则应结合模型能力矩阵：是否支持 tool call、JSON、长上下文、流式和特定领域评测。

### fallback 必须是预验证路径

fallback 的目标不是“随便找一个还能返回文本的模型”。备用模型应经过对应任务样本验证，并明确：

- 哪些任务允许替代；
- 结构化输出是否兼容；
- context length 是否足够；
- 是否允许数据出域；
- 降级后如何提示用户；
- 最多 fallback 几次。

fallback DAG 要无环。如果主模型失败后回到同一服务的另一个别名，可能形成 502/重试风暴。

### 第44章 Canary 与网关路由不要双重切流

KServe 已经对同一服务名做 Revision 5%/20%/50% Canary 时，网关仍只指向稳定 Service 名。不要再在网关创建 `llm-general-32b-canary` 并做第二层随机流量，否则质量、延迟和成本指标无法解释。

---

## 45.4 统一接口、错误语义与 Trace

Runtime、Console 和网关之间的接口越稳定，底层模型生态变化对业务影响越小。

```text
POST /v1/chat/completions
Headers:
  Authorization: Bearer <platform-key>
  X-Task-Type: nl2sql
  traceparent: 00-<trace_id>-...

Request:
{
  "model": "llm-general-32b",
  "messages": [...],
  "stream": true,
  "metadata": {
    "agent_id": "data_agent",
    "session_id": "s_001"
  }
}
```

建议返回可诊断 Header：

```text
X-Route-Backend: kserve-llm-general-32b
X-Token-Usage-Billed: 1523
X-Policy-Version: gateway-policy-v18
```

错误语义要让 Runtime 知道下一步该做什么：

| 状态 | 语义 | Runtime 建议 |
|---|---|---|
| 401 | 身份无效 | 终止，不重试 |
| 403 | 模型/策略不允许 | 终止或请求授权 |
| 429 | 限流/配额 | 按 `Retry-After` 退避 |
| 502 | backend 不可用 | 按策略短重试/fallback |
| 503 | 已降级或服务不可用 | 提示、异步或人工路径 |

**429 不是“模型坏了”，403 也不是“平台不稳定”。** 把策略拒绝、容量保护和技术故障混成一个错误码，会让业务、SRE 和 Runtime 做出完全错误的恢复动作。

### Trace 不断链

![图45-4：Trace 不断链，tenant 标签只在网关注入](../../images/part8/ch/ch45-04.png)

*图45-4：Trace 不断链，tenant 标签只在网关注入。来源：本书自绘。Alt text：Trace 从 Agent 发起贯穿网关到模型供应商，tenant 标签在网关统一注入而非每个 Agent 各自打标，箭头标出标签注入点，体现治理集中在网关一处。*

每次调用至少记录：

```text
tenant_id
agent_id
model
backend
route_rule_id
policy_version
fallback_reason
cache_hit
input_tokens / output_tokens
estimated_cost
trace_id
```

这些字段应和第38章 Trace、第41章 FinOps 使用同一命名，避免“网关一套 tenant 名，成本报表另一套 tenant 名”。

---

## 45.5 缓存、限流与成本治理

网关 cache 和模型层 prefix/KV cache 是不同层次。

*表45-4：两类缓存的边界。来源：本书整理。*

| 缓存 | 复用对象 | 适合 | 风险 |
|---|---|---|---|
| 网关 semantic/result cache | 答案、模板、分析计划 | FAQ、稳定指标解释 | 过期/跨租户复用 |
| 后端 prefix/KV cache | 模型前缀计算 | 长系统 Prompt、稳定 schema | 绑定具体引擎 |

语义缓存的 key 不能只有 prompt hash。至少要考虑：

```text
tenant_id + model + prompt/context fingerprint
+ policy_version + tool_version + data/metric version
```

finance 等高敏场景可以禁用跨 session 结果缓存，只保留安全的 prefix cache 或固定说明缓存。

**缓存命中率不是独立优化目标。** 如果命中率升高同时伴随用户追问、报告退回或 EvidenceRef 失效，说明缓存边界过宽。

限流则必须和 Runtime 重试预算协同。收到 429 后固定 100ms 无限重试，会把网关保护机制反向变成流量放大器。每个 session/Run 应有最大重试次数和总 backoff 预算。

成本归因最好落到“成功任务成本”而非单次请求。网关负责提供 token、backend、fallback 与 tenant 事实，第41章再把它与工具、缓存、人工复核共同计算。

---

## 45.6 实现与上线：LiteLLM 作为初版语义网关

*表45-5：几类网关方案的定位。来源：本书整理。*

| 方案 | 强项 | 适合 |
|---|---|---|
| LiteLLM | 多 backend、OpenAI 兼容 | 初版统一 LLM 入口 |
| Portkey | 路由、缓存、可观测 | SaaS/平台化治理 |
| Higress/Kong AI | TLS、WAF、API 网关生态 | 已有 API Gateway 体系 |
| 自研 | 深度业务策略 | 超大规模、特殊合规 |

本书推荐初版使用 LiteLLM 承担 LLM 语义、模型映射和基础路由；已有 Higress/Kong 的企业可以让前置网关继续负责 TLS/WAF/IP allowlist。**API 网关和 LLM 网关可以叠加，但职责不要重叠。**

### LiteLLM 配置示意

```yaml
model_list:
  - model_name: llm-general-32b
    litellm_params:
      model: openai/llm-general-32b
      api_base: http://llm-general-32b.model-serving.svc:8000/v1

  - model_name: llm-code-7b
    litellm_params:
      model: openai/llm-code-7b
      api_base: http://llm-code-7b.model-serving.svc:8000/v1

  - model_name: gpt-4o-fallback
    litellm_params:
      model: gpt-4o
      api_key: os.environ/OPENAI_API_KEY

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
```

生产环境还必须在策略层补齐：API Key → tenant 映射、`allowed_models`、日/月配额、合规路由和审计字段。不要把这些规则只放进管理后台手工修改；第46章应把策略版本纳入 GitOps 或受控策略仓库。

### 切流顺序

较稳的上线流程是：

1. staging 单租户验证 KServe backend；
2. 建立 tenant Key、白名单和配额；
3. 验证错误语义、Trace 与成本字段；
4. 测试 fallback、限流和缓存；
5. 按应用/租户分批切流；
6. NetworkPolicy 收紧直连 KServe；
7. 保留有时限、有审批的 break-glass 路径。

**只把 `OPENAI_BASE_URL` 改成网关地址，还不算完成统一入口。** 如果业务 Pod 仍能直接访问模型 Service，故障时就很容易有人绕过网关，平台重新回到多入口失控。

---

## 45.7 生产治理：影子评估、策略演练与租户争议

网关是集中治理点，也会成为集中故障点。路由规则、模型白名单、fallback、缓存和配额变化，应先经过固定样本或影子评估。

### 影子策略

真实请求继续执行旧策略，新策略只计算“如果生效会怎样”：

- 路由到哪个模型；
- 是否会被拒绝；
- 是否触发 fallback；
- 预计成本怎样变化；
- 合规路径是否变化。

影子结果可以发现“省了成本但把 finance 路由到云端”这类不能用单一指标判断的问题。

### 固定探测样本

至少持续验证：

- finance 请求云端模型 → 403；
- tenant 超预算 → 稳定 429 + `Retry-After`；
- 主 backend 下线 → 只 fallback 一次；
- fallback 目标与审计字段一致；
- cache key 不跨租户；
- Trace 从 Runtime 穿过网关到模型服务。

### 高频故障

*表45-6：网关高频失败模式。来源：本书整理。*

| 失败 | 根因 | 处理 |
|---|---|---|
| fallback 风暴 | DAG 成环、Runtime 无限重试 | 静态校验 + 重试预算 |
| 租户串扰 | 信任客户端 tenant Header | server-side identity mapping |
| cache 污染 | key 缺 tenant/version | 加入租户与版本上下文 |
| 配额误配 | 临时额度未回收 | 配额变更审批 + 到期时间 |
| 网关单点 | 限流 Redis/网关副本故障 | 多副本、Redis HA、明确 fail-open/closed |

网关策略还会引发多租户资源争议。争议应回到运行证据：任务类型、模型、TPM、并发、成本、重试、限流原因、用户影响和业务价值。高价值交互任务可以申请临时容量，低价值批任务更适合转异步；如果消耗来自错误重试，先修调用方而不是盲目提额。

**网关的长期价值，是把模型使用从“每个团队自己接 API”变成一组可解释、可审计、可回退的共享规则。**

## 本章小结

LLM 网关是模型调用的统一控制平面。多租户隔离不能只靠 API Key，而要同时覆盖认证、授权、配额和观测；tenant 必须来自可信身份映射。路由应先执行合规硬约束，再按任务能力、成本、延迟和容量选择 backend，fallback 必须无环并经过任务级验证。网关错误码需要指导 Runtime 正确重试或终止，Trace 与成本字段要使用统一命名。语义缓存必须绑定租户、模型、策略和数据版本，限流要和 Runtime 重试预算协同。LiteLLM 适合作为初版 LLM 语义网关，但企业仍需补齐租户策略、合规路由、审计与 GitOps。统一入口的验收标准不是“请求能转发”，而是任何模型调用都能回答：谁调用、为什么路由到这里、花了多少、是否降级、能否复盘。

## 参考文献

LiteLLM. (n.d.). [Documentation](https://docs.litellm.ai/).

Portkey. (n.d.). [AI Gateway documentation](https://portkey.ai/docs).

Kong. (n.d.). [AI Gateway documentation](https://docs.konghq.com/gateway/latest/ai-gateway/).

Envoy Proxy. (n.d.). [Documentation](https://www.envoyproxy.io/docs/envoy/latest/).
