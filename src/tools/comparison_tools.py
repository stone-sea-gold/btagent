"""Strategy comparison and update tools for the Agent."""

from src.exceptions import StrategyNotFoundError
from src.logging import get_logger
from src.tools.storage_tools import StrategyStore

logger = get_logger("comparison_tools")

MAX_COMPARE_LIMIT = 10
MAX_VERSION_CHAIN_DEPTH = 50


def compare_strategies(strategy_ids: list[str], store: StrategyStore) -> dict:
    """Compare multiple strategies side-by-side.

    Returns metrics comparison and factor differences.
    """
    if len(strategy_ids) > MAX_COMPARE_LIMIT:
        return {"error": f"最多比较 {MAX_COMPARE_LIMIT} 个策略", "status": "error"}

    strategies = []
    for sid in strategy_ids:
        try:
            s = store.load(sid)
            strategies.append(s)
        except StrategyNotFoundError:
            return {"error": f"策略 '{sid}' 不存在", "status": "error"}

    if not strategies:
        return {"error": "未找到任何策略", "status": "error"}

    # Build comparison table
    comparison = []
    all_factor_ids = set()
    for s in strategies:
        config = s.get("config", {})
        entry = {
            "strategy_id": s["strategy_id"],
            "name": s.get("name", ""),
            "version": s.get("version", 1),
            "factors": config.get("factor_ids", []),
            "max_holding": config.get("max_holding", 10),
            "rebalance_freq": config.get("rebalance_freq", ""),
            "weight_scheme": config.get("weight_scheme", ""),
        }
        comparison.append(entry)
        all_factor_ids.update(config.get("factor_ids", []))

    # Factor diff
    factor_sets = {s["strategy_id"]: set(s["config"].get("factor_ids", [])) for s in strategies}
    factor_diff = {}
    for sid, factors in factor_sets.items():
        unique = factors - set().union(*[v for k, v in factor_sets.items() if k != sid])
        if unique:
            factor_diff[sid] = list(unique)

    logger.info("compare_strategies", count=len(strategies))
    return {
        "strategies": comparison,
        "factor_diff": factor_diff,
        "all_factors": list(all_factor_ids),
        "status": "success",
    }


def update_strategy(
    strategy_id: str,
    modifications: dict,
    store: StrategyStore,
    agent_summary: str = "",
) -> dict:
    """Update a strategy by creating a new version.

    Args:
        strategy_id: ID of the strategy to update.
        modifications: Dict of config fields to modify.
        store: StrategyStore instance.
        agent_summary: New agent summary (optional).

    Returns:
        New version strategy info.
    """
    try:
        original = store.load(strategy_id)
    except StrategyNotFoundError:
        return {"error": f"策略 '{strategy_id}' 不存在", "status": "error"}

    # Check version chain depth
    chain = store.get_version_chain(strategy_id)
    if len(chain) >= MAX_VERSION_CHAIN_DEPTH:
        return {
            "error": f"版本链深度已达上限 ({MAX_VERSION_CHAIN_DEPTH})",
            "status": "error",
        }

    # Apply modifications to config
    config = original["config"].copy()
    config.update(modifications)

    # Create new version
    new_version = original.get("version", 1) + 1
    new_summary = agent_summary or original.get("agent_summary", "")

    result = store.save(
        name=original["name"],
        config=config,
        description=original.get("description", ""),
        agent_summary=new_summary,
        version=new_version,
        parent_id=strategy_id,
    )

    logger.info(
        "strategy_updated",
        original_id=strategy_id,
        new_id=result["strategy_id"],
        version=new_version,
        modifications=list(modifications.keys()),
    )
    return {
        "strategy_id": result["strategy_id"],
        "name": original["name"],
        "version": new_version,
        "parent_id": strategy_id,
        "modifications": modifications,
        "status": "updated",
    }
