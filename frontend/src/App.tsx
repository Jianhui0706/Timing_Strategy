import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

type RunSummary = {
  id?: string;
  run_id?: string;
  name: string;
  status: string;
  is_active?: boolean;
  runtime_note?: string;
  model?: string;
  started_at?: string;
  ended_at?: string | null;
  factor_count?: number;
  best_score?: number | null;
  summary?: Record<string, unknown>;
};

type RunStep = {
  id: string;
  step_name: string;
  status: string;
  started_at?: string;
  ended_at?: string | null;
  message?: string;
  detail?: Record<string, unknown>;
};

type AgentCall = {
  id: string;
  step_id?: string | null;
  agent_name: string;
  prompt_name: string;
  prompt_version: string;
  full_prompt: string;
  input: unknown;
  output: unknown;
  raw_output?: string;
  token_usage?: Record<string, unknown>;
  created_at?: string;
};

type Evaluation = {
  id: string;
  score?: number | null;
  metrics?: Record<string, unknown>;
  equity_curve?: Array<Record<string, unknown>>;
};

type Factor = {
  id: string;
  trajectory_id?: string;
  factor_name: string;
  phase?: string;
  hypothesis?: string;
  expression?: string;
  ast?: unknown;
  position_rule?: unknown;
  status?: string;
  validation?: unknown;
  evaluation?: Evaluation | null;
  reflection?: unknown;
};

type Lineage = {
  id: string;
  child_factor_id: string;
  parent_factor_id?: string | null;
  relation_type: string;
};

type RunDetail = RunSummary & {
  config?: unknown;
  steps: RunStep[];
  agent_calls: AgentCall[];
  factors: Factor[];
  lineage: Lineage[];
};

type PoolItem = {
  factor_id: string;
  run_id: string;
  factor_name: string;
  hypothesis?: string;
  expression?: string;
  metrics?: Record<string, unknown>;
};

type DataFile = {
  name: string;
  path: string;
  relative_path: string;
  suffix: string;
  size_bytes: number;
  modified_at: number;
};

type HighlightItem = {
  label: string;
  value: string;
};

const DEFAULT_DATA_PATH = "data/raw/513860_etf.parquet";

const FIELD_LABELS: Record<string, string> = {
  market_regime: "市场状态",
  trend_summary: "趋势摘要",
  volatility_summary: "波动摘要",
  volume_summary: "成交摘要",
  risk_summary: "风险摘要",
  hypothesis: "生成假设",
  mechanism_type: "机制类型",
  expected_mechanism: "预期机制",
  risk_hint: "风险提示",
  factor_name: "因子名称",
  expression: "因子表达式",
  position_rule: "仓位规则",
  passed: "是否通过",
  decision_reason: "审核意见",
  issues: "发现问题",
  repair_hint: "修复建议",
  prediction_review: "预测复盘",
  return_review: "收益复盘",
  risk_review: "风险复盘",
  failure_reason: "失败原因",
  likely_root_cause: "可能根因",
  next_action: "下一步动作",
  mutation_hint: "变异建议",
  crossover_hint: "组合建议",
  mutation_reason: "变异理由",
  reason_summary: "理由摘要",
  raw_error: "原始错误",
  error_type: "错误类型",
  diagnosis_error: "原因生成错误"
};

const FIELD_ORDER = [
  "hypothesis",
  "factor_name",
  "expression",
  "position_rule",
  "market_regime",
  "trend_summary",
  "volatility_summary",
  "volume_summary",
  "risk_summary",
  "mechanism_type",
  "expected_mechanism",
  "risk_hint",
  "passed",
  "decision_reason",
  "issues",
  "prediction_review",
  "return_review",
  "risk_review",
  "failure_reason",
  "likely_root_cause",
  "repair_hint",
  "next_action",
  "mutation_hint",
  "crossover_hint",
  "mutation_reason",
  "reason_summary",
  "raw_error",
  "error_type",
  "diagnosis_error"
];

function runId(run: RunSummary): string {
  return run.id || run.run_id || "";
}

function formatNumber(value: unknown, digits = 4): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(digits);
}

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function valueToText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return formatJson(value);
}

function stepHighlights(step: RunStep | undefined, call: AgentCall | undefined): HighlightItem[] {
  const source = asRecord(call?.output) || asRecord(step?.detail) || {};
  const keys = [
    ...FIELD_ORDER.filter((key) => Object.prototype.hasOwnProperty.call(source, key)),
    ...Object.keys(source).filter((key) => !FIELD_ORDER.includes(key)).slice(0, 6)
  ];
  const items = keys
    .map((key) => ({
      label: FIELD_LABELS[key] || key,
      value: valueToText(source[key])
    }))
    .filter((item) => item.value !== "-");

  if (items.length > 0) return items;
  if (step?.message) return [{ label: "步骤消息", value: step.message }];
  return [{ label: "详情", value: "这一步暂时没有可展示的结构化产出。" }];
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = typeof data?.detail === "string" ? data.detail : JSON.stringify(data);
    throw new Error(message);
  }
  return data as T;
}

function App() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [pool, setPool] = useState<PoolItem[]>([]);
  const [dataFiles, setDataFiles] = useState<DataFile[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedStepId, setSelectedStepId] = useState("");
  const [selectedFactorId, setSelectedFactorId] = useState("");
  const [selectedCallId, setSelectedCallId] = useState("");
  const [activeView, setActiveView] = useState<"timeline" | "factor">("timeline");
  const [dataPath, setDataPath] = useState(DEFAULT_DATA_PATH);
  const [runName, setRunName] = useState("513860 ETF 前端运行");
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState("");
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);
  const animatedFactorIdRef = useRef("");

  const loadRuns = useCallback(async () => {
    const nextRuns = await requestJson<RunSummary[]>("/api/runs");
    setRuns(nextRuns);
    if (!selectedRunId && nextRuns.length > 0) {
      setSelectedRunId(runId(nextRuns[0]));
    }
  }, [selectedRunId]);

  const loadPool = useCallback(async () => {
    setPool(await requestJson<PoolItem[]>("/api/factor-pool"));
  }, []);

  const loadDataFiles = useCallback(async () => {
    const files = await requestJson<DataFile[]>("/api/data-files");
    setDataFiles(files);
    if (files.length === 0) {
      setDataPath("");
      return;
    }
    if (files.length > 0 && !files.some((file) => file.path === dataPath)) {
      setDataPath(files[0].path);
    }
  }, [dataPath]);

  const loadDetail = useCallback(
    async (id = selectedRunId) => {
      if (!id) return;
      const nextDetail = await requestJson<RunDetail>(`/api/runs/${id}`);
      setDetail(nextDetail);
      if (!selectedFactorId && nextDetail.factors.length > 0) {
        setSelectedFactorId(nextDetail.factors[0].id);
      }
      if (!selectedCallId && nextDetail.agent_calls.length > 0) {
        setSelectedCallId(nextDetail.agent_calls[0].id);
      }
    },
    [selectedRunId, selectedFactorId, selectedCallId]
  );

  useEffect(() => {
    Promise.all([loadRuns(), loadPool(), loadDataFiles()]).catch((exc) => setError(exc.message));
  }, [loadRuns, loadPool, loadDataFiles]);

  useEffect(() => {
    if (!selectedRunId) return;
    loadDetail(selectedRunId).catch((exc) => setError(exc.message));
  }, [selectedRunId, loadDetail]);

  useEffect(() => {
    const hasRunning = detail?.is_active || runs.some((run) => run.is_active);
    if (!hasRunning) return;
    const timer = window.setInterval(() => {
      loadRuns().catch((exc) => setError(exc.message));
      loadDetail().catch((exc) => setError(exc.message));
      loadPool().catch((exc) => setError(exc.message));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [detail?.status, runs, loadRuns, loadDetail, loadPool]);

  const selectedFactor = useMemo(() => {
    if (!detail) return undefined;
    const found = detail.factors.find((factor) => factor.id === selectedFactorId);
    if (found) return found;
    return selectedFactorId ? undefined : detail.factors[0];
  }, [detail, selectedFactorId]);

  const selectedCall = useMemo(
    () => detail?.agent_calls.find((call) => call.id === selectedCallId) || detail?.agent_calls[0],
    [detail, selectedCallId]
  );

  useEffect(() => {
    if (!detail?.steps.length) {
      setSelectedStepId("");
      return;
    }
    if (!detail.steps.some((step) => step.id === selectedStepId)) {
      setSelectedStepId(detail.steps[0].id);
    }
  }, [detail, selectedStepId]);

  const selectedStep = useMemo(
    () => detail?.steps.find((step) => step.id === selectedStepId) || detail?.steps[0],
    [detail, selectedStepId]
  );

  const selectedStepCall = useMemo(
    () => detail?.agent_calls.find((call) => call.step_id === selectedStep?.id),
    [detail, selectedStep]
  );

  const selectedStepHighlights = useMemo(
    () => stepHighlights(selectedStep, selectedStepCall),
    [selectedStep, selectedStepCall]
  );

  useEffect(() => {
    const resize = () => chartInstanceRef.current?.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstanceRef.current || chartInstanceRef.current.isDisposed()) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }
    const chart = chartInstanceRef.current;
    const curve = selectedFactor?.evaluation?.equity_curve || [];
    const labels = curve.map((row, index) => String(row.date || row.datetime || row.trade_date || index + 1));
    const strategy = curve.map((row) => Number(row.strategy_equity ?? row.equity ?? row.nav ?? 1));
    const benchmark = curve.map((row) => Number(row.benchmark_equity ?? row.benchmark ?? 1));
    const position = curve.map((row) => Number(row.position ?? 0));
    const factorKey = selectedFactor?.id || "empty-chart";
    const shouldAnimate = animatedFactorIdRef.current !== factorKey;
    animatedFactorIdRef.current = factorKey;
    chart.setOption({
      animation: shouldAnimate,
      animationDuration: 700,
      animationDurationUpdate: 0,
      animationEasing: "cubicOut",
      tooltip: { trigger: "axis" },
      legend: { top: 0, data: ["策略净值", "基准净值", "仓位"] },
      grid: { left: 48, right: 28, top: 46, bottom: 38 },
      xAxis: { type: "category", data: labels, axisLabel: { hideOverlap: true } },
      yAxis: [
        { type: "value", name: "净值", scale: true },
        { type: "value", name: "仓位", min: 0, max: 1 }
      ],
      series: [
        { name: "策略净值", type: "line", showSymbol: false, data: strategy },
        { name: "基准净值", type: "line", showSymbol: false, data: benchmark },
        { name: "仓位", type: "line", showSymbol: false, yAxisIndex: 1, data: position }
      ]
    }, { notMerge: true });
  }, [selectedFactor]);

  async function startRun() {
    setIsStarting(true);
    setError("");
    try {
      const response = await requestJson<{ run_id: string; status: string }>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ name: runName, data_path: dataPath })
      });
      setSelectedRunId(response.run_id);
      await loadRuns();
      await loadDetail(response.run_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setIsStarting(false);
    }
  }

  async function deleteCurrentRun() {
    if (!detail) return;
    if (!window.confirm("确定删除当前运行记录和对应报告吗？")) return;
    try {
      await requestJson(`/api/runs/${runId(detail)}`, { method: "DELETE" });
      setDetail(null);
      setSelectedRunId("");
      setSelectedStepId("");
      setSelectedFactorId("");
      setSelectedCallId("");
      await loadRuns();
      await loadPool();
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  async function clearAllRuns() {
    if (!window.confirm("确定清空全部运行记录和 output/reports 报告吗？原始行情数据不会删除。")) return;
    try {
      await requestJson("/api/runs", { method: "DELETE" });
      setDetail(null);
      setSelectedRunId("");
      setSelectedStepId("");
      setSelectedFactorId("");
      setSelectedCallId("");
      await loadRuns();
      await loadPool();
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>择时策略系统</h1>
          <p>固定 Python 内核 + GPT 研究员 + 全流程 Trace</p>
        </div>
        <div className="run-form">
          <input value={runName} onChange={(event) => setRunName(event.target.value)} aria-label="运行名称" />
          <select value={dataPath} onChange={(event) => setDataPath(event.target.value)} aria-label="行情数据文件">
            {dataFiles.length === 0 ? (
              <option value="">data/raw 中暂无 CSV 或 Parquet 数据</option>
            ) : (
              dataFiles.map((file) => (
                <option value={file.path} key={file.path}>
                  {file.relative_path}
                </option>
              ))
            )}
          </select>
          <button type="button" onClick={() => loadDataFiles().catch((exc) => setError(exc.message))}>
            刷新数据
          </button>
          <button className="primary" onClick={startRun} disabled={isStarting || !dataPath}>
            {isStarting ? "启动中..." : "启动真实运行"}
          </button>
        </div>
      </header>

      {error && <div className="notice">{error}</div>}

      <section className="layout">
        <aside className="sidebar">
          <section className="panel">
            <div className="panel-title">
              <h2>运行列表</h2>
              <button onClick={() => loadRuns()}>刷新</button>
            </div>
            <div className="list">
              {runs.map((run) => (
                <button
                  key={runId(run)}
                  className={`list-item ${runId(run) === selectedRunId ? "active" : ""}`}
                  onClick={() => {
                    setSelectedRunId(runId(run));
                    setSelectedStepId("");
                    setSelectedFactorId("");
                    setSelectedCallId("");
                    setActiveView("timeline");
                  }}
                >
                  <strong>{run.name}</strong>
                  <span>
                    {run.status}
                    {run.is_active ? " · 真实运行中" : ""}
                    {" · "}
                    {run.factor_count ?? 0} 个因子
                  </span>
                  <span>score {formatNumber(run.best_score)}</span>
                </button>
              ))}
              {runs.length === 0 && <p className="empty">暂无运行记录。</p>}
            </div>
            <div className="danger-row">
              <button onClick={deleteCurrentRun} disabled={!detail || detail.is_active}>
                删除当前运行
              </button>
              <button onClick={clearAllRuns} disabled={runs.length === 0 || runs.some((run) => run.is_active)}>
                清空运行记录与报告
              </button>
            </div>
          </section>

          <section className="panel">
            <h2>Factor Pool</h2>
            <div className="list">
              {pool.map((item) => (
                <button
                  key={item.factor_id}
                  className={`list-item ${item.factor_id === selectedFactorId ? "active" : ""}`}
                  onClick={() => {
                    setSelectedRunId(item.run_id);
                    setSelectedFactorId(item.factor_id);
                    setActiveView("factor");
                  }}
                >
                  <strong>{item.factor_name}</strong>
                  <span>score {formatNumber(item.metrics?.score)}</span>
                </button>
              ))}
              {pool.length === 0 && <p className="empty">暂无已回测因子。</p>}
            </div>
          </section>
        </aside>

        <section className={`content ${activeView === "factor" ? "factor-first" : ""}`}>
          {!detail ? (
            <div className="panel empty-state">请选择一次运行，或启动一轮真实流程。</div>
          ) : (
            <>
              <section className="stats">
                <div>
                  <span>模型</span>
                  <strong>{detail.model || "-"}</strong>
                </div>
                <div>
                  <span>状态</span>
                  <strong>{detail.is_active ? `${detail.status} · 真实运行中` : detail.status}</strong>
                </div>
                <div>
                  <span>因子数</span>
                  <strong>{detail.factor_count ?? detail.factors.length}</strong>
                </div>
                <div>
                  <span>最佳分数</span>
                  <strong>{formatNumber(detail.best_score)}</strong>
                </div>
              </section>

              <div className="view-switch" aria-label="详情视图切换">
                <button
                  type="button"
                  className={activeView === "timeline" ? "active" : ""}
                  onClick={() => setActiveView("timeline")}
                >
                  运行时间线
                </button>
                <button
                  type="button"
                  className={activeView === "factor" ? "active" : ""}
                  onClick={() => setActiveView("factor")}
                >
                  因子详情
                </button>
              </div>

              <section className="panel timeline-panel">
                <h2>运行时间线</h2>
                <div className="timeline">
                  {detail.steps.map((step) => {
                    const stepCall = detail.agent_calls.find((call) => call.step_id === step.id);
                    return (
                      <button
                        type="button"
                        className={`step ${step.status} ${selectedStep?.id === step.id ? "active" : ""}`}
                        key={step.id}
                        onClick={() => {
                          setSelectedStepId(step.id);
                          if (stepCall) {
                            setSelectedCallId(stepCall.id);
                          }
                        }}
                      >
                        <strong>{step.step_name}</strong>
                        <span>{step.status}</span>
                        <span>{step.message || (stepCall ? "点击查看模型输出" : "点击查看步骤详情")}</span>
                      </button>
                    );
                  })}
                </div>
                {selectedStep && (
                  <div className="step-inspector">
                    <div className="step-inspector-head">
                      <div>
                        <h3>{selectedStep.step_name}</h3>
                        <p>
                          {selectedStepCall
                            ? `${selectedStepCall.agent_name} / ${selectedStepCall.prompt_name}`
                            : "固定 Python 步骤"}
                        </p>
                      </div>
                      <span>{selectedStep.status}</span>
                    </div>
                    <div className="highlight-grid">
                      {selectedStepHighlights.map((item) => (
                        <article key={item.label}>
                          <span>{item.label}</span>
                          <p>{item.value}</p>
                        </article>
                      ))}
                    </div>
                    {selectedStepCall ? (
                      <details>
                        <summary>展开完整 prompt、输入和原始输出</summary>
                        <h3>完整中文 Prompt</h3>
                        <pre>{selectedStepCall.full_prompt}</pre>
                        <h3>模型输入</h3>
                        <pre>{formatJson(selectedStepCall.input)}</pre>
                        <h3>模型原始输出</h3>
                        <pre>{selectedStepCall.raw_output || formatJson(selectedStepCall.output)}</pre>
                      </details>
                    ) : (
                      <details>
                        <summary>展开 Python 步骤详情</summary>
                        <pre>{formatJson(selectedStep.detail)}</pre>
                      </details>
                    )}
                  </div>
                )}
              </section>

              <section className="two-column factor-panel">
                <div className="panel">
                  <h2>因子详情</h2>
                  <select
                    value={selectedFactor?.id || ""}
                    onChange={(event) => {
                      setSelectedFactorId(event.target.value);
                      setActiveView("factor");
                    }}
                  >
                    {detail.factors.map((factor) => (
                      <option value={factor.id} key={factor.id}>
                        {factor.factor_name}
                      </option>
                    ))}
                  </select>
                  {selectedFactor && (
                    <div className="detail-block">
                      <h3>{selectedFactor.factor_name}</h3>
                      <p>{selectedFactor.hypothesis || "暂无假设文本。"}</p>
                      <code>{selectedFactor.expression || "-"}</code>
                      <dl>
                        <dt>状态</dt>
                        <dd>{selectedFactor.status || "-"}</dd>
                        <dt>得分</dt>
                        <dd>{formatNumber(selectedFactor.evaluation?.score)}</dd>
                        <dt>阶段</dt>
                        <dd>{selectedFactor.phase || "-"}</dd>
                      </dl>
                      <h3>仓位规则</h3>
                      <pre>{formatJson(selectedFactor.position_rule)}</pre>
                    </div>
                  )}
                </div>

                <div className="panel">
                  <h2>回测面板</h2>
                  <div className="chart" ref={chartRef} />
                </div>
              </section>

              <section className="two-column trace-panel">
                <div className="panel">
                  <h2>Prompt 查看器</h2>
                  <select value={selectedCall?.id || ""} onChange={(event) => setSelectedCallId(event.target.value)}>
                    {detail.agent_calls.map((call) => (
                      <option value={call.id} key={call.id}>
                        {call.agent_name} / {call.prompt_name}
                      </option>
                    ))}
                  </select>
                  {selectedCall && (
                    <>
                      <h3>完整中文 Prompt</h3>
                      <pre>{selectedCall.full_prompt}</pre>
                      <h3>模型输入</h3>
                      <pre>{formatJson(selectedCall.input)}</pre>
                      <h3>模型输出</h3>
                      <pre>{selectedCall.raw_output || formatJson(selectedCall.output)}</pre>
                    </>
                  )}
                </div>

                <div className="panel">
                  <h2>校验、反思与谱系</h2>
                  <h3>Python 校验</h3>
                  <pre>{formatJson(selectedFactor?.validation)}</pre>
                  <h3>回测反思</h3>
                  <pre>{formatJson(selectedFactor?.reflection)}</pre>
                  <h3>Lineage</h3>
                  <pre>{formatJson(detail.lineage)}</pre>
                </div>
              </section>

              <section className="panel report-panel">
                <h2>报告路径</h2>
                <pre>{formatJson(detail.summary?.report_paths || detail.summary)}</pre>
              </section>
            </>
          )}
        </section>
      </section>
    </main>
  );
}

export default App;
