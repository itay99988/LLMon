#!/usr/bin/env python
"""
batch_formula_tester.py
───────────────────────
Randomly generate 100 PT-LTL formulas that contain a custom operator,
build monitors for each, and compare them to monitors derived from the
canonical translation that uses only the basic operators
      @  P  H   (unary)    and   S   (binary).

Requires the following modules on your PYTHONPATH:
    • syntax_translator.py   – must expose  translate_formula
    • monitor_generator.py         – must expose  gen_save_monitor_code
    • compare_monitors.py          – must expose  compare_monitors

Example
-------
$ python batch_formula_tester.py \
      --new-op Aft --equiv "({left}) S ({right})"
"""

from __future__ import annotations
import argparse, importlib, random, re, sys
from pathlib import Path

# Locate the directory one level up from *this* file
PARENT_DIR = Path(__file__).resolve().parents[1]

# Put it on sys.path if it is not there already
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

translate_formula                   = importlib.import_module(
    "syntax_translator"
).translate_formula
gen_save_monitor_code_with_aux      = importlib.import_module(
    "monitor_generator_with_aux"
).gen_save_monitor_code_with_aux
gen_save_monitor_code               = importlib.import_module(
    "monitor_generator"
).gen_save_monitor_code
compare_monitors                    = importlib.import_module(
    "compare_monitors_with_aux"
).compare_monitors

def parse_cli() -> tuple[str, str]:
    ap = argparse.ArgumentParser(
        description=("Batch-test 100 random formulas that use a custom "
                     "past-time LTL construct."))
    ap.add_argument("--new-op", required=True,
                    help="Notation of the construct (token) – e.g. N, Aft")
    ap.add_argument("--equiv",  required=True,
                    help=("Equivalence template using ONLY the four basic "
                          "operators.  Unary: must contain {arg};  "
                          "Binary: must contain {left} and {right}."))
    args = ap.parse_args()
    return args.new_op, args.equiv


# ------------------------------------------------------------------------
# random-formula generator  (updated)
# ------------------------------------------------------------------------
LOGIC_BIN        = ["&&", "||", "->", "<->"]
UNARY_BASICS     = ["@", "P", "H"]
BINARY_BASIC_OP  = "S"

TOKEN_RE_TEMPLATE = r'(<->|->|&&|\|\||!|%s|@|P|H|S|q\d+)'

# –– helper --------------------------------------------------------------
def count_tokens(expr: str, new_op: str) -> int:
    token_re = re.compile(TOKEN_RE_TEMPLATE % re.escape(new_op))
    return len(token_re.findall(expr))

def ensure_contiguous_vars(expr: str) -> str:
    """Inject missing q-variables so we have q1..qk with no gaps."""
    used = {int(m.group(1)) for m in re.finditer(r"q(\d+)", expr)}
    if not used:
        return expr + " && q1"
    k = max(used)
    missing = [f"q{i}" for i in range(1, k + 1) if i not in used]
    for v in missing:
        # Glue the missing var with a harmless conjunction
        expr = f"({expr} && {v})"
    return expr

# –– variable-aware builders --------------------------------------------
def random_var(pool: list[str]) -> str:
    return random.choice(pool)

def random_basic_unary(expr: str) -> str:
    op = random.choice(UNARY_BASICS)
    return f"{op}({expr})"

def random_basic_binary(left: str, right: str) -> str:
    return f"({left} {BINARY_BASIC_OP} {right})"

def gen_random_expr(depth: int,
                    var_pool: list[str],
                    new_op: str,
                    is_new_unary: bool) -> str:
    """Recursive generator – gets more complex with depth."""
    if depth == 0:
        base = random_var(var_pool)
        return f"!{base}" if random.random() < 0.25 else base

    choice = random.random()
    if choice < 0.55:            # unary basic
        return random_basic_unary(
            gen_random_expr(depth - 1, var_pool, new_op, is_new_unary))
    elif choice < 0.8:          # binary basic  S
        return random_basic_binary(
            gen_random_expr(depth - 1, var_pool, new_op, is_new_unary),
            gen_random_expr(depth - 1, var_pool, new_op, is_new_unary),
        )
    else:                       # logic connective
        left  = gen_random_expr(depth - 1, var_pool, new_op, is_new_unary)
        right = gen_random_expr(depth - 1, var_pool, new_op, is_new_unary)
        op    = random.choice(LOGIC_BIN)
        return f"({left} {op} {right})"

def inject_new_construct(expr: str,
                         var_pool: list[str],
                         new_op: str,
                         is_new_unary: bool) -> str:
    """Guarantee at least ONE occurrence of the construct."""
    sub = gen_random_expr(1, var_pool, new_op, is_new_unary)
    if is_new_unary:
        wrapped = f"({new_op}({sub}))"
    else:
        other   = gen_random_expr(1, var_pool, new_op, is_new_unary)
        wrapped = f"(({sub}) {new_op} ({other}))"
    return f"({expr} && {wrapped})" if random.random() < 0.5 else f"({wrapped} || {expr})"

def make_formula(new_op: str,
                 is_new_unary: bool,
                 target_tokens: int = 5) -> str:
    """
    Build a formula whose variables are q1..qk (contiguous from 1) and
    whose total token count is roughly `target_tokens`.
    """
    # 1. Pick a contiguous variable block  q1..qk   (k ∈ {1,…,5})
    k         = random.randint(1, 5)
    var_pool  = [f"q{i}" for i in range(1, k + 1)]

    # 2. Generate a core expression and inject the custom operator
    depth     = random.randint(2, 3)
    expr      = gen_random_expr(depth, var_pool, new_op, is_new_unary)
    expr      = inject_new_construct(expr, var_pool, new_op, is_new_unary)

    # 3. Ensure *all* variables q1..qk appear
    expr      = ensure_contiguous_vars(expr)

    # 4. Optionally shrink/grow tokens by adding harmless conjunctions
    #    until we are close to the target (±2 tokens tolerance)
    while count_tokens(expr, new_op) < target_tokens - 2:
        expr = f"({expr} && {random_var(var_pool)})"
    return expr


def run_single(idx: int,
               new_op: str,
               equivalence: str,
               new_formula: str) -> bool:
    """Generate monitor, translate formula, compare. Return success bool."""
    standard_formula = translate_formula(new_op, equivalence, new_formula)

    # Re-use a single filename (overwrite) to keep directory tidy
    cust_monitor_path = Path("custom_monitor.py").as_posix()
    gen_save_monitor_code(new_formula, cust_monitor_path)

    std_monitor_path = Path("standard_monitor.py").as_posix()
    gen_save_monitor_code_with_aux(standard_formula, std_monitor_path)

    print(f"\n── Test #{idx:02d} ──────────────────────────────────────────")
    print("Original formula: ", new_formula)
    print("Translated:      ", standard_formula)
    print("------------------------------------------------------------")

    result = compare_monitors(cust_monitor_path, std_monitor_path, standard_formula)
    # compare_monitors prints its own report and returns True / False
    print("Result:", "SUCCESS" if result else "FAIL")
    return bool(result)


# ──────────────────────────────────────────────────────────────────────────
# main batch driver
# ──────────────────────────────────────────────────────────────────────────
def main() -> None:
    new_op, equiv = parse_cli()
    is_new_unary  = "{arg}" in equiv
    if is_new_unary:
        assert "{left}" not in equiv and "{right}" not in equiv, \
            "Unary template must NOT contain {left}/{right}"
    else:
        assert "{left}" in equiv and "{right}" in equiv, \
            "Binary template must contain {left} and {right}"

    successes = 0
    for i in range(1, 101):
        formula = make_formula(new_op, is_new_unary, target_tokens=10)
        if run_single(i, new_op, equiv, formula):
            successes += 1

    print("\n============================================================")
    print(f"   TOTAL SUCCEEDED:  {successes} / 100")
    print("============================================================")


# ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
