#  monitor_generator.py  –  JSON-driven generator for RV monitors. outputs a monitor file
#  ───────────────────────────────────────────────────────────────────
"""
$ python monitor_generator.py "<FORMULA>"  monitor.py

The generator expects an `operators_data.json` file next to this script.
"""

import json, re, sys
from pathlib import Path
from textwrap import indent, dedent

# ───────────────────────────────────────────────────────────────
# helpers
# ───────────────────────────────────────────────────────────────
def _decode_class(text: str) -> str:
    """Turn the literal '\n' sequences from JSON into real new-lines."""
    return dedent(text.replace("\\n", "\n")).rstrip()
def _syntax_error(msg: str):
    sys.stderr.write(f"Syntax error while parsing formula: {msg}\n")
    sys.exit(3)


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
