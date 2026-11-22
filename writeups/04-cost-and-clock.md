# 04 — 成本与时钟：两个不会写进 prompt、但决定生死的约束

PLE 给每个 harness 的预算是 **6 小时 / 题 / 次**，hidden test 跑 3 次，29 题。
如果用自己的 key，**每一次模型调用都是你付钱**：smoke、dev 复现、hidden test ×3。

这一篇讲两件在 prompt 里看不见、但会直接决定"跑不跑得完、付不付得起"的事。

## 96% 的输入是重复的

我在 baseline 的 trace 里找到一个数字：`data-hall-mep-routing` 单题消耗
**1894 万 prompt token，其中 1821 万是 cached**。也就是 96%。

原因不难理解：这一题要读 7 张 PNG 图纸，模型每一步都带着前面读过的全部上下文。
84 步的轨迹里，前缀一直在重复。

对 Claude 来说这有个陷阱：**它只在请求明确标记的地方缓存**。

> Claude caches a prompt prefix only where the request marks it: put
> `"cache_control": {"type": "ephemeral"}` on the system prompt and on the newest message
> (Claude allows 4 such marks). Without the marks every turn pays the full input price.

不打标记 = 每轮为整段历史付全价。cache read 与未缓存的输入单价差一个数量级，
在 84 步的尺度上，这不是"省点钱"，是**同一个 harness 能不能跑完 3 次 hidden test 的差别**。

### 所以 `model.py` 有两条路径

```
MODEL_API = google-cloud/claude-opus-5-5
  ├─ Anthropic 原生（ANTHROPIC_BASE_URL 有值且模型名含 claude）
  │    → POST {base}/v1/messages
  │    → system 作为一个 text block，带 cache_control
  │    → 最新一条 user / tool_result 也带 cache_control
  └─ OpenAI 兼容（其余情况）
       → POST {base}/chat/completions
       → tools 走 function calling
```

为什么不统一走 OpenAI 兼容？因为 `MODEL_BASE_URL` 虽然对所有模型都填了 OpenAI 兼容端点，
但**只有 Anthropic 原生 API 认 `cache_control`**。走兼容层就拿不到显式缓存标记，
96% 的重复前缀就变成 96% 的全价重付。

代价是两条序列化路径要各自正确：assistant 的 `tool_calls` 要转成 `tool_use` block、
`tool` 消息要转成 `tool_result` block、最新的 `tool_result` 还要再打一次 `cache_control`。
这部分我只做了编译级验证，**没有真跑过**——这是 GATE-B 里的 T-03。

## 时钟：84 步意味着每步 4 分钟

`agent_timeout_sec = 21600`（6 小时），单条 `exec` 上限 600 秒。
baseline 平均 84 步 → 每步平均可用预算约 4 分钟，其中大部分要留给模型思考。

我的实现里有两个阈值：

```python
HARD_BUDGET = 0.94      # 到 94% 就无论如何收工
WRAP_BUDGET = 0.80      # 剩 20% 时切"收工模式"
```

到 80% 时，system prompt 追加一段：

> === WRAP-UP MODE ===
> The budget is nearly gone. Stop exploring. Make sure the deliverable at the contract path
> is complete, valid and readable, then call finish with a summary.

到 94% 直接跳出循环，用守卫最后一次结果拼一个 `final_message` 发 `done`。

**为什么不等到 100%？** 因为 evaluator 在超时会发 `{"type": "cancel"}` 然后 10 秒后关 socket。
如果 socket 在 `done` 之前关掉，这一题直接算失败——不是扣分，是这一题没了。
提前留 6% 是为了"永远有机会 say done"。

## 一个我还没校准的推断

官方建议"前 ~100 步出第一版完整交付物，然后原地迭代"，而 baseline 平均只有 84 步。
我从这两个数反推出：**第 10~20 步就该落一个能打开的最小完整包。**

但这个数字是推断的，不是测出来的。它已经写进 system prompt 的非妥协条款里：

> Land a first complete, openable version of the deliverable early (by roughly step 10-20),
> even if values are rough, then rewrite it in place.

用真模型跑 1~2 道 dev 题就能校准它——这也是我把"真模型端到端"排在 `kit check` 之后的第二个原因。

## 一句话总结

分数之外还有两条命：**缓存标记决定你付不付得起，提前收工决定你这一题算不算交**。
两者都不在题面里，都在 `serve.py` 和 `model.py` 的几十行代码里。
