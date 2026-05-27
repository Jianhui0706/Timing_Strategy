from __future__ import annotations

import shutil
from pathlib import Path
from threading import Thread
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from timing_strategy.agents import WorkflowRunner
from timing_strategy.config import load_app_config
from timing_strategy.data.loader import DataValidationError
from timing_strategy.storage import TraceRepository


class RunRequest(BaseModel):
    name: str = "择时策略运行"
    data_path: str | None = None


config = load_app_config()
repository = TraceRepository(config.get("paths", {}).get("storage_db", "storage/timing_strategy.sqlite3"))
active_run_ids: set[str] = set()

app = FastAPI(title="择时策略系统 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def backend_home() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>择时策略系统后端</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f5ef;
      --panel: #ffffff;
      --text: #263331;
      --muted: #68736f;
      --line: #dedbd1;
      --accent: #3d8588;
      --danger: #ba5747;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
    }
    main {
      width: min(1120px, calc(100vw - 40px));
      margin: 32px auto;
    }
    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 22px;
    }
    h1 { margin: 0 0 8px; font-size: 32px; }
    p { margin: 0; color: var(--muted); line-height: 1.65; }
    a { color: var(--accent); font-weight: 650; text-decoration: none; }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 1px 4px rgba(38, 51, 49, 0.06);
    }
    .panel h2 { margin: 0 0 14px; font-size: 18px; }
    .links {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    button, .link-button {
      border: 1px solid var(--line);
      background: #fdfcf8;
      color: var(--text);
      border-radius: 7px;
      padding: 10px 13px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }
    button.primary, .link-button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: white;
    }
    button.danger {
      border-color: var(--danger);
      color: var(--danger);
    }
    label {
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-weight: 650;
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 11px 12px;
      margin-bottom: 10px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }
    code {
      background: #efede5;
      border-radius: 5px;
      padding: 2px 5px;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: #242a28;
      color: #eef3ee;
      border-radius: 8px;
      padding: 14px;
      min-height: 160px;
      max-height: 460px;
      overflow: auto;
      font-size: 13px;
      line-height: 1.55;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 6px;
      text-align: left;
      vertical-align: top;
    }
    th { color: var(--muted); }
    .stack { display: flex; flex-direction: column; gap: 10px; }
    .full { grid-column: 1 / -1; }
    @media (max-width: 860px) {
      header { display: block; }
      .grid { grid-template-columns: 1fr; }
      main { width: min(100vw - 24px, 1120px); margin: 20px auto; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>择时策略系统后端</h1>
        <p>这里是 FastAPI 后端调试页，用来检查接口、查看运行记录、启动一次真实流程。客户演示界面仍然在 React 前端。</p>
      </div>
      <div class="links">
        <a class="link-button primary" href="/docs">接口文档 /docs</a>
        <a class="link-button" href="/redoc">接口文档 /redoc</a>
        <a class="link-button" href="http://127.0.0.1:5173/">打开前端</a>
      </div>
    </header>

    <section class="grid">
      <div class="panel">
        <h2>服务检查</h2>
        <div class="stack">
          <button onclick="callApi('/api/health')">检查后端状态</button>
          <button onclick="callApi('/api/config')">查看当前配置</button>
          <button onclick="refreshRuns()">刷新运行列表</button>
        </div>
      </div>

      <div class="panel">
        <h2>启动运行</h2>
        <label for="runName">运行名称</label>
        <input id="runName" value="513860 ETF FastAPI 测试运行" />
        <label for="dataPath">行情数据路径</label>
        <input id="dataPath" value="data/raw/513860_etf.parquet" />
        <button class="primary" onclick="createRun()">启动真实运行</button>
      </div>

      <div class="panel">
        <h2>清理操作</h2>
        <p>清空只删除运行记录和 <code>output/reports</code> 报告，不删除 <code>data/raw</code> 原始数据。</p>
        <div style="height: 12px"></div>
        <button class="danger" onclick="clearRuns()">清空运行记录与报告</button>
      </div>

      <div class="panel full">
        <h2>运行列表</h2>
        <div id="runsTable">正在读取运行列表...</div>
      </div>

      <div class="panel full">
        <h2>接口返回</h2>
        <pre id="output">等待操作...</pre>
      </div>
    </section>
  </main>

  <script>
    const output = document.getElementById("output");
    const runsTable = document.getElementById("runsTable");

    function show(value) {
      output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    async function request(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options
      });
      const text = await response.text();
      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = text;
      }
      if (!response.ok) {
        throw new Error(JSON.stringify(data, null, 2));
      }
      return data;
    }

    async function callApi(path) {
      try {
        show(await request(path));
      } catch (error) {
        show("请求失败：\\n" + error.message);
      }
    }

    async function createRun() {
      try {
        const payload = {
          name: document.getElementById("runName").value,
          data_path: document.getElementById("dataPath").value
        };
        const data = await request("/api/runs", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        show(data);
        await refreshRuns();
      } catch (error) {
        show("启动失败：\\n" + error.message);
      }
    }

    async function clearRuns() {
      if (!confirm("确定清空所有运行记录和 output/reports 报告吗？原始行情数据不会删除。")) {
        return;
      }
      try {
        const data = await request("/api/runs", { method: "DELETE" });
        show(data);
        await refreshRuns();
      } catch (error) {
        show("清空失败：\\n" + error.message);
      }
    }

    async function deleteRun(runId) {
      if (!confirm("确定删除这次运行记录和对应报告吗？")) {
        return;
      }
      try {
        const data = await request(`/api/runs/${runId}`, { method: "DELETE" });
        show(data);
        await refreshRuns();
      } catch (error) {
        show("删除失败：\\n" + error.message);
      }
    }

    async function readRun(runId) {
      try {
        show(await request(`/api/runs/${runId}`));
      } catch (error) {
        show("读取失败：\\n" + error.message);
      }
    }

    async function refreshRuns() {
      try {
        const runs = await request("/api/runs");
        if (!runs.length) {
          runsTable.innerHTML = "<p>暂无运行记录。</p>";
          return;
        }
        runsTable.innerHTML = `
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>模型</th>
                <th>因子数</th>
                <th>最佳分数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              ${runs.map(run => {
                const id = run.id || run.run_id;
                return `
                <tr>
                  <td>${run.name || id}</td>
                  <td>${run.status || "-"}</td>
                  <td>${run.model || "-"}</td>
                  <td>${run.factor_count ?? "-"}</td>
                  <td>${run.best_score ?? "-"}</td>
                  <td>
                    <button onclick="readRun('${id}')">查看 JSON</button>
                    <button class="danger" onclick="deleteRun('${id}')" ${run.is_active ? "disabled" : ""}>删除</button>
                  </td>
                </tr>
              `}).join("")}
            </tbody>
          </table>
        `;
      } catch (error) {
        runsTable.innerHTML = "<p>读取失败，请确认后端服务正常。</p>";
        show("读取运行列表失败：\\n" + error.message);
      }
    }

    refreshRuns();
  </script>
</body>
</html>
    """


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def read_config() -> dict[str, Any]:
    return {
        "project": config.get("project", {}),
        "llm": {
            "provider": config.get("llm", {}).get("provider", "openai"),
            "model": config.get("llm", {}).get("model", "gpt-5.5"),
        },
    }


@app.get("/api/data-files")
def list_data_files() -> list[dict[str, Any]]:
    raw_dir = Path(config.get("paths", {}).get("raw_data_dir", "data/raw"))
    if not raw_dir.exists():
        return []
    supported_suffixes = {".csv", ".parquet", ".pq"}
    files = []
    for path in raw_dir.rglob("*"):
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in supported_suffixes:
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "path": path.as_posix(),
                "relative_path": path.relative_to(raw_dir).as_posix(),
                "suffix": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return sorted(files, key=lambda item: (item["relative_path"].lower(), item["modified_at"]))


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    return [_with_runtime_state(run) for run in repository.list_runs()]


@app.post("/api/runs")
def create_run(request: RunRequest) -> dict[str, str]:
    runner = WorkflowRunner(config=config, repository=repository, logger=lambda message: print(message, flush=True))
    try:
        market_data = runner.load_market_data(request.data_path)
        run_id = repository.create_run(name=request.name, model=runner.llm_client.model, config=config)
    except DataValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    active_run_ids.add(run_id)
    thread = Thread(
        target=_run_in_background,
        args=(run_id, request.name, request.data_path, market_data),
        daemon=True,
    )
    thread.start()
    return {"run_id": run_id, "status": "running"}


def _run_in_background(run_id: str, run_name: str, data_path: str | None, market_data) -> None:
    runner = WorkflowRunner(config=config, repository=repository, logger=lambda message: print(message, flush=True))
    try:
        runner.run(data_path=data_path, run_name=run_name, run_id=run_id, market_data=market_data)
    except Exception as exc:
        repository.finish_run(run_id, "failed", {"error": str(exc)})
        print(f"后台运行失败：{run_id}：{exc}", flush=True)
    finally:
        active_run_ids.discard(run_id)


@app.get("/api/runs/{run_id}")
def read_run(run_id: str) -> dict[str, Any]:
    detail = repository.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="找不到运行记录")
    return _with_runtime_state(detail)


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str) -> dict[str, str]:
    detail = repository.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="找不到运行记录")
    if run_id in active_run_ids:
        raise HTTPException(status_code=409, detail="这次运行仍在当前后端进程中执行，不能删除。")
    _delete_report_files(detail.get("summary", {}))
    deleted = repository.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到运行记录")
    return {"status": "deleted", "run_id": run_id}


@app.delete("/api/runs")
def clear_runs() -> dict[str, str]:
    if active_run_ids:
        raise HTTPException(status_code=409, detail="存在当前后端进程正在执行的任务，不能清空运行记录。")
    repository.clear_runs()
    reports_dir = Path(config.get("paths", {}).get("reports_dir", "output/reports"))
    if reports_dir.exists():
        shutil.rmtree(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    return {"status": "cleared"}


@app.get("/api/factor-pool")
def list_factor_pool(limit: int = 50) -> list[dict[str, Any]]:
    return repository.list_factor_pool(limit=limit)


def _with_runtime_state(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("id") or payload.get("run_id") or "")
    return {
        **payload,
        "is_active": run_id in active_run_ids,
        "runtime_note": "当前后端进程正在执行" if run_id in active_run_ids else "",
    }


def _delete_report_files(summary: dict[str, Any]) -> None:
    paths = summary.get("report_paths")
    if not isinstance(paths, dict):
        return
    for path_text in paths.values():
        if not isinstance(path_text, str):
            continue
        path = Path(path_text)
        if path.exists() and path.is_file():
            path.unlink()
