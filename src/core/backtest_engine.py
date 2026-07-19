"""BacktestEngine — wraps Qlib's backtest API with caching and result parsing.

Features:
- Runs backtests via Qlib's backtest framework
- Parses results into BacktestMetrics + equity curve
- Idempotency: same (strategy_hash, date_range) returns cached result
- Structured logging of every backtest run
"""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.config import settings
from src.core.models import (
    BacktestMetrics,
    BacktestResult,
    StrategyConfig,
)
from src.exceptions import BacktestError
from src.logging import get_logger

logger = get_logger("backtest_engine")


class BacktestEngine:
    """Qlib backtest wrapper with caching and result parsing."""

    def __init__(self, cache_dir: str | None = None):
        self._cache_dir = cache_dir or str(Path(settings.project_root) / "data" / "backtest_cache")
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)

        # SQLite cache for backtest results (check_same_thread=False for LangGraph)
        self._db_path = str(Path(self._cache_dir) / "backtest_cache.db")
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_cache_db()

    def _init_cache_db(self) -> None:
        """Create cache table if not exists."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                cache_key TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def run(
        self,
        strategy_id: str,
        compiled_strategy: dict,
        start_date: str,
        end_date: str,
        benchmark: str = "SH000300",
    ) -> BacktestResult:
        """Run a backtest or return cached result.

        Args:
            strategy_id: Unique strategy identifier.
            compiled_strategy: Output from StrategyCompiler.compile().
            start_date: Backtest start (YYYY-MM-DD).
            end_date: Backtest end (YYYY-MM-DD).
            benchmark: Benchmark index code.

        Returns:
            BacktestResult with metrics and equity curve.
        """
        # Check cache (idempotency)
        cache_key = self._compute_cache_key(strategy_id, compiled_strategy, start_date, end_date)
        cached = self._get_cached(cache_key)
        if cached:
            logger.info("backtest_cache_hit", strategy_id=strategy_id, cache_key=cache_key)
            cached.is_cached = True
            return cached

        # Run backtest
        logger.info(
            "backtest_start",
            strategy_id=strategy_id,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            result = self._execute_backtest(strategy_id, compiled_strategy, start_date, end_date, benchmark)
        except BacktestError:
            raise  # Already a BacktestError — don't double-wrap
        except Exception as e:
            logger.error("backtest_failed", strategy_id=strategy_id, error=str(e))
            raise BacktestError(
                f"回测执行异常: {e}",
                details={"strategy_id": strategy_id, "error": str(e), "error_type": type(e).__name__},
            ) from e

        # Cache result
        self._cache_result(cache_key, strategy_id, result)

        logger.info(
            "backtest_complete",
            strategy_id=strategy_id,
            sharpe_ratio=result.metrics.sharpe_ratio,
            total_return=result.metrics.total_return,
            max_drawdown=result.metrics.max_drawdown,
        )
        return result

    def _execute_backtest(
        self, strategy_id, compiled_strategy, start_date, end_date, benchmark
    ) -> BacktestResult:
        """Execute the actual backtest using Qlib."""
        # ── Step 1: Import Qlib ──────────────────────────────────────
        try:
            import qlib
            from qlib.contrib.evaluate import backtest_daily, risk_analysis
            from qlib.contrib.model.linear import LinearModel
            from qlib.data.dataset import DatasetH
        except ImportError as e:
            module = str(e).split("'")[-2] if "'" in str(e) else str(e)
            logger.error("qlib_import_failed", error=str(e))
            raise BacktestError(
                f"Qlib 模块导入失败（{module}）。请确认已安装 qlib：pip install pyqlib",
                details={"error": str(e), "error_type": "import_error", "module": module},
            ) from e

        # ── Step 2: Initialize Qlib ──────────────────────────────────
        try:
            qlib.init(provider_uri=settings.qlib_data_path, region="cn")
        except Exception:
            pass  # Already initialized

        # ── Step 3: Validate data availability ───────────────────────
        try:
            from qlib.data import D
            cal = D.calendar(start_time="2000-01-01", end_time="2030-12-31")
            if len(cal) == 0:
                raise BacktestError(
                    "Qlib 日历数据为空。请运行 `python cli.py --init-data --force` 重新下载数据。",
                    details={"error_type": "data_empty"},
                )
            data_end = str(cal[-1])[:10]
            data_start = str(cal[0])[:10]
            if end_date > data_end:
                raise BacktestError(
                    f"回测结束日期 {end_date} 超出数据范围。"
                    f"当前数据覆盖 {data_start} ~ {data_end}。"
                    f"请将结束日期改为 {data_end} 或更早，或运行 `python cli.py --init-data --force` 更新数据。",
                    details={
                        "error_type": "date_out_of_range",
                        "data_start": data_start,
                        "data_end": data_end,
                        "requested_end": end_date,
                    },
                )
            if start_date > data_end:
                raise BacktestError(
                    f"回测开始日期 {start_date} 晚于数据最新日期 {data_end}。"
                    f"请将开始日期改为 {data_end} 或更早。",
                    details={
                        "error_type": "date_out_of_range",
                        "data_start": data_start,
                        "data_end": data_end,
                        "requested_start": start_date,
                    },
                )
        except BacktestError:
            raise
        except Exception as e:
            logger.warning("data_coverage_check_failed", error=str(e))

        # ── Step 4: Build dataset and run backtest ───────────────────
        try:
            strategy_config = compiled_strategy.get("qlib_strategy", {})
            topk = strategy_config.get("kwargs", {}).get("topk", 10)

            ds_conf = {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": start_date,
                        "end_time": end_date,
                        "fit_start_time": start_date,
                        "fit_end_time": end_date,
                        "instruments": "csi300",
                        "infer_processors": [
                            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
                            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
                        ],
                        "learn_processors": [
                            {"class": "DropnaLabel"},
                            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
                        ],
                    },
                },
                "segments": {
                    "train": (start_date, end_date),
                    "valid": (start_date, end_date),
                    "test": (start_date, end_date),
                },
            }

            dataset = DatasetH(**ds_conf)
            model = LinearModel()
            model.fit(dataset)

            bt_strategy = {
                "class": "TopkDropoutStrategy",
                "module_path": "qlib.contrib.strategy.signal_strategy",
                "kwargs": {
                    "signal": (model, dataset),
                    "topk": topk,
                    "n_drop": topk,
                },
            }

            report_normal, positions_normal = backtest_daily(
                start_time=start_date,
                end_time=end_date,
                strategy=bt_strategy,
                benchmark=benchmark,
            )

            risk_report = risk_analysis(report_normal)
            metrics = self._parse_metrics(report_normal, risk_report)
            equity_curve = self._parse_equity_curve(report_normal)

            return BacktestResult(
                id=f"bt_{strategy_id}_{start_date}_{end_date}",
                strategy_id=strategy_id,
                metrics=metrics,
                equity_curve=equity_curve,
                is_cached=False,
            )

        except BacktestError:
            raise
        except ZeroDivisionError as e:
            logger.error("backtest_data_error", error=str(e))
            raise BacktestError(
                f"回测数据为空或无效（{start_date} ~ {end_date}）。"
                f"请检查日期范围内是否有交易数据，或运行 `python cli.py --init-data --force` 重新下载数据。",
                details={"error_type": "data_error", "error": str(e)},
            ) from e
        except Exception as e:
            logger.error("backtest_runtime_error", error=str(e), error_type=type(e).__name__)
            raise BacktestError(
                f"回测运行失败（{type(e).__name__}）: {e}",
                details={"error_type": "runtime_error", "error": str(e), "exception_type": type(e).__name__},
            ) from e

    def _parse_metrics(self, report_normal, risk_report=None) -> BacktestMetrics:
        """Parse Qlib backtest report into BacktestMetrics.

        Args:
            report_normal: Dict from backtest_daily — keys like '1day',
                           values are DataFrames with 'return' column.
            risk_report: DataFrame from risk_analysis (optional).
        """
        try:
            import pandas as pd
            import numpy as np

            # Extract the daily returns DataFrame
            # report_normal is a dict like {'1day': DataFrame} or directly a DataFrame
            if isinstance(report_normal, dict):
                # Use first available frequency
                df = next(iter(report_normal.values()))
            else:
                df = report_normal

            # Get returns column
            if hasattr(df, 'columns'):
                if 'return' in df.columns:
                    returns = df['return'].dropna()
                elif 'excess_return_without_cost' in df.columns:
                    returns = df['excess_return_without_cost'].dropna()
                else:
                    returns = df.iloc[:, 0].dropna()
            else:
                returns = pd.Series(df).dropna()

            if len(returns) == 0:
                raise ValueError("Empty returns series")

            # Compute metrics from returns
            total_return = float((1 + returns).prod() - 1)
            n_days = len(returns)
            annualized_return = float((1 + total_return) ** (252 / max(n_days, 1)) - 1)
            volatility = float(returns.std() * (252 ** 0.5))
            sharpe = float(annualized_return / volatility) if volatility > 0 else 0.0

            # Max drawdown
            cumulative = (1 + returns).cumprod()
            rolling_max = cumulative.expanding().max()
            drawdown = (cumulative - rolling_max) / rolling_max
            max_drawdown = float(drawdown.min())
            max_dd_duration = 0

            win_rate = float((returns > 0).sum() / len(returns))

            return BacktestMetrics(
                total_return=round(total_return, 4),
                annualized_return=round(annualized_return, 4),
                sharpe_ratio=round(sharpe, 4),
                max_drawdown=round(max_drawdown, 4),
                max_drawdown_duration=max_dd_duration,
                volatility=round(volatility, 4),
                win_rate=round(win_rate, 4),
                turnover=0.0,
            )
        except Exception as e:
            logger.warning("metrics_parse_error", error=str(e))

        # Fallback
        return BacktestMetrics(
            total_return=0.0, annualized_return=0.0, sharpe_ratio=0.0,
            max_drawdown=0.0, max_drawdown_duration=0, volatility=0.0,
            win_rate=0.0, turnover=0.0,
        )

    def _parse_equity_curve(self, report_normal) -> list[dict]:
        """Parse Qlib report into equity curve data points."""
        try:
            import pandas as pd

            # Extract the daily returns DataFrame
            if isinstance(report_normal, dict):
                df = next(iter(report_normal.values()))
            else:
                df = report_normal

            if hasattr(df, 'columns'):
                if 'return' in df.columns:
                    returns = df['return'].dropna()
                elif 'excess_return_without_cost' in df.columns:
                    returns = df['excess_return_without_cost'].dropna()
                else:
                    returns = df.iloc[:, 0].dropna()
            else:
                returns = pd.Series(df).dropna()

            cumulative = (1 + returns).cumprod()
            curve = []
            for date, value in cumulative.items():
                curve.append({
                    "date": str(date)[:10],
                    "value": round(float(value), 4),
                })
            return curve
        except Exception as e:
            logger.warning("equity_curve_parse_error", error=str(e))
        return []

    def _compute_cache_key(self, strategy_id, compiled_strategy, start_date, end_date) -> str:
        """Compute a deterministic cache key."""
        key_data = {
            "strategy_id": strategy_id,
            "alpha_expression": compiled_strategy.get("alpha_expression", ""),
            "selection": compiled_strategy.get("selection_expression", {}),
            "start_date": start_date,
            "end_date": end_date,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def _get_cached(self, cache_key: str) -> BacktestResult | None:
        """Retrieve cached result if exists."""
        row = self._conn.execute(
            "SELECT result_json FROM backtest_results WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row:
            data = json.loads(row["result_json"])
            return BacktestResult(**data)
        return None

    def _cache_result(self, cache_key: str, strategy_id: str, result: BacktestResult) -> None:
        """Cache a backtest result."""
        self._conn.execute(
            "INSERT OR REPLACE INTO backtest_results (cache_key, strategy_id, result_json, created_at) VALUES (?, ?, ?, ?)",
            (cache_key, strategy_id, result.model_dump_json(), datetime.now().isoformat()),
        )
        self._conn.commit()

    def list_all(self, limit: int = 50) -> list[dict]:
        """List all cached backtest results (summary, no equity curve)."""
        rows = self._conn.execute(
            "SELECT result_json, created_at FROM backtest_results ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        results = []
        for row in rows:
            data = json.loads(row["result_json"])
            results.append({
                "backtest_id": data.get("id", ""),
                "strategy_id": data.get("strategy_id", ""),
                "metrics": data.get("metrics", {}),
                "created_at": row["created_at"],
            })
        return results

    def get_by_id(self, backtest_id: str) -> BacktestResult | None:
        """Retrieve a specific backtest result by its ID."""
        rows = self._conn.execute(
            "SELECT result_json FROM backtest_results",
        ).fetchall()
        for row in rows:
            data = json.loads(row["result_json"])
            if data.get("id") == backtest_id:
                return BacktestResult(**data)
        return None

    def close(self) -> None:
        """Close database connections."""
        self._conn.close()
