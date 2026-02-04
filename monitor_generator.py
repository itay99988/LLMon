#  monitor_generator.py  –  JSON-driven generator for RV monitors. outputs a monitor file
#  ───────────────────────────────────────────────────────────────────
"""
$ python monitor_generator.py "<FORMULA>"  monitor.py

The generator expects an `operators_data.json` file next to this script.
"""

import json, re, sys
from pathlib import Path
from textwrap import indent, dedent
from itertools import product
from collections import deque
from typing import Any, Dict, List, Tuple, Set, Optional

# For automaton construction
from automata.fa.dfa import DFA

# ───────────────────────────────────────────────────────────────
# helpers
# ───────────────────────────────────────────────────────────────
def _decode_class(text: str) -> str:
    """Turn the literal '\n' sequences from JSON into real new-lines."""
    return dedent(text.replace("\\n", "\n")).rstrip()
def _syntax_error(msg: str):
    sys.stderr.write(f"Syntax error while parsing formula: {msg}\n")
    sys.exit(3)


def _load_ops_metadata() -> Tuple[Dict[str, Any], Set[str], Set[str], Dict[str, str], Dict[str, str]]:
    ops_json = Path(__file__).with_name("operators_data.json")
    if not ops_json.exists():
        sys.stderr.write(f"ERROR: {ops_json} not found\n")
        sys.exit(2)

    with ops_json.open(encoding="utf-8") as f:
        data = json.load(f)

    req = {"op_notation", "is_unary", "class_name", "class_content"}
    for item in data:
        if not req.issubset(item):
            raise ValueError(f"operator entry missing keys: {item}")

    temporal_ops = {item["op_notation"]: item for item in data}
    unary_temporal = {k for k, v in temporal_ops.items() if v["is_unary"]}
    binary_temporal = set(temporal_ops) - unary_temporal
    temp_classname = {k: v["class_name"] for k, v in temporal_ops.items()}
    temp_classcode = {
        v["class_name"]: _decode_class(v["class_content"])
        for v in temporal_ops.values()
    }
    return temporal_ops, unary_temporal, binary_temporal, temp_classname, temp_classcode

def build_operator_class(class_content: str, class_name: str):
    namespace: Dict[str, Any] = {}
    exec(class_content, namespace)
    if class_name not in namespace:
        raise ValueError(f"Class '{class_name}' not found in class_content.")
    return namespace[class_name]


def build_monitor_dfa_stateful(formula: str) -> DFA:
    """
    Build a DFA for the monitor by tracking operator class field tuples (stateful simulation).
    - Operator nodes (temporal + standard logic) are included in the state vector.
    - Temporal nodes track tuples of their instance fields; logic nodes track their current boolean value.
    - Transitions are explored via BFS over all proposition assignments until closure.
    """

    TEMPORAL_OPS, UNARY_TEMPORAL, BINARY_TEMPORAL, TEMP_CLASSNAME, TEMP_CLASSCODE = _load_ops_metadata()

    # ---------- Lexer / Parser (same as build_monitor_dfa) ----------
    BOOL_MULTI = ["<->", "->", "&&", "||"]
    MULTI_TOKENS = sorted([*BOOL_MULTI, *(tok for tok in TEMPORAL_OPS if len(tok) > 1)], key=len, reverse=True)
    SINGLE_TOKENS = [tok for tok in TEMPORAL_OPS if len(tok) == 1]

    token_re = re.compile(
        r"""(
            \s+                                   |  # whitespace
            {}                                    |  # multi-char ops
            [{}()]                                |  # parentheses
            !                                     |  # negation
            and|or|not                            |  # word ops
            q\d+                                     # propositions
        )""".format(
            "|".join(re.escape(t) for t in MULTI_TOKENS),
            re.escape("".join(SINGLE_TOKENS)),
        ),
        re.VERBOSE | re.IGNORECASE,
    )

    def tokenize(s: str):
        for m in token_re.finditer(s):
            tok = m.group(0)
            if not tok.isspace():
                yield tok
        yield "EOF"

    PRECEDENCE = {
        "<->": 1,
        "->": 2,
        **{tok: 3 for tok in (set(TEMPORAL_OPS) - UNARY_TEMPORAL)},
        "or": 4,
        "||": 4,
        "and": 5,
        "&&": 5,
    }
    UNARY = {"not", "!", *UNARY_TEMPORAL}

    class AST:
        _counter = 0

        def __init__(self, op, *kids):
            AST._counter += 1
            self.id, self.op, self.kids = f"n{AST._counter}", op, kids

        def walk_post(self):
            for k in self.kids:
                yield from k.walk_post()
            yield self

    def parse(tokens):
        tok_iter = iter(tokens)
        current = next(tok_iter)

        def peek():
            return current

        def advance():
            nonlocal current
            current = next(tok_iter)

        def primary():
            tok = peek()
            advance()
            if tok == "(":
                node = expr(0)
                if peek() != ")":
                    _syntax_error("missing ')'")
                advance()
                return node
            if tok in UNARY:
                return AST(tok, primary())
            if re.fullmatch(r"q\d+", tok):
                return AST(tok)
            _syntax_error(f"unexpected token {tok}")

        def expr(min_prec):
            node = primary()
            while True:
                tok = peek()
                if tok in PRECEDENCE and PRECEDENCE[tok] >= min_prec:
                    prec = PRECEDENCE[tok]
                    advance()
                    right = expr(prec + 1)
                    node = AST(tok, node, right)
                else:
                    break
            return node

        tree = expr(0)
        if peek() != "EOF":
            _syntax_error("extra input")
        return tree

    ast = parse(tokenize(formula))

    # ---------- Collect propositions and operator nodes ----------
    propositions: Set[str] = set()
    operator_nodes: List[AST] = []
    for node in ast.walk_post():
        if re.fullmatch(r"q\d+", node.op):
            propositions.add(node.op)
        if node.op in TEMPORAL_OPS or node.op in {"and", "&&", "or", "||", "not", "!", "->", "<->"}:
            operator_nodes.append(node)

    prop_list = sorted(propositions)
    if not prop_list:
        raise ValueError("Formula must reference at least one proposition (q1, q2, ...).")

    # ---------- Prepare operator classes and field order ----------
    temporal_classes: Dict[str, Any] = {}
    field_order: Dict[str, List[str]] = {}
    for node in operator_nodes:
        if node.op not in TEMPORAL_OPS:
            continue
        meta = TEMPORAL_OPS[node.op]
        cls = build_operator_class(meta["class_content"], meta["class_name"])
        temporal_classes[node.id] = cls
        inst = cls()
        field_order[node.id] = sorted(vars(inst).keys())

    node_order = [n.id for n in operator_nodes]

    def vector_from_map(state_map: Dict[str, Any]) -> Tuple[Any, ...]:
        return tuple(state_map[nid] for nid in node_order)

    def map_from_vector(vec: Tuple[Any, ...]) -> Dict[str, Any]:
        return {nid: vec[i] for i, nid in enumerate(node_order)}

    # ---------- Helpers to snapshot/restore temporal operator state ----------
    def snapshot_state(node_id: str, instance) -> Tuple[Any, ...]:
        return tuple(getattr(instance, name) for name in field_order[node_id])

    def restore_instance(node_id: str, state_tuple: Tuple[Any, ...]):
        cls = temporal_classes[node_id]
        inst = cls()
        for name, val in zip(field_order[node_id], state_tuple):
            setattr(inst, name, val)
        return inst

    # ---------- Evaluate one step ----------
    def eval_node(node: AST, event: Dict[str, bool], curr_states: Dict[str, Any], next_states: Dict[str, Any]) -> bool:
        if re.fullmatch(r"q\d+", node.op):
            return event.get(node.op, False)
        if node.op in {"and", "&&"}:
            left = eval_node(node.kids[0], event, curr_states, next_states)
            right = eval_node(node.kids[1], event, curr_states, next_states)
            value = left and right
            next_states[node.id] = value
            return value
        if node.op in {"or", "||"}:
            left = eval_node(node.kids[0], event, curr_states, next_states)
            right = eval_node(node.kids[1], event, curr_states, next_states)
            value = left or right
            next_states[node.id] = value
            return value
        if node.op in {"not", "!"}:
            value = not eval_node(node.kids[0], event, curr_states, next_states)
            next_states[node.id] = value
            return value
        if node.op == "->":
            a = eval_node(node.kids[0], event, curr_states, next_states)
            b = eval_node(node.kids[1], event, curr_states, next_states)
            value = (not a) or b
            next_states[node.id] = value
            return value
        if node.op == "<->":
            a = eval_node(node.kids[0], event, curr_states, next_states)
            b = eval_node(node.kids[1], event, curr_states, next_states)
            value = a == b
            next_states[node.id] = value
            return value

        # temporal operator with explicit state
        curr_state_tuple = curr_states[node.id]
        inst = restore_instance(node.id, curr_state_tuple)
        if node.op in UNARY_TEMPORAL:
            arg = eval_node(node.kids[0], event, curr_states, next_states)
            out = inst.update(arg)
        else:
            left_val = eval_node(node.kids[0], event, curr_states, next_states)
            right_val = eval_node(node.kids[1], event, curr_states, next_states)
            out = inst.update(left_val, right_val)
        next_states[node.id] = snapshot_state(node.id, inst)
        return out

    # ---------- Alphabet ----------
    alphabet = list(product([False, True], repeat=len(prop_list)))

    def make_event(symbol_tuple: Tuple[bool, ...]) -> Dict[str, bool]:
        return {prop_list[i]: symbol_tuple[i] for i in range(len(prop_list))}

    # ---------- Initial state ----------
    initial_state_map: Dict[str, Any] = {}
    for node in operator_nodes:
        if node.op in TEMPORAL_OPS:
            inst = temporal_classes[node.id]()
            initial_state_map[node.id] = snapshot_state(node.id, inst)
        else:
            initial_state_map[node.id] = False
    initial_vec = vector_from_map(initial_state_map)

    # ---------- BFS ----------
    queue: List[Tuple[Any, ...]] = [initial_vec]
    visited: Dict[Tuple[Any, ...], str] = {initial_vec: "S0"}
    transitions: Dict[str, Dict[Tuple[bool, ...], str]] = {}
    accepting: Set[str] = set()
    name_counter = 1

    while queue:
        vec = queue.pop(0)
        state_name = visited[vec]
        transitions[state_name] = {}
        curr_state_map = map_from_vector(vec)

        for sym in alphabet:
            event = make_event(sym)
            next_state_map: Dict[str, Any] = {}
            root_val = eval_node(ast, event, curr_state_map, next_state_map)
            next_vec = vector_from_map(next_state_map)
            if next_vec not in visited:
                visited[next_vec] = f"S{name_counter}"
                name_counter += 1
                queue.append(next_vec)
            transitions[state_name][sym] = visited[next_vec]
            if root_val:
                accepting.add(visited[next_vec])

    monitor_dfa = DFA(
        states=set(visited.values()),
        input_symbols=set(alphabet),
        transitions=transitions,
        initial_state="S0",
        final_states=accepting,
    )
    return monitor_dfa, len(visited)


def compare_monitor_vs_dfa(
    formula: str,
    num_traces: int = 200,
    max_len: int = 8,
    seed: int = 0,
    walks: int = 800,
    walk_len: int = 15,
) -> Dict[str, Any]:
    """
    Generate a monitor and a learned monitor-automaton for the formula,
    then compare their verdicts across random traces.
    """
    import random

    # Build the runtime monitor function from generated code.
    monitor_code = make_monitor_code(formula)
    ns: Dict[str, Any] = {}
    exec(monitor_code, ns)
    analyze_trace = ns["analyze_trace"]

    # Build the monitor DFA (learned composition of operator automata).
    dfa, state_count = build_monitor_dfa_stateful(formula)

    # Proposition order must match DFA symbol ordering.
    props = sorted(set(re.findall(r"q\d+", formula)))
    if not props:
        raise ValueError("Formula must contain at least one proposition qN.")

    rng = random.Random(seed)
    mismatches: List[Dict[str, Any]] = []

    def eval_dfa(trace: List[Dict[str, bool]]) -> List[bool]:
        state = dfa.initial_state
        verdicts = []
        for event in trace:
            symbol = tuple(event.get(p, False) for p in props)
            state = dfa.transitions[state][symbol]
            verdicts.append(state in dfa.final_states)
        return verdicts

    for _ in range(num_traces):
        length = rng.randint(1, max_len)
        trace = [
            {p: bool(rng.getrandbits(1)) for p in props}
            for _ in range(length)
        ]
        monitor_out = analyze_trace(trace)
        dfa_out = eval_dfa(trace)

        if monitor_out != dfa_out:
            mismatches.append(
                {
                    "trace": trace,
                    "monitor": monitor_out,
                    "dfa": dfa_out,
                }
            )

    return {
        "formula": formula,
        "props": props,
        "num_traces": num_traces,
        "max_len": max_len,
        "seed": seed,
        "state_count": state_count,
        "mismatches": mismatches,
    }


def find_distinguishing_traces(
    formula_i: str,
    formula_j: str,
    version_i: int,
    version_j: int,
    walks: int = 800,
    walk_len: int = 15,
) -> Dict[str, str]:
    """
    Build monitor DFAs for two formulas and return shortest distinguishing traces.
    Returns at most two keys: diff1 (Ai - Aj) and diff2 (Aj - Ai).
    """
    props_i = sorted(set(re.findall(r"q\d+", formula_i)))
    props_j = sorted(set(re.findall(r"q\d+", formula_j)))
    if props_i != props_j:
        raise ValueError("Formulas must contain the same set of propositions.")
    props = props_i

    dfa_i, _ = build_monitor_dfa_stateful(formula_i)
    dfa_j, _ = build_monitor_dfa_stateful(formula_j)

    alphabet = sorted(dfa_i.input_symbols)
    if set(alphabet) != set(dfa_j.input_symbols):
        raise ValueError("Monitor DFAs have different alphabets.")

    comp_accept_j = (dfa_j.states - dfa_j.final_states) - {dfa_j.initial_state}
    comp_accept_i = (dfa_i.states - dfa_i.final_states) - {dfa_i.initial_state}

    def shortest_diff_trace(
        dfa_a: DFA,
        dfa_b: DFA,
        accept_a: Set[Any],
        accept_b: Set[Any],
    ) -> Optional[List[Tuple[bool, ...]]]:
        start = (dfa_a.initial_state, dfa_b.initial_state)
        if start[0] in accept_a and start[1] in accept_b:
            return []
        queue = deque([start])
        prev: Dict[Tuple[Any, Any], Tuple[Optional[Tuple[Any, Any]], Optional[Tuple[bool, ...]]]] = {
            start: (None, None)
        }
        while queue:
            curr = queue.popleft()
            for sym in alphabet:
                nxt = (dfa_a.transitions[curr[0]][sym], dfa_b.transitions[curr[1]][sym])
                if nxt in prev:
                    continue
                prev[nxt] = (curr, sym)
                if nxt[0] in accept_a and nxt[1] in accept_b:
                    path: List[Tuple[bool, ...]] = []
                    node = nxt
                    while prev[node][0] is not None:
                        node, symbol = prev[node]
                        if symbol is not None:
                            path.append(symbol)
                    path.reverse()
                    return path
                queue.append(nxt)
        return None

    def format_trace(symbols: List[Tuple[bool, ...]], verdict_i: bool, verdict_j: bool) -> str:
        prop_values = {p: [] for p in props}
        for sym in symbols:
            for idx, p in enumerate(props):
                prop_values[p].append(sym[idx])
        parts = []
        for p in props:
            vals = prop_values[p]
            if not vals:
                seq = ""
            else:
                seq = ", ".join("True" if v else "False" for v in vals)
            parts.append(f"{p} = ({seq})")
        return (
            f"Trace: {'; '.join(parts)} => "
            f"Version {version_i}: {'True' if verdict_i else 'False'}, "
            f"Version {version_j}: {'True' if verdict_j else 'False'}"
        )

    results: Dict[str, str] = {}

    diff1 = shortest_diff_trace(dfa_i, dfa_j, dfa_i.final_states, comp_accept_j)
    if diff1 is not None:
        results["diff1"] = format_trace(diff1, True, False)

    diff2 = shortest_diff_trace(dfa_j, dfa_i, dfa_j.final_states, comp_accept_i)
    if diff2 is not None:
        results["diff2"] = format_trace(diff2, False, True)

    return results

# ───────────────────────────────────────────────────────────────
# main code-generation routine
# ───────────────────────────────────────────────────────────────
def make_monitor_code(formula: str) -> str:
    """Parse formula and return the complete source of the monitor."""
    # 0) ------------------------------------------------ read JSON
    ops_json = Path(__file__).with_name("operators_data.json")
    if not ops_json.exists():
        sys.stderr.write(f"ERROR: {ops_json} not found\n")
        sys.exit(2)

    with ops_json.open(encoding="utf-8") as f:
        data = json.load(f)

    req = {"op_notation", "is_unary", "class_name", "class_content"}
    for item in data:
        if not req.issubset(item):
            raise ValueError(f"operator entry missing keys: {item}")

    TEMPORAL_OPS   = {item["op_notation"]: item for item in data}
    UNARY_TEMPORAL = {k for k, v in TEMPORAL_OPS.items() if v["is_unary"]}
    BINARY_TEMPORAL= set(TEMPORAL_OPS) - UNARY_TEMPORAL
    TEMP_CLASSNAME = {k: v["class_name"]   for k, v in TEMPORAL_OPS.items()}
    TEMP_CLASSCODE = {
        v["class_name"]: _decode_class(v["class_content"])
        for v in TEMPORAL_OPS.values()
    }

    # 1) ------------------------------------------------ LEXER
    BOOL_MULTI = ["<->", "->", "&&", "||"]
    MULTI_TOKENS = sorted([*BOOL_MULTI,
                           *(tok for tok in TEMPORAL_OPS if len(tok) > 1)],
                          key=len, reverse=True)
    SINGLE_TOKENS = [tok for tok in TEMPORAL_OPS if len(tok) == 1]

    token_re = re.compile(
        r"""(
            \s+                                   |  # whitespace
            {}                                    |  # multi-char ops
            [{}()]                                |  # parentheses
            !                                     |  # negation
            and|or|not                            |  # word ops
            q\d+                                     # propositions
        )""".format(
            "|".join(re.escape(t) for t in MULTI_TOKENS),
            re.escape("".join(SINGLE_TOKENS)),
        ),
        re.VERBOSE | re.IGNORECASE,
    )

    def tokenize(s: str):
        for m in token_re.finditer(s):
            tok = m.group(0)
            if not tok.isspace():
                yield tok
        yield "EOF"

    # 2) ------------------------------------------------ PARSER
    PRECEDENCE = {
        "<->": 1, "->": 2,
        **{tok: 3 for tok in BINARY_TEMPORAL},     # all binary temporals
        "or": 4, "||": 4,
        "and": 5, "&&": 5,
    }
    UNARY = {"not", "!", *UNARY_TEMPORAL}

    class AST:
        _counter = 0
        def __init__(self, op, *kids):
            AST._counter += 1
            self.id, self.op, self.kids = f"n{AST._counter}", op, kids

        # ---- code-generation helpers ----
        def obj_name(self): return f"o_{self.id}"
        def val_name(self): return f"v_{self.id}"

        def emit_decls(self, out: set[str]):
            if self.op in TEMPORAL_OPS:
                out.add(f"{self.obj_name()} = {TEMP_CLASSNAME[self.op]}()")
            for k in self.kids: k.emit_decls(out)

        def emit_updates(self, lines: list[str]):
            for k in self.kids: k.emit_updates(lines)

            if re.fullmatch(r"q\d+", self.op):
                lines.append(f"{self.val_name()} = event.get('{self.op}', False)")
            elif self.op in {"and", "&&"}:
                lines.append(f"{self.val_name()} = {self.kids[0].val_name()} and {self.kids[1].val_name()}")
            elif self.op in {"or", "||"}:
                lines.append(f"{self.val_name()} = {self.kids[0].val_name()} or {self.kids[1].val_name()}")
            elif self.op in {"not", "!"}:
                lines.append(f"{self.val_name()} = not {self.kids[0].val_name()}")
            elif self.op == "->":
                a, b = self.kids
                lines.append(f"{self.val_name()} = (not {a.val_name()}) or {b.val_name()}")
            elif self.op == "<->":
                a, b = self.kids
                lines.append(f"{self.val_name()} = {a.val_name()} == {b.val_name()}")
            elif self.op in TEMPORAL_OPS:
                if self.op in UNARY_TEMPORAL:
                    lines.append(f"{self.val_name()} = {self.obj_name()}.update({self.kids[0].val_name()})")
                else:
                    a, b = self.kids
                    lines.append(f"{self.val_name()} = {self.obj_name()}.update({a.val_name()}, {b.val_name()})")
            else:
                raise RuntimeError(f"unhandled operator {self.op}")

    def parse(tokens):
        tok_iter = iter(tokens); current = next(tok_iter)
        def peek(): return current
        def advance():  # noqa: non-local assignment
            nonlocal current
            current = next(tok_iter)

        def primary():
            tok = peek(); advance()
            if tok == "(":
                node = expr(0)
                if peek() != ")": _syntax_error("missing ')'")
                advance(); return node
            if tok in UNARY: return AST(tok, primary())
            if re.fullmatch(r"q\d+", tok): return AST(tok)
            _syntax_error(f"unexpected token {tok}")

        def expr(min_prec):
            node = primary()
            while True:
                tok = peek()
                if tok in PRECEDENCE and PRECEDENCE[tok] >= min_prec:
                    prec = PRECEDENCE[tok]; advance()
                    right = expr(prec + 1)
                    node = AST(tok, node, right)
                else: break
            return node

        tree = expr(0)
        if peek() != "EOF": _syntax_error("extra input")
        return tree

    # 3) ------------------------------------------------ code-emit
    ast = parse(tokenize(formula))

    decls: set[str] = set()
    ast.emit_decls(decls)

    updates: list[str] = []
    ast.emit_updates(updates)

    analyze_fn = (
        "def analyze_trace(trace):\n" +
        indent("\n".join([
            "# instantiate temporal operators",
            *sorted(decls),
            "",
            "verdicts = []",
            "for event in trace:",
            indent("\n".join(updates), " " * 4),
            f"    verdicts.append({ast.val_name()})",
            "return verdicts",
        ]), " " * 4)
    )

    header = f'''\
"""Auto-generated monitor – DO NOT EDIT
Formula: {formula}
Run  analyze_trace(trace)  where trace = List[Dict[str,bool]]
"""

# temporal helper classes (loaded from operators_data.json)
{ "\n\n".join(TEMP_CLASSCODE.values()) }
'''

    return header + "\n\n" + analyze_fn


# this function is called from the tool UI
def gen_save_monitor_code(formula: str, filename: str):
    code = make_monitor_code(formula)
    Path(filename).write_text(code, encoding="utf-8")
    print(f"Monitor written to {filename}")


# CLI for some local tests
def main():
    if len(sys.argv) != 3:
        print("Usage: python monitor_generator.py \"<FORMULA>\"  <out_file.py>")
        sys.exit(1)
    gen_save_monitor_code(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()

# result = compare_monitor_vs_dfa("PTH (q1)", num_traces=1000, max_len=20, seed=42)
# print("States:", result["state_count"])
# print("Mismatches:", len(result["mismatches"]))
# print(result)


# res = find_distinguishing_traces(
#     "((q1 HB q2) && (q3 S q1)) && @(q3)",
#     "((q1 HB q2) && (q3 WS q1)) && @(q3)",
#     version_i=1,
#     version_j=2,
# )
# print(res)

# dfa, state_count = build_monitor_dfa_stateful("@q1")
# render_dfa(dfa, "prev_dfa")