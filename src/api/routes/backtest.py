"""Backtest API routes."""

from fastapi import APIRouter

from src.api.dependencies import get_services
from src.api.schemas import BacktestAnalyzeRequest, BacktestRequest
from src.tools.backtest_tools import analyze_backtest, run_backtest

router = APIRouter()


@router.post("/")
async def run_backtest_endpoint(req: BacktestRequest):
    """Run a backtest."""
    services = get_services()
    result = run_backtest(
        strategy_config=req.strategy_config,
        compiler=services.strategy_compiler,
        engine=services.backtest_engine,
    )
    return result


@router.get("/")
async def list_backtests():
    """List all cached backtest results."""
    services = get_services()
    results = services.backtest_engine.list_all()
    return {"results": results, "total": len(results)}


@router.get("/{backtest_id}")
async def get_backtest(backtest_id: str):
    """Get a specific backtest result by ID."""
    services = get_services()
    result = services.backtest_engine.get_by_id(backtest_id)
    if result is None:
        return {"status": "error", "error": f"Backtest '{backtest_id}' not found"}
    return {
        "backtest_id": result.id,
        "strategy_id": result.strategy_id,
        "metrics": result.metrics.model_dump(),
        "equity_curve": result.equity_curve,
        "is_cached": result.is_cached,
        "status": "success",
    }


@router.post("/analyze")
async def analyze_backtest_endpoint(req: BacktestAnalyzeRequest):
    """Analyze backtest results."""
    result = analyze_backtest(req.backtest_result)
    return {"analysis": result, "status": "success"}
