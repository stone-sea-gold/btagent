"""PositionManager — user holdings and position rule management.

Stores user portfolio holdings and position management rules in SQLite.
Supports violation checking against configured rules.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.config import settings
from src.core.models import HoldingRecord, PositionRule, PositionViolation, RuleType
from src.exceptions import PositionError
from src.logging import get_logger

logger = get_logger("position_manager")


class PositionManager:
    """SQLite-based position management."""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or settings.sqlite_db_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                quantity INTEGER NOT NULL,
                cost_price REAL NOT NULL,
                current_price REAL NOT NULL,
                market_value REAL NOT NULL,
                pnl REAL DEFAULT 0.0,
                pnl_pct REAL DEFAULT 0.0,
                industry TEXT DEFAULT '',
                weight REAL DEFAULT 0.0,
                updated_at TEXT NOT NULL,
                UNIQUE(session_id, stock_code)
            );

            CREATE TABLE IF NOT EXISTS position_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                max_weight REAL NOT NULL,
                scope TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(session_id, rule_type, scope)
            );
        """)
        # Migration for existing databases
        self._migrate_add_column("holdings", "pnl", "REAL DEFAULT 0.0")
        self._migrate_add_column("holdings", "pnl_pct", "REAL DEFAULT 0.0")
        self._conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_holdings_session ON holdings(session_id);
            CREATE INDEX IF NOT EXISTS idx_position_rules_session ON position_rules(session_id);
        """)
        self._conn.commit()

    def _migrate_add_column(self, table: str, column: str, col_type: str) -> None:
        try:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass

    def save_holdings(self, session_id: str, holdings: list[HoldingRecord]) -> dict:
        """Save or update holdings for a session."""
        now = datetime.now().isoformat()
        for h in holdings:
            self._conn.execute(
                """INSERT INTO holdings (session_id, stock_code, stock_name, quantity,
                   cost_price, current_price, market_value, pnl, pnl_pct, industry, weight, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, stock_code) DO UPDATE SET
                   stock_name=excluded.stock_name, quantity=excluded.quantity,
                   cost_price=excluded.cost_price, current_price=excluded.current_price,
                   market_value=excluded.market_value, pnl=excluded.pnl, pnl_pct=excluded.pnl_pct,
                   industry=excluded.industry, weight=excluded.weight, updated_at=excluded.updated_at""",
                (session_id, h.stock_code, h.stock_name, h.quantity,
                 h.cost_price, h.current_price, h.market_value,
                 h.pnl, h.pnl_pct, h.industry, h.weight, now),
            )
        self._conn.commit()
        logger.info("holdings_saved", session_id=session_id, count=len(holdings))
        return {"session_id": session_id, "count": len(holdings), "status": "saved"}

    def get_holdings(self, session_id: str) -> list[HoldingRecord]:
        """Get current holdings for a session."""
        rows = self._conn.execute(
            "SELECT * FROM holdings WHERE session_id = ? ORDER BY market_value DESC",
            (session_id,),
        ).fetchall()
        return [
            HoldingRecord(
                stock_code=r["stock_code"], stock_name=r["stock_name"],
                quantity=r["quantity"], cost_price=r["cost_price"],
                current_price=r["current_price"], market_value=r["market_value"],
                pnl=r["pnl"], pnl_pct=r["pnl_pct"],
                industry=r["industry"], weight=r["weight"],
            )
            for r in rows
        ]

    def save_rules(self, session_id: str, rules: list[PositionRule]) -> dict:
        """Save position management rules (replaces existing)."""
        now = datetime.now().isoformat()
        # Clear existing rules for this session
        self._conn.execute("DELETE FROM position_rules WHERE session_id = ?", (session_id,))
        for r in rules:
            self._conn.execute(
                "INSERT INTO position_rules (session_id, rule_type, max_weight, scope, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, r.rule_type.value, r.max_weight, r.scope, now),
            )
        self._conn.commit()
        logger.info("position_rules_saved", session_id=session_id, count=len(rules))
        return {"session_id": session_id, "count": len(rules), "status": "saved"}

    def get_rules(self, session_id: str) -> list[PositionRule]:
        """Get position rules for a session."""
        rows = self._conn.execute(
            "SELECT * FROM position_rules WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return [
            PositionRule(rule_type=RuleType(r["rule_type"]), max_weight=r["max_weight"], scope=r["scope"])
            for r in rows
        ]

    def check_violations(
        self, holdings: list[HoldingRecord], rules: list[PositionRule]
    ) -> list[PositionViolation]:
        """Check all holdings against all rules, return violations."""
        violations = []

        for rule in rules:
            if rule.rule_type == RuleType.SINGLE_STOCK_LIMIT:
                for h in holdings:
                    if h.weight > rule.max_weight:
                        violations.append(PositionViolation(
                            rule_type=rule.rule_type,
                            stock_code=h.stock_code,
                            current_weight=h.weight,
                            max_weight=rule.max_weight,
                            excess=round(h.weight - rule.max_weight, 4),
                            message=f"{h.stock_code} 仓位 {h.weight:.1%} 超过单票上限 {rule.max_weight:.1%}",
                        ))

            elif rule.rule_type == RuleType.TOTAL_POSITION_LIMIT:
                total_weight = sum(h.weight for h in holdings)
                if total_weight > rule.max_weight:
                    violations.append(PositionViolation(
                        rule_type=rule.rule_type,
                        current_weight=total_weight,
                        max_weight=rule.max_weight,
                        excess=round(total_weight - rule.max_weight, 4),
                        message=f"总仓位 {total_weight:.1%} 超过上限 {rule.max_weight:.1%}",
                    ))

            elif rule.rule_type == RuleType.INDUSTRY_LIMIT:
                industry_weights: dict[str, float] = {}
                for h in holdings:
                    if h.industry:
                        industry_weights[h.industry] = industry_weights.get(h.industry, 0) + h.weight
                for industry, weight in industry_weights.items():
                    if weight > rule.max_weight and (not rule.scope or rule.scope == industry):
                        violations.append(PositionViolation(
                            rule_type=rule.rule_type,
                            industry=industry,
                            current_weight=weight,
                            max_weight=rule.max_weight,
                            excess=round(weight - rule.max_weight, 4),
                            message=f"{industry} 行业仓位 {weight:.1%} 超过上限 {rule.max_weight:.1%}",
                        ))

        logger.info("violations_checked", holdings=len(holdings), rules=len(rules), violations=len(violations))
        return violations

    def close(self) -> None:
        self._conn.close()
