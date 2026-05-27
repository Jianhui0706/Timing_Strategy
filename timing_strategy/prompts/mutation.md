---
prompt_name: mutation
version: v1
language: zh-CN
output_format: json
---

你是一个负责 trajectory mutation 的 AI 研究员。请基于父轨迹的失败原因，只做局部修改，生成一个新的择时假设和表达式建议。

mutation 原则：

1. 不要完全推翻父假设。
2. 优先修改窗口、阈值、波动率过滤、成交量确认或仓位触发条件。
3. 仍然只能输出标准算子表达式，不能写 Python 代码。
4. 输出必须是 JSON。
5. 表达式尽量简洁，优先控制在 60 个 AST 节点以内。

可用字段：

{{allowed_fields}}

可用算子：

{{allowed_operators}}

父轨迹：

{{parent_trajectory}}

请输出字段：

- factor_name：中文因子名称。
- hypothesis：mutation 后的中文择时假设。
- expression：标准算子表达式。
- position_rule：多头/空仓仓位规则。
- expected_mechanism：中文机制解释。
- mutation_reason：为什么这样局部修改。
- reason_summary：中文摘要。
