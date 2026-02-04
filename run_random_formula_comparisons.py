import argparse
import json
import random
from pathlib import Path

from monitor_generator import compare_monitor_vs_dfa


def load_temporal_ops(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    unary = [item["op_notation"] for item in data if item["is_unary"]]
    binary = [item["op_notation"] for item in data if not item["is_unary"]]
    return unary, binary


def random_formula(rng, props, unary_temporal, binary_temporal, depth):
    if depth <= 0:
        return rng.choice(props)

    unary_ops = ["!", *unary_temporal]
    binary_ops = ["&&", "||", "->", "<->", *binary_temporal]

    choice = rng.random()
    if choice < 0.35:
        op = rng.choice(unary_ops)
        child = random_formula(rng, props, unary_temporal, binary_temporal, depth - 1)
        return f"{op} {child}"
    else:
        op = rng.choice(binary_ops)
        left = random_formula(rng, props, unary_temporal, binary_temporal, depth - 1)
        right = random_formula(rng, props, unary_temporal, binary_temporal, depth - 1)
        return f"({left} {op} {right})"


def main():
    parser = argparse.ArgumentParser(description="Compare monitor vs DFA on random formulas.")
    parser.add_argument("--count", type=int, default=100, help="Number of formulas to test.")
    parser.add_argument("--traces", type=int, default=30000, help="Traces per formula.")
    parser.add_argument("--max-len", type=int, default=50, help="Max trace length.")
    parser.add_argument("--depth", type=int, default=4, help="Formula depth.")
    parser.add_argument("--props", type=int, default=5, help="Number of propositions (q1..qN).")
    parser.add_argument("--seed", type=int, default=11, help="Random seed.")
    parser.add_argument("--json", default="operators_data.json", help="Path to operators_data.json.")
    parser.add_argument("--walks", type=int, default=800, help="Equivalence oracle walks.")
    parser.add_argument("--walk-len", type=int, default=15, help="Equivalence oracle walk length.")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    props = [f"q{i}" for i in range(1, args.props + 1)]
    unary_temporal, binary_temporal = load_temporal_ops(args.json)

    for i in range(args.count):
        formula = random_formula(rng, props, unary_temporal, binary_temporal, args.depth)
        try:
            result = compare_monitor_vs_dfa(
                formula,
                num_traces=args.traces,
                max_len=args.max_len,
                seed=rng.randint(0, 1_000_000),
                walks=args.walks,
                walk_len=args.walk_len,
            )
            mismatches = len(result["mismatches"])
            print(f"[{i + 1}/{args.count}] {formula}")
            print(f"  traces_tested={args.traces} mismatches={mismatches} states={result['state_count']}")
        except Exception as exc:
            print(f"[{i + 1}/{args.count}] {formula}")
            print(f"  error={exc}")


if __name__ == "__main__":
    main()
