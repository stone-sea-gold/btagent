"""Tests for canonical security code handling.

The point of these tests is the round trip: a code must survive every
supported spelling without drifting, and the market inference must agree with
the ranges the exchanges actually use.
"""

import pytest

from src.data.codes import (
    Market,
    Security,
    infer_market,
    normalize,
    parse,
    to_qlib,
)
from src.exceptions import DataSourceError


class TestParseForms:
    """Every supported spelling parses to the same security."""

    @pytest.mark.parametrize(
        "spelling",
        [
            "600519",        # bare digits
            "sh.600519",     # BaoStock
            "SH.600519",     # BaoStock, upper case
            "sh600519",      # Sina / Tencent
            "SH600519",      # Qlib
            "600519.SH",     # TuShare / canonical
            "600519.sh",     # TuShare, lower case
            "1.600519",      # EastMoney secid
        ],
    )
    def test_all_spellings_agree(self, spelling):
        security = parse(spelling)
        assert security.market is Market.SH
        assert security.digits == "600519"
        assert security.symbol == "600519.SH"

    def test_surrounding_whitespace_is_ignored(self):
        assert parse("  600519.SH  ").symbol == "600519.SH"


class TestConversions:
    """Each target spelling matches what the corresponding source expects."""

    def setup_method(self):
        self.sh = parse("600519.SH")
        self.sz = parse("000001.SZ")

    def test_shanghai(self):
        assert self.sh.to_bare() == "600519"
        assert self.sh.to_baostock() == "sh.600519"
        assert self.sh.to_sina() == "sh600519"
        assert self.sh.to_tushare() == "600519.SH"
        assert self.sh.to_qlib() == "SH600519"
        assert self.sh.to_eastmoney() == "1.600519"

    def test_shenzhen(self):
        assert self.sz.to_baostock() == "sz.000001"
        assert self.sz.to_sina() == "sz000001"
        assert self.sz.to_qlib() == "SZ000001"
        assert self.sz.to_eastmoney() == "0.000001"

    def test_round_trip_through_every_form(self):
        original = parse("300750.SZ")
        for rendered in (
            original.to_bare(),
            original.to_baostock(),
            original.to_sina(),
            original.to_tushare(),
            original.to_qlib(),
            original.to_eastmoney(),
        ):
            assert parse(rendered) == original

    def test_str_is_canonical(self):
        assert str(parse("sh.600519")) == "600519.SH"


class TestMarketInference:
    """Bare codes resolve to the exchange that actually uses that range."""

    @pytest.mark.parametrize(
        "digits,market",
        [
            ("600519", Market.SH),   # main board
            ("601318", Market.SH),
            ("603288", Market.SH),
            ("605499", Market.SH),
            ("688981", Market.SH),   # STAR market
            ("900901", Market.SH),   # B-share
            ("510300", Market.SH),   # ETF
            ("588000", Market.SH),   # STAR ETF
            ("000001", Market.SZ),   # main board
            ("002594", Market.SZ),
            ("300750", Market.SZ),   # ChiNext
            ("301029", Market.SZ),
            ("200011", Market.SZ),   # B-share
            ("159915", Market.SZ),   # ETF
            ("399001", Market.SZ),   # index
            ("430047", Market.BJ),   # NEEQ-select legacy
            ("830799", Market.BJ),
            ("871981", Market.BJ),
            ("920819", Market.BJ),   # new-issue range
        ],
    )
    def test_prefix_ranges(self, digits, market):
        assert infer_market(digits) is market
        assert parse(digits).market is market

    def test_ambiguous_bare_index_resolves_to_stock(self):
        """000001 is Ping An Bank when written bare.

        The Shanghai Composite uses the same digits, so callers meaning the
        index must spell out the market. This is a documented limitation
        rather than an accident.
        """
        assert parse("000001").market is Market.SZ
        assert parse("000001.SH").market is Market.SH

    def test_unknown_prefix_is_rejected(self):
        with pytest.raises(DataSourceError, match="cannot infer market"):
            infer_market("123456")


class TestRejections:
    """Malformed input fails loudly instead of guessing."""

    @pytest.mark.parametrize(
        "bad",
        ["", "   ", "abc", "60051", "6005199", "SH.60051", "600519.XX", "0.600519"],
    )
    def test_rejected(self, bad):
        with pytest.raises(DataSourceError):
            parse(bad)

    def test_non_string_rejected(self):
        with pytest.raises(DataSourceError, match="must be a string"):
            parse(600519)  # type: ignore[arg-type]

    def test_secid_prefix_mismatch_is_named(self):
        """secid 0 claims Shenzhen/Beijing but the code range is Shanghai-only."""
        with pytest.raises(DataSourceError, match="ambiguous secid"):
            parse("0.600519")


class TestHelpers:
    def test_normalize(self):
        assert normalize("sh600519") == "600519.SH"
        assert normalize("000001") == "000001.SZ"

    def test_to_qlib(self):
        assert to_qlib("600519") == "SH600519"
        assert to_qlib("sz.000001") == "SZ000001"

    def test_security_is_hashable(self):
        assert len({parse("600519"), parse("sh.600519"), parse("SH600519")}) == 1

    def test_security_str_and_repr(self):
        security = Security(Market.BJ, "430047")
        assert str(security) == "430047.BJ"
