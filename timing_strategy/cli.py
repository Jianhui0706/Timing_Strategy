from __future__ import annotations

import argparse
import json
import sys

from timing_strategy.agents import WorkflowRunner
from timing_strategy.config import load_app_config
from timing_strategy.data.loader import DataValidationError
from timing_strategy.storage import TraceRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="择时策略系统 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="运行一次择时挖掘流程")
    run_parser.add_argument("--data", help="本地行情 CSV 或 Parquet 路径")
    run_parser.add_argument("--name", default="择时策略运行", help="运行名称")

    subparsers.add_parser("list-runs", help="查看历史运行")

    args = parser.parse_args()
    config = load_app_config()
    repository = TraceRepository(config.get("paths", {}).get("storage_db", "output/storage/timing_strategy.sqlite3"))

    if args.command == "run":
        runner = WorkflowRunner(config=config, repository=repository, logger=lambda message: print(message, flush=True))
        try:
            run_id = runner.run(data_path=args.data, run_name=args.name)
            print(f"运行完成：{run_id}")
        except (DataValidationError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif args.command == "list-runs":
        print(json.dumps(repository.list_runs(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
