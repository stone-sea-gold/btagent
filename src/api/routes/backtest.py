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


@router.post("/analyze")
async def analyze_backtest_endpoint(req: BacktestAnalyzeRequest):
    """Analyze backtest results."""
    result = analyze_backtest(req.backtest_result)
    return {"analysis": result, "status": "success"}
