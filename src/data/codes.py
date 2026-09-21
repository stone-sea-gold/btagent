"""Canonical A-share security code handling.

One security is written six different ways depending on the data source, and
every one of those spellings already appears somewhere in this project:

    form              example      seen in
    ----------------  -----------  --------------------------------------------
    bare digits       600519       user input, src/tools/astock_*.py
    baostock          sh.600519    the planned primary daily source
    Sina / Tencent    sh600519     src/tools/market_data_tools.py
    Tushare           600519.SH    canonical form used by this package
    Qlib              SH600519     features/ directory names (uppercase, no dot)
    EastMoney secid   1.600519     src/tools/astock_signal.py

``600519.SH`` is the canonical form: it is unambiguous, sorts naturally by
market, and converts to every other form without loss.

Storing anything else in the local warehouse would be a mistake, because the
same stock pulled from two sources would land in two different rows. The
warehouse keys every table on the canonical form and converts at the provider
boundary.

Note on bare digits
-------------------
A bare six-digit code is ambiguous for indices: ``000001`` is Ping An Bank in
Shenzhen *and* the Shanghai Composite index. Bare input is therefore resolved
against the stock rules below, and callers that mean the index must say so by
passing ``000001.SH``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.exceptions import DataSourceError


class Market(str, Enum):
    """Exchange a security is listed on."""

    SH = "SH"
    SZ = "SZ"
    BJ = "BJ"


# Bare-code prefixes that unambiguously identify the exchange.
#
# Shanghai: 60 main board, 68 STAR market, 90 B-shares, 50/51/52/56/58 funds
#   and ETFs. 000/001 indices are deliberately absent — they collide with
#   Shenzhen main-board stocks, so they require an explicit market.
# Shenzhen: 00 main board, 30 ChiNext, 20 B-shares, 15/16/18 funds,
#   39 indices.
# Beijing: 43/83/87/88 legacy NEEQ-select codes, 920 new-issue codes.
_SH_PREFIXES = ("60", "68", "90", "50", "51", "52", "56", "58")
_SZ_PREFIXES = ("00", "30", "20", "15", "16", "18", "39")
_BJ_PREFIXES = ("43", "83", "87", "88", "92")

_DIGITS_RE = re.compile(r"^\d{6}$")
_BAOSTOCK_RE = re.compile(r"^(SH|SZ|BJ)\.(\d{6})$")
_TUSHARE_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$")
_QLIB_RE = re.compile(r"^(SH|SZ|BJ)(\d{6})$")
_SECID_RE = re.compile(r"^([01])\.(\d{6})$")


@dataclass(frozen=True, slots=True)
class Security:
    """A parsed A-share security.

    Always construct through :func:`parse`; the fields are already validated
    and normalized there.
    """

    market: Market
    digits: str
    """Six-digit code without any market decoration."""

    @property
    def symbol(self) -> str:
        """Canonical form, e.g. ``600519.SH``."""
        return f"{self.digits}.{self.market.value}"

    def to_bare(self) -> str:
        """Bare digits, e.g. ``600519``."""
        return self.digits

    def to_baostock(self) -> str:
        """BaoStock form, e.g. ``sh.600519``."""
        return f"{self.market.value.lower()}.{self.digits}"

    def to_sina(self) -> str:
        """Sina / Tencent form, e.g. ``sh600519``."""
        return f"{self.market.value.lower()}{self.digits}"

    def to_tushare(self) -> str:
        """TuShare / JoinQuant form — identical to the canonical form."""
        return self.symbol

    def to_qlib(self) -> str:
        """Qlib instrument name, e.g. ``SH600519``."""
        return f"{self.market.value}{self.digits}"

    def to_eastmoney(self) -> str:
        """EastMoney secid, e.g. ``1.600519``.

        EastMoney numbers Shanghai as 1 and everything else as 0, so Shenzhen
        and Beijing share a prefix.
        """
        return f"{1 if self.market is Market.SH else 0}.{self.digits}"

    def __str__(self) -> str:
        return self.symbol


def infer_market(digits: str) -> Market:
    """Infer the exchange from bare digits.

    Raises:
        DataSourceError: the prefix matches no known A-share range.
    """
    for prefix in _SH_PREFIXES:
        if digits.startswith(prefix):
            return Market.SH
    for prefix in _SZ_PREFIXES:
        if digits.startswith(prefix):
            return Market.SZ
    for prefix in _BJ_PREFIXES:
        if digits.startswith(prefix):
            return Market.BJ
    raise DataSourceError(
        f"cannot infer market for code {digits!r}: no known A-share prefix",
        {"code": digits},
    )


def parse(raw: str) -> Security:
    """Parse any supported spelling into a :class:`Security`.

    Accepts all six forms listed in the module docstring, case-insensitively
    and with surrounding whitespace.

    Args:
        raw: The code in any supported spelling.

    Returns:
        The parsed security.

    Raises:
        DataSourceError: the input matches no supported form, or a bare code
            has no known A-share prefix.
    """
    if not isinstance(raw, str):
        raise DataSourceError(f"code must be a string, got {type(raw).__name__}")

    text = raw.strip().upper()
    if not text:
        raise DataSourceError("code is empty")

    # baostock: sh.600519
    if match := _BAOSTOCK_RE.match(text):
        return Security(Market(match.group(1)), match.group(2))

    # TuShare / canonical: 600519.SH
    if match := _TUSHARE_RE.match(text):
        return Security(Market(match.group(2)), match.group(1))

    # Qlib / Sina / Tencent: SH600519, sh600519
    if match := _QLIB_RE.match(text):
        return Security(Market(match.group(1)), match.group(2))

    # EastMoney secid: 1.600519
    if match := _SECID_RE.match(text):
        digits = match.group(2)
        market = Market.SH if match.group(1) == "1" else infer_market(digits)
        if match.group(1) == "0" and market is Market.SH:
            # secid 0 means Shenzhen or Beijing; a Shanghai-only prefix here
            # means the caller mixed up the prefixes, which is worth surfacing.
            raise DataSourceError(
                f"ambiguous secid {raw!r}: prefix 0 does not match Shanghai code {digits}",
                {"code": raw},
            )
        return Security(market, digits)

    # bare digits: 600519
    if _DIGITS_RE.match(text):
        return Security(infer_market(text), text)

    raise DataSourceError(
        f"unrecognized code {raw!r}; expected one of 600519, sh.600519, "
        f"sh600519, 600519.SH, SH600519, 1.600519",
        {"code": raw},
    )


def normalize(raw: str) -> str:
    """Return the canonical ``600519.SH`` spelling of ``raw``."""
    return parse(raw).symbol


def to_qlib(raw: str) -> str:
    """Return the Qlib instrument name for ``raw``, e.g. ``SH600519``."""
    return parse(raw).to_qlib()
