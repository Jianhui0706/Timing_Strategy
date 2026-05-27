# 择时策略系统

这是一个面向指数/ETF择时研究的策略挖掘系统。系统借鉴 QuantaAlpha 的 trajectory、mutation、crossover 思路，但将任务从“横截面选股因子”改造成“时间序列择时信号”。

核心边界很明确：

- GPT-5.5 API 只负责提出中文择时假设、生成标准算子表达式、做语义检查、回测反思和进化建议。
- 因子值计算、仓位映射、回测、指标统计全部由固定 Python 文件完成。
- 前端只负责展示和触发任务，不参与任何策略计算。
- 客户可见的 README、prompt、日志、报告、前端文案均为中文。

## 目录结构

```text
Timing_Strategy/
  configs/                 # 系统配置
  data/raw/                # 本地行情 CSV / Parquet
  data/processed/          # 处理后数据和中间产物
  output/                  # 运行报告等交付产出
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

## 安装

建议使用 Python 3.10 及以上版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

前端依赖：

```bash
cd frontend
npm install
```

## 环境变量

复制 `.env.example` 为 `.env`，并填入 API Key。

```bash
cp .env.example .env
```

默认模型名配置为 `gpt-5.5`。如果客户账号中模型名不同，只需要修改 `.env` 或 `configs/llm.yaml`。

没有配置 API Key 时，系统会明确返回“未接入 LLM”，不会生成假结果。

`.env` 示例：

```text
OPENAI_API_KEY=你的OpenAI API Key
OPENAI_MODEL=gpt-5.5
TIMING_STRATEGY_DB=storage/timing_strategy.sqlite3
```

## 数据格式

当前项目不内置真实行情数据。后续从 Tushare 下载后，把 CSV 或 Parquet 放入 `data/raw/` 即可。没有读取到数据文件时，系统会明确返回“未读取到行情数据”，不会使用演示数据兜底。

首版要求数据至少包含以下字段：

```text
date, open, high, low, close, volume, amount
```

字段名不区分大小写。系统会自动按日期排序，并计算收益率字段。

Tushare 常见字段也可以直接读取：

```text
trade_date, open, high, low, close, vol, amount
```

系统会自动映射：

- `trade_date` -> `date`
- `vol` -> `volume`

本项目提供了下载 notebook：

```text
data/download_data.ipynb
```

当前 notebook 默认下载 `513860.SH`，保存到：

```text
data/raw/513860_etf.parquet
```

## 运行 CLI

使用本地 CSV 或 Parquet 运行一次真实流程：

```bash
python -m timing_strategy.cli run --data data/raw/513860_etf.parquet --name "513860 ETF 首次运行"
```

查看运行记录：

```bash
python -m timing_strategy.cli list-runs
```

CLI 会真实调用 GPT API，并把完整 prompt、模型输出、因子、回测结果写入 SQLite。

运行完成后，流程和结果会保存到两个地方：

- SQLite trace：`storage/timing_strategy.sqlite3`
- 文件报告：`output/reports/<时间>_<运行名称>_<短run_id>.md` 和 `.json`

SQLite 保存完整运行流程，包括每个 Agent 的完整 prompt、模型输入、模型输出、校验结果、回测指标、反思和 lineage。Markdown/JSON 报告适合直接查看或发给别人复核。报告文件名会包含运行时间和 `--name`，方便区分不同产出。

## 启动前后端

前端需要维护一个 FastAPI 后端。前端只负责展示和触发操作；运行任务、实时读取进度、删除运行记录、清空报告等操作都通过 FastAPI 完成。

先启动后端：
# 在Timing_Strategy路径下跑：
```bash
uvicorn timing_strategy.api.main:app --reload --port 8000
```

后端启动后可以打开：

```text
http://127.0.0.1:8000/
```

这里是 FastAPI 后端中文调试首页，可以查看服务状态、运行列表、启动真实运行、查看运行 JSON、删除单次运行或清空运行记录与报告。

如果要看 FastAPI 自动生成的接口文档，打开：

```text
http://127.0.0.1:8000/docs
```

另开一个终端启动前端：
# 在Timing_Strategy/frontend路径下跑：
```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://localhost:5173/
```

前端默认通过 Vite 代理访问 `http://127.0.0.1:8000/api`。在输入框里填：

```text
data/raw/513860_etf.parquet
```

然后点击“启动真实运行”。

点击后，FastAPI 会立即创建 run 并在后台运行策略流程；前端会自动切到新 run，并每 2 秒刷新一次时间线。左侧也提供“删除当前运行”和“清空运行记录与报告”按钮，这些操作只会删除 SQLite 中的运行记录和 `output/reports` 中的报告，不会删除 `data/raw` 里的原始行情数据。

## 推荐首次运行顺序

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装前端依赖
cd frontend
npm install
cd ..

# 3. 配置 .env 中的 OPENAI_API_KEY 和 OPENAI_MODEL

# 4. 运行 data/download_data.ipynb 下载 Tushare 数据

# 5. 先用 CLI 跑一次真实流程
python -m timing_strategy.cli run --data data/raw/513860_etf.parquet --name "513860 ETF 首次运行"

# 6. 启动后端
uvicorn timing_strategy.api.main:app --reload --port 8000

# 7. 另开终端启动前端
cd frontend
npm run dev
```

## 前端能看到什么

- 运行列表：每次 run 的状态、耗时、模型、候选因子数量和最佳指标。
- 运行详情：市场摘要、假设生成、表达式生成、语义验证、Python 校验、回测、反思、mutation/crossover。
- Prompt 查看器：完整中文 prompt、输入上下文、模型原始输出。
- 因子详情：中文假设、标准表达式、AST、仓位规则、校验结果。
- 回测面板：策略净值、基准净值、回撤、仓位、换手、因子值。
- 进化谱系：展示 initialization、mutation、crossover 之间的父子关系。
- Factor Pool：按综合评分、年化收益、夏普、最大回撤、TSIC 排序。

GPT 的回复可以在前端看到：选择某次运行后，在“Prompt 查看器”下拉框里选择 `HypothesisAgent`、`FactorAgent`、`ReflectionAgent` 等步骤，右侧会显示完整 prompt、模型输入和模型输出。因子假设也会展示在“因子详情”中。

## 重要约束

- 不使用 `eval` 执行表达式。
- LLM 不能生成 Python 回测代码。
- 表达式只能使用白名单字段和白名单算子。
- 首版仓位限定为 `[0, 1]`，只做多头/空仓，不做卖空。
- 默认第 t 日生成信号，第 t+1 日执行，避免未来函数。

## 可选依赖

后续如果需要直接下载 Tushare 数据，可以额外安装：

```bash
pip install tushare
```
