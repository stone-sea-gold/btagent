"""Test LLM agent's natural language → tool call translation.

Uses the actual agent graph and captures the first tool call
to verify correct parameter extraction.

Usage:
    python tests/test_agent_translation.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.graph import create_agent_graph
from src.api.dependencies import init_services


# ── Test cases ──────────────────────────────────────────────────
# (user_message, expected_tool, expected_params_subset_or_None)
# If expected_params is None, only check tool name.

TEST_CASES = [
    (
        "帮我搜索动量因子",
        "_search_factors",
        {"query": "动量"},
    ),
    (
        "帮我用3个月动量因子快速回测一下，2019年全年，选前10只股票，月度调仓",
        "_run_backtest",
        None,
    ),
    (
        "帮我用动量因子和价值因子构建一个策略，回测时间2019-01-01到2019-06-30",
        "_compose_strategy",
        {"start_date": "2019-01-01", "end_date": "2019-06-30"},
    ),
    (
        "看看我保存了哪些策略",
        "_list_strategies",
        {},
    ),
    (
        "今天是几号",
        "_get_current_date",
        {},
    ),
]


def run_tests():
    print("初始化服务...")
    services = init_services()

    graph = create_agent_graph(
        factor_store=services.factor_store,
        strategy_compiler=services.strategy_compiler,
        backtest_engine=services.backtest_engine,
        strategy_store=services.strategy_store,
        session_store=services.session_store,
        position_manager=services.position_manager,
        param_optimizer=services.param_optimizer,
        stock_selector=services.stock_selector,
        checkpointer=None,
    )

    results = []

    for i, (user_msg, expected_tool, expected_params) in enumerate(TEST_CASES):
        print(f"\n{'='*60}")
        print(f"测试 {i+1}: {user_msg[:50]}...")
        print(f"  期望工具: {expected_tool}")

        try:
            # Stream the graph and capture the first agent output
            input_state = {
                "messages": [HumanMessage(content=user_msg)],
                "session_id": "",
                "current_strategy": None,
                "last_backtest_result": None,
                "tool_call_log": [],
            }

            tool_calls = []
            for event in graph.stream(input_state, stream_mode="updates"):
                for node_name, update in event.items():
                    if node_name == "agent":
                        msgs = update.get("messages", [])
                        for msg in msgs:
                            if isinstance(msg, AIMessage) and msg.tool_calls:
                                tool_calls = msg.tool_calls
                                break
                    # Stop after capturing agent's tool calls (don't execute tools)
                if tool_calls:
                    break

            if not tool_calls:
                print(f"  结果: FAIL — LLM 没有调用任何工具")
                results.append((i + 1, user_msg[:40], "FAIL", "无工具调用"))
                continue

            first_call = tool_calls[0]
            actual_tool = first_call["name"]
            actual_args = first_call["args"]

            print(f"  实际工具: {actual_tool}")
            print(f"  参数: {json.dumps(actual_args, ensure_ascii=False)[:200]}")

            # Check tool name
            if actual_tool != expected_tool:
                print(f"  结果: FAIL — 期望 {expected_tool}, 实际 {actual_tool}")
                results.append((i + 1, user_msg[:40], "FAIL", f"{actual_tool} != {expected_tool}"))
                continue

            # Check params
            if expected_params is not None:
                mismatches = []
                for key, expected_val in expected_params.items():
                    actual_val = actual_args.get(key)
                    if actual_val != expected_val:
                        mismatches.append(f"{key}: 期望={expected_val}, 实际={actual_val}")

                if mismatches:
                    print(f"  结果: FAIL — 参数不匹配:")
                    for m in mismatches:
                        print(f"    {m}")
                    results.append((i + 1, user_msg[:40], "FAIL", "; ".join(mismatches)))
                else:
                    print(f"  结果: PASS")
                    results.append((i + 1, user_msg[:40], "PASS", ""))
            else:
                print(f"  结果: PASS")
                results.append((i + 1, user_msg[:40], "PASS", ""))

        except Exception as e:
            print(f"  结果: ERROR — {e}")
            results.append((i + 1, user_msg[:40], "ERROR", str(e)[:100]))

    # Summary
    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    passed = sum(1 for _, _, s, _ in results if s == "PASS")
    failed = len(results) - passed
    print(f"通过: {passed}/{len(results)}, 失败: {failed}/{len(results)}")
    for idx, msg, status, detail in results:
        marker = "V" if status == "PASS" else "X"
        print(f"  [{marker}] {idx}. {msg} — {status} {detail}")

    services.close()
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
