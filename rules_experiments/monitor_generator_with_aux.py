#  monitor_generator_with_aux.py  –  RV-monitor code-generator
#  this files generates monitors that support temporal operators + recursive auxiliary variables.
#  important - a generated monitor has to be in the same dir as the recursive_aux_var.py since it imports it.
#  ──────────────────────────────────────────────────────────────
"""
Usage
=====
$ python monitor_generator_with_aux.py "<FORMULA>"  monitor.py
$ python monitor.py                             # run the embedded demo

Required side-files in the SAME directory:

• aux_vars_data.json         – list of {"var_name": "a1", "transition_rule": "…"}
• recursive_aux_var.py  – defines  class RecursiveAuxVar(rule:str)
                          with  get_val()  and  update()  methods

Required side-files in the PARENT directory:
• operators_data.json   – as before (temporal operators)
"""

import json, re, sys
from pathlib import Path
from textwrap import indent, dedent

# ───────────────────────────────────────────────────────────────
# helpers
# ───────────────────────────────────────────────────────────────
def _decode(src: str) -> str:
    """Turn the two-character sequence '\\n' into real new-lines and dedent."""
    return dedent(src.replace("\\n", "\n")).rstrip()

def _load(path: Path, what: str) -> list[dict]:
    if not path.exists():
        sys.stderr.write(f"ERROR: missing {what} file: {path}\n"); sys.exit(2)
    with path.open(encoding="utf-8") as f:
        return json.load(f)

def _syntax(msg: str): sys.stderr.write(f"Syntax error: {msg}\n"); sys.exit(3)

# ───────────────────────────────────────────────────────────────
#  main generator
# ───────────────────────────────────────────────────────────────
def make_monitor_code(formula: str) -> str:
    here = Path(__file__).parent
    parent = Path(__file__).resolve().parents[1]

    op_raw  = _load(parent / "operators_data.json", "operators catalogue")
    aux_raw = _load(here / "aux_vars_data.json"      , "aux-vars catalogue")

    OPS = {e["op_notation"]: e for e in op_raw}
    UNARY_OPS = {k for k,v in OPS.items() if v["is_unary"]}
    BIN_OPS   = set(OPS) - UNARY_OPS
    OP_CLASS  = {k: v["class_name"]   for k,v in OPS.items()}
    OP_CODE   = {v["class_name"]: _decode(v["class_content"]) for v in OPS.values()}

    AUX      = {e["var_name"]: e["transition_rule"] for e in aux_raw}

    BOOL_MULTI = ["<->","->","&&","||"]
    MULTI_OPS  = sorted([*BOOL_MULTI,*(t for t in OPS if len(t)>1)],
                        key=len, reverse=True)
    SINGLE_OPS = "".join(t for t in OPS if len(t)==1)

    token_re = re.compile(
        rf"""(
            \s+                            |  # whitespace
            {'|'.join(map(re.escape,MULTI_OPS))} |
            [{re.escape(SINGLE_OPS)}()]    |  # single-char ops & parens
            !                              |  # negation
            and|or|not                     |  # word ops
            q\d+ | a\d+                      # propositions / aux vars
        )""", re.VERBOSE | re.IGNORECASE)

    def toks(s:str):
        for m in token_re.finditer(s):
            tok = m.group(0)
            if not tok.isspace(): yield tok
        yield "EOF"

    PREC = {"<->":1,"->":2,**{t:3 for t in BIN_OPS},"or":4,"||":4,"and":5,"&&":5}
    UNARY = {"not","!",*UNARY_OPS}

    class AST:
        _id = 0
        def __init__(self, op,*kids):
            AST._id+=1; self.id,self.op,self.kids=f"n{AST._id}",op,kids
        def v(self): return f"v_{self.id}"
        def o(self): return f"o_{self.id}"        # temporal objects

        def collect(self, tdecl:set[str], aux_decl:set[str], used_aux:set[str]):
            if self.op in OPS:
                tdecl.add(f"{self.o()} = {OP_CLASS[self.op]}()")
            elif self.op in AUX:
                aux_decl.add(f"{self.op}_obj = RecursiveAuxVar({AUX[self.op]!r})")
                used_aux.add(self.op)
            for k in self.kids: k.collect(tdecl, aux_decl, used_aux)

        def emit(self, lines:list[str]):
            for k in self.kids: k.emit(lines)
            if re.fullmatch(r"q\d+", self.op):
                lines.append(f"{self.v()} = event.get('{self.op}', False)")
            elif self.op in AUX:
                lines.append(f"{self.v()} = {self.op}_obj.get_val()")
            elif self.op in {"and","&&"}:
                lines.append(f"{self.v()} = {self.kids[0].v()} and {self.kids[1].v()}")
            elif self.op in {"or","||"}:
                lines.append(f"{self.v()} = {self.kids[0].v()} or {self.kids[1].v()}")
            elif self.op in {"not","!"}:
                lines.append(f"{self.v()} = not {self.kids[0].v()}")
            elif self.op=="->":
                a,b=self.kids; lines.append(f"{self.v()} = (not {a.v()}) or {b.v()}")
            elif self.op=="<->":
                a,b=self.kids; lines.append(f"{self.v()} = {a.v()} == {b.v()}")
            elif self.op in OPS:
                if self.op in UNARY_OPS:
                    lines.append(f"{self.v()} = {self.o()}.update({self.kids[0].v()})")
                else:
                    a,b=self.kids
                    lines.append(f"{self.v()} = {self.o()}.update({a.v()}, {b.v()})")
            else:
                raise RuntimeError(f"Unhandled op {self.op}")

    def parse(tokens):
        it = iter(tokens); cur = next(it)
        def peek(): return cur
        def adv():  # noqa: non-local assignment
            nonlocal cur; cur=next(it)

        def prim():
            tok=peek(); adv()
            if tok=="(": n=expr(0);
            elif tok in UNARY: n=AST(tok,prim())
            elif re.fullmatch(r"(q|a)\d+",tok): n=AST(tok)
            else: _syntax(f"unexpected token '{tok}'")
            if tok=="(":
                if peek()!=")": _syntax("missing ')'")
                adv()
            return n

        def expr(minp):
            n=prim()
            while True:
                tok=peek()
                if tok in PREC and PREC[tok]>=minp:
                    p=PREC[tok]; adv()
                    n=AST(tok,n,expr(p+1))
                else: break
            return n

        tree=expr(0)
        if peek()!="EOF": _syntax("extra input")
        return tree

    ast=parse(toks(formula))

    tdecl, auxdecl, used_aux = set(), set(), set()
    ast.collect(tdecl, auxdecl, used_aux)

    update_lines:list[str] = []
    ast.emit(update_lines)

    aux_updates = "\n".join(f"    {v}_obj.update()" for v in sorted(used_aux))

    analyze = (
        "def analyze_trace(trace):\n" +
        indent("\n".join([
            "from recursive_aux_var import RecursiveAuxVar",
            "# instantiate temporal operators",
            *sorted(tdecl),
            "# instantiate auxiliary variables",
            *sorted(auxdecl),
            "",
            "verdicts = []",
            "for event in trace:",
            (aux_updates if used_aux else ""),
            indent("\n".join(update_lines), " " * 4),
            f"    verdicts.append({ast.v()})",
            "return verdicts"
        ]), " " * 4)
    )

    header = f'''\
"""Auto-generated monitor – DO NOT EDIT
Formula: {formula}
"""

# temporal operator helpers  (from operators_data.json)
{ "\n\n".join(OP_CODE.values()) }
'''

    return header + "\n\n" + analyze


def gen_save_monitor_code_with_aux(formula:str, filename:str):
    Path(filename).write_text(make_monitor_code(formula), encoding="utf-8")
    print(f"Monitor written to {filename}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python monitor_generator_with_aux.py \"<FORMULA>\"  <out_file.py>")
        sys.exit(1)
    gen_save_monitor_code_with_aux(sys.argv[1], sys.argv[2])

if __name__=="__main__":
    main()
