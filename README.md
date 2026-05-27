# 择时策略系统

这是一个面向指数/ETF 择时研究的策略挖掘系统。系统采用固定 Python 计算内核、FastAPI 后端和 Vite + React 前端；GPT 只作为“研究员”，负责提出中文假设、生成表达式、做语义审核、回测反思和进化建议。

## 快速启动

建议先打开两个终端：一个跑后端，一个跑前端。

### 1. 安装 Python 依赖

在项目根目录执行：

```bash
cd /Users/linaismith/Desktop/实习/论文复刻/Timing_Strategy
pip install -r requirements.txt
```

### 2. 安装前端依赖

```bash
cd /Users/linaismith/Desktop/实习/论文复刻/Timing_Strategy/frontend
npm install
```

### 3. 配置 OpenAI API

在项目根目录复制环境变量模板：

```bash
cd /Users/linaismith/Desktop/实习/论文复刻/Timing_Strategy
cp .env.example .env
```

然后编辑 `.env`，填入：

```text
OPENAI_API_KEY=你的OpenAI API Key
OPENAI_MODEL=gpt-5.4
TIMING_STRATEGY_DB=output/storage/timing_strategy.sqlite3
```

如果客户账号里的模型名不是 `gpt-5.4`，就把 `OPENAI_MODEL` 改成实际可用模型名。

没有配置 API Key 时，系统会明确返回“未接入 LLM”，不会生成假结果。

### 4. 准备行情数据

把 CSV 或 Parquet 行情数据放到：

```text
data/raw/
```

当前项目已经支持 `.csv`、`.parquet`、`.pq`。前端会自动扫描 `data/raw/`，并在顶部下拉框里显示可选数据文件，不需要手动输入完整路径。

项目提供了 Tushare 下载 notebook：

```text
data/download_data.ipynb
```

当前 notebook 默认下载 `513860.SH`，保存到：

```text
data/raw/513860_etf.parquet
```

### 5. 启动后端

在项目根目录执行：

```bash
cd /Users/linaismith/Desktop/实习/论文复刻/Timing_Strategy
uvicorn timing_strategy.api.main:app --reload --port 8000
```

后端启动后可以打开：

```text
http://127.0.0.1:8000/
```

这是 FastAPI 后端中文调试首页，可以查看服务状态、运行列表、启动真实运行、查看运行 JSON、删除单次运行或清空运行记录与报告。

接口文档地址：

```text
http://127.0.0.1:8000/docs
```

### 6. 启动前端

另开一个终端：

```bash
cd /Users/linaismith/Desktop/实习/论文复刻/Timing_Strategy/frontend
npm run dev
```
## 访问
```text
http://localhost:5173/
```


## CLI 运行方式

除了前端，也可以用命令行跑一次真实流程：

```bash
cd /Users/linaismith/Desktop/实习/论文复刻/Timing_Strategy
python -m timing_strategy.cli run --data data/raw/513860_etf.parquet --name "513860 ETF 首次运行"
```

查看历史运行记录：

```bash
python -m timing_strategy.cli list-runs
```

CLI 和前端使用的是同一套 Python 内核、同一个 SQLite trace 存储。

## 输出位置

所有运行产出统一保存在 `output/` 目录下：

```text
output/
  storage/timing_strategy.sqlite3   # SQLite trace 数据库
  reports/                          # Markdown / JSON 报告
```

其中：

- `output/storage/timing_strategy.sqlite3` 保存完整 trace，包括每个 Agent 的 prompt、输入、输出、校验结果、回测指标、反思和 lineage。
- `output/reports/` 保存 Markdown 和 JSON 报告，文件名包含运行时间、运行名称和短 run id，方便区分不同产出。

报告文件示例：

```text
output/reports/20260528_040801_513860_ETF_首次运行_29daf059.md
output/reports/20260528_040801_513860_ETF_首次运行_29daf059.json
```

## 数据格式

首版要求行情数据至少包含以下字段：

```text
date, open, high, low, close, volume, amount
```

字段名不区分大小写。系统会自动按日期排序，并计算收益率字段。

Tushare 常见字段可以直接读取：

```text
trade_date, open, high, low, close, vol, amount
```

系统会自动映射：

- `trade_date` -> `date`
- `vol` -> `volume`

如果没有读取到数据文件，系统会明确返回“未读取到行情数据”，不会使用演示数据兜底。


## 系统介绍

本系统借鉴 QuantaAlpha 的 trajectory、mutation、crossover 思路，但将任务从“横截面选股因子”改造成“时间序列择时信号”。

核心边界：

- GPT 只负责研究逻辑，不负责执行回测代码。
- 因子值计算、仓位映射、回测、指标统计全部由固定 Python 文件完成。
- 前端只负责展示和触发任务，不参与任何策略计算。
- 客户可见的 README、prompt、日志、报告、前端文案均为中文。

## 前端能看到什么

- 运行列表：每次 run 的状态、模型、候选因子数量和最佳指标。
- 运行时间线：逐步查看市场摘要、假设、表达式、校验、回测、反思和进化。
- Prompt 查看器：完整中文 prompt、输入上下文、模型原始输出。
- 因子详情：中文假设、标准表达式、AST、仓位规则和校验结果。
- 回测面板：策略净值、基准净值、仓位变化。
- 进化谱系：展示 initialization、mutation、crossover 之间的父子关系。
- Factor Pool：展示已经回测的因子及其指标。

关于“AI 怎么思考”：

- 前端展示完整 prompt、输入、输出、验证意见、反思总结和进化建议。
- 不展示模型不可见的内部推理链。
- Agent 会显式输出中文 `reason_summary`、`decision_reason`、`failure_reason`，用于审计和展示。

## 目录结构

```text
Timing_Strategy/
  configs/                 # 系统配置
  data/raw/                # 本地行情 CSV / Parquet
  data/processed/          # 处理后数据和中间产物
  output/                  # 统一运行产出目录
    reports/               # Markdown / JSON 报告
    storage/               # SQLite trace 数据库
  timing_strategy/
    api/                   # FastAPI 后端
    llm/                   # GPT API 封装、prompt 加载、输出结构
    agents/                # 多 Agent 工作流
    prompts/               # 中文 prompt 模板
    data/                  # 行情读取与标准化
    operators/             # 固定择时算子库
    parser/                # 表达式解析和 AST
    validation/            # 语法、参数、复杂度校验
    engine/                # 固定因子计算和仓位映射
    backtest/              # 固定回测逻辑
    metrics/               # 固定指标计算
    evolution/             # mutation / crossover 辅助逻辑
    storage/               # SQLite trace 存储
  frontend/                # Vite + React 可视化前端
  tests/                   # 自动化测试
```

## 重要约束

- 不使用 `eval` 执行表达式。
- LLM 不能生成或修改 Python 回测代码。
- 表达式只能使用白名单字段和白名单算子。
- 首版仓位限定为 `[0, 1]`，只做多头/空仓，不做卖空。
- 默认第 t 日生成信号，第 t+1 日执行，避免未来函数。
