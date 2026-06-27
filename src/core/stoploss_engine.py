"""StopLossEngine — evaluates stop-loss rules against daily portfolio data.

Supports three rule types:
- Fixed stop-loss: trigger if loss from cost exceeds threshold
- Trailing stop: trigger if drop from peak exceeds threshold
- Max drawdown circuit breaker: trigger if portfolio drawdown exceeds threshold
"""

from src.core.models import StopLossEvent, StopLossRule, StopLossType
from src.logging import get_logger

logger = get_logger("stoploss_engine")


class StopLossEngine:
    """Evaluates stop-loss rules for a single day."""

    def evaluate_day(
        self,
        date: str,
        portfolio_value: float,
        holdings: list[dict],
        prices: dict[str, float],
        peak_values: dict[str, float],
        cost_prices: dict[str, float],
        rules: list[StopLossRule],
        portfolio_peak_value: float = 0.0,
    ) -> list[StopLossEvent]:
        """Evaluate all rules for a single day.

        Args:
            date: Current date string.
            portfolio_value: Current total portfolio value.
            holdings: List of holding dicts with stock_code, current_price, etc.
            prices: Dict of stock_code -> current_price.
            peak_values: Dict of stock_code -> peak_price (for trailing stop).
            cost_prices: Dict of stock_code -> cost_price (for fixed stop).
            rules: List of stop-loss rules to evaluate.
            portfolio_peak_value: Peak portfolio value (for max drawdown).

        Returns:
            List of triggered StopLossEvent.
        """
        events = []

        for rule in rules:
            if rule.rule_type == StopLossType.FIXED:
                for h in holdings:
                    code = h["stock_code"]
                    cost = cost_prices.get(code, h.get("cost_price", 0))
                    current = prices.get(code, h.get("current_price", 0))
                    event = self._check_fixed_stop(code, current, cost, rule.threshold, date)
                    if event:
                        events.append(event)

            elif rule.rule_type == StopLossType.TRAILING:
                for h in holdings:
                    code = h["stock_code"]
                    current = prices.get(code, h.get("current_price", 0))
                    peak = peak_values.get(code, current)
                    event = self._check_trailing_stop(code, current, peak, rule.threshold, date)
                    if event:
                        events.append(event)

            elif rule.rule_type == StopLossType.MAX_DRAWDOWN:
                if portfolio_peak_value > 0:
                    event = self._check_max_drawdown(
                        portfolio_value, portfolio_peak_value, rule.threshold, date
                    )
                    if event:
                        events.append(event)

        if events:
            logger.info("stoploss_events", date=date, count=len(events))
        return events

    def _check_fixed_stop(
        self, stock_code: str, current_price: float,
        cost_price: float, threshold: float, date: str,
    ) -> StopLossEvent | None:
        """Fixed stop-loss: trigger if loss from cost exceeds threshold."""
        if cost_price <= 0:
            return None
        loss_pct = (cost_price - current_price) / cost_price
        if loss_pct >= threshold:
            return StopLossEvent(
                rule_type=StopLossType.FIXED,
                stock_code=stock_code,
                trigger_date=date,
                trigger_price=current_price,
                peak_price=cost_price,
                loss_pct=round(loss_pct, 4),
                action_taken=f"固定止损触发: {stock_code} 亏损 {loss_pct:.1%}",
            )
        return None

    def _check_trailing_stop(
        self, stock_code: str, current_price: float,
        peak_price: float, threshold: float, date: str,
    ) -> StopLossEvent | None:
        """Trailing stop: trigger if drop from peak exceeds threshold."""
        if peak_price <= 0:
            return None
        drop_pct = (peak_price - current_price) / peak_price
        if drop_pct >= threshold:
            return StopLossEvent(
                rule_type=StopLossType.TRAILING,
                stock_code=stock_code,
                trigger_date=date,
                trigger_price=current_price,
                peak_price=peak_price,
                loss_pct=round(drop_pct, 4),
                action_taken=f"追踪止损触发: {stock_code} 从高点回落 {drop_pct:.1%}",
            )
        return None

    def _check_max_drawdown(
        self, portfolio_value: float, peak_value: float,
        threshold: float, date: str,
    ) -> StopLossEvent | None:
        """Portfolio circuit breaker: trigger if drawdown from peak exceeds threshold."""
        if peak_value <= 0:
            return None
        drawdown = (peak_value - portfolio_value) / peak_value
        if drawdown >= threshold:
            return StopLossEvent(
                rule_type=StopLossType.MAX_DRAWDOWN,
                trigger_date=date,
                trigger_price=portfolio_value,
                peak_price=peak_value,
                loss_pct=round(drawdown, 4),
                action_taken=f"最大回撤熔断: 组合回撤 {drawdown:.1%}，建议清仓",
            )
        return None
