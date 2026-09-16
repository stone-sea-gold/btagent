"""Tests for adjustment derivation.

The fixtures use real measured values for 600519 around its 2020-06-24
ex-dividend date, because the whole point of this module is reproducing values
the exchange actually published. With invented numbers the test would only
confirm that the arithmetic is self-consistent, not that it is right.
"""

from datetime import date, datetime

import pytest

from src.data.derive import ChainArtifact, derive_series, enforce_monotonic_chain
from src.data.schema import AdjustFactor, Bar
from src.exceptions import DataSourceError


def _ts(day: str) -> datetime:
    """Naive timestamp — a trading day is a calendar date, not an instant."""
    return datetime.fromisoformat(day)


def bar(day, close, *, code="600519.SH", volume=1_000_000.0, suspended=False, pct_change=None):
    return Bar(
        code=code,
        ts=_ts(day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        amount=volume * close,
        is_suspended=suspended,
        pct_change=pct_change,
        source="test",
    )


def factor(day, value, *, code="600519.SH"):
    return AdjustFactor(code=code, ts=date.fromisoformat(day), factor=value, source="test")


class TestDeriveSeries:
    def test_prices_are_multiplied_by_the_factor(self):
        rows = derive_series(
            [bar("2024-01-02", 100.0)], [factor("2024-01-02", 7.0)]
        )

        assert rows[0].close == pytest.approx(700.0)
        assert rows[0].open == pytest.approx(700.0)
        assert rows[0].factor == 7.0

    def test_volume_is_not_adjusted(self):
        """Share counts are already real; only prices are restated."""
        rows = derive_series(
            [bar("2024-01-02", 100.0, volume=250.0)], [factor("2024-01-02", 7.0)]
        )

        assert rows[0].volume == 250.0

    def test_first_row_has_no_change(self):
        rows = derive_series([bar("2024-01-02", 100.0)], [factor("2024-01-02", 7.0)])

        assert rows[0].change is None

    def test_change_is_measured_on_adjusted_prices(self):
        rows = derive_series(
            [bar("2024-01-02", 100.0), bar("2024-01-03", 110.0)],
            [factor("2024-01-02", 1.0), factor("2024-01-03", 1.0)],
        )

        assert rows[1].change == pytest.approx(0.10)

    def test_ex_dividend_day_reproduces_the_published_change(self):
        """The measured case that motivates the whole module.

        600519 went ex-dividend on 2020-06-24 with a 17.02 CNY payout on a
        1474.50 previous close. The exchange published +0.1736%; the raw price
        fell 0.98%, and reading that fall as the return is the bug this
        adjustment exists to prevent.
        """
        raw = [bar("2020-06-23", 1474.50), bar("2020-06-24", 1460.01)]
        factors = [factor("2020-06-23", 6.491130), factor("2020-06-24", 6.566931)]

        rows = derive_series(raw, factors)

        assert rows[1].change == pytest.approx(0.001736, abs=5e-7)
        # What the raw series would have claimed, for contrast.
        raw_change = 1460.01 / 1474.50 - 1
        assert raw_change == pytest.approx(-0.009827, abs=5e-7)
        assert rows[1].change > 0 > raw_change

    def test_adjustment_removes_the_divergence_on_ordinary_days(self):
        """Away from corporate actions the two conventions must agree."""
        raw = [bar("2020-06-22", 1439.00), bar("2020-06-23", 1474.50)]
        factors = [factor("2020-06-22", 6.491130), factor("2020-06-23", 6.491130)]

        rows = derive_series(raw, factors)

        assert rows[1].change == pytest.approx(1474.50 / 1439.00 - 1)

    def test_rows_are_sorted_by_timestamp(self):
        rows = derive_series(
            [bar("2024-01-03", 100.0), bar("2024-01-02", 90.0)],
            [factor("2024-01-02", 1.0), factor("2024-01-03", 1.0)],
        )

        assert [r.ts.date() for r in rows] == [date(2024, 1, 2), date(2024, 1, 3)]

    def test_suspension_flag_is_carried_through(self):
        rows = derive_series(
            [bar("2024-01-02", 100.0, suspended=True, volume=0.0)],
            [factor("2024-01-02", 1.0)],
        )

        assert rows[0].is_suspended is True

    def test_missing_factor_is_refused(self):
        """Defaulting to 1.0 would leave the price unadjusted and look fine."""
        with pytest.raises(DataSourceError, match="no adjustment factor"):
            derive_series(
                [bar("2024-01-02", 100.0), bar("2024-01-03", 110.0)],
                [factor("2024-01-02", 1.0)],
            )

    def test_empty_input(self):
        assert derive_series([], []) == []

    def test_trading_date_helper(self):
        rows = derive_series([bar("2024-01-02", 100.0)], [factor("2024-01-02", 1.0)])

        assert rows[0].trading_date == date(2024, 1, 2)


class TestEnforceMonotonicChain:
    def test_leaves_a_healthy_chain_alone(self):
        actions = [(date(2020, 5, 28), 1.0), (date(2021, 5, 14), 1.02)]

        corrected, artifacts = enforce_monotonic_chain(actions)

        assert corrected == actions
        assert artifacts == []

    def test_repairs_the_real_baostock_artifact(self):
        """000001.SZ really does report these three values."""
        actions = [
            (date(2020, 5, 28), 119.960317),
            (date(2020, 12, 31), 99.787353),
            (date(2021, 5, 14), 100.572054),
        ]

        corrected, artifacts = enforce_monotonic_chain(actions)

        assert [round(value, 6) for _, value in corrected] == [
            119.960317,
            119.960317,
            120.903653,
        ]
        assert len(artifacts) == 1
        assert artifacts[0].day == date(2020, 12, 31)
        assert artifacts[0].step == pytest.approx(-0.16816, abs=1e-5)

    def test_repaired_chain_is_non_decreasing(self):
        actions = [
            (date(2020, 5, 28), 100.0),
            (date(2020, 12, 31), 90.0),
            (date(2021, 5, 14), 91.0),
            (date(2022, 5, 14), 92.0),
        ]

        corrected, artifacts = enforce_monotonic_chain(actions)

        values = [value for _, value in corrected]
        assert values == sorted(values)
        assert len(artifacts) == 1

    def test_later_steps_keep_their_true_size(self):
        """Rescaling must preserve the ratio of a subsequent real action."""
        actions = [
            (date(2020, 5, 28), 100.0),
            (date(2020, 12, 31), 50.0),
            (date(2021, 5, 14), 51.0),
        ]

        corrected, _ = enforce_monotonic_chain(actions)

        first_step = corrected[2][1] / corrected[1][1]
        assert first_step == pytest.approx(51.0 / 50.0)

    def test_multiple_artifacts_compound(self):
        actions = [
            (date(2020, 1, 1), 100.0),
            (date(2020, 6, 1), 80.0),
            (date(2021, 1, 1), 60.0),
        ]

        corrected, artifacts = enforce_monotonic_chain(actions)

        assert [value for _, value in corrected] == [100.0, 100.0, 100.0]
        assert len(artifacts) == 2

    def test_a_flat_chain_is_not_an_artifact(self):
        """An unchanged value is not a decrease."""
        actions = [(date(2020, 1, 1), 5.0), (date(2020, 6, 1), 5.0)]

        corrected, artifacts = enforce_monotonic_chain(actions)

        assert corrected == actions
        assert artifacts == []

    def test_empty_chain(self):
        assert enforce_monotonic_chain([]) == ([], [])

    def test_artifact_step_is_always_negative(self):
        artifact = ChainArtifact(day=date(2020, 12, 31), recorded=90.0, corrected=100.0)

        assert artifact.step == pytest.approx(-0.10)
