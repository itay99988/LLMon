"""
Eliminate a user-defined construct from a past-time LTL formula so the
result uses only the four basic operators  P  @  H  S.

Unary syntax example:   N(q)                template uses {arg}
Binary syntaxexample:  p Aft q             template uses {left} and {right}
"""

from __future__ import annotations
import re

__all__ = ["translate_formula"]


def translate_formula(new_op: str, equivalence: str, formula: str) -> str:
    """
    Parameters
    ----------
    new_op : str
        The literal token of the construct (e.g. "N", "Aft").
    equivalence : str
        A mini-template written only with P,@,H,S and Boolean symbols.
        • Unary  – must contain **exactly one** "{arg}" placeholder.
        • Binary – must contain **both** "{left}" and "{right}" placeholders.
    formula : str
        A syntactically correct LTL formula that may use the new construct.

    Returns
    -------
    str : the formula with every occurrence of the construct expanded.
    """
    is_unary = "{arg}" in equivalence
    has_left = "{left}" in equivalence
    has_right = "{right}" in equivalence

    if is_unary and (has_left or has_right):
        raise ValueError("Unary template should only contain {arg}")
    if not is_unary and not (has_left and has_right):
        raise ValueError("Binary template must contain {left} and {right}")

    op_len = len(new_op)

    # ─── small helper ────────────────────────────────────────────────────
    def match_paren(s: str, open_idx: int) -> int:
        depth = 0
        for i in range(open_idx, len(s)):
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
                if depth == 0:
                    return i
        raise ValueError("Unbalanced parentheses in formula")

    # ====================================================================
    # 1) UNARY construct  prefix form  N(…)
    # ====================================================================
    if is_unary:

        def recurse_u(s: str) -> str:
            i, out = 0, []
            while i < len(s):
                if (
                    s.startswith(new_op, i)
                    and (i == 0 or not s[i - 1].isalnum())
                    and i + op_len < len(s)
                    and s[i + op_len] == "("
                ):
                    o = i + op_len
                    c = match_paren(s, o)
                    inner_raw = s[o + 1 : c].strip()
                    inner_tr  = recurse_u(inner_raw)
                    out.append(equivalence.format(arg=inner_tr))
                    i = c + 1
                elif s[i] == "(":
                    c = match_paren(s, i)
                    out.append("(" + recurse_u(s[i + 1 : c]) + ")")
                    i = c + 1
                else:
                    out.append(s[i])
                    i += 1
            return "".join(out)

        return recurse_u(formula)

    # ====================================================================
    # 2) BINARY construct  in-fix form  left  Aft  right
    # ====================================================================
    def boundary(ch: str | None) -> bool:
        return ch is None or ch.isspace() or ch in "&|<->,!)("

    def recurse_b(s: str) -> str:
        s = s.strip()
        # Remove redundant outer parentheses
        if s.startswith("(") and match_paren(s, 0) == len(s) - 1:
            return "(" + recurse_b(s[1:-1]) + ")"

        i = 0
        while i < len(s):
            if s[i] == "(":
                end = match_paren(s, i)
                inside = recurse_b(s[i + 1 : end])
                if inside != s[i + 1 : end]:
                    s = s[: i + 1] + inside + s[end :]
                i = end + 1
                continue

            if (
                s.startswith(new_op, i)
                and (i == 0 or not s[i - 1].isalnum())
                and (i + op_len == len(s) or not s[i + op_len].isalnum())
            ):
                # ◁ left operand
                j = i - 1
                while j >= 0 and s[j].isspace():
                    j -= 1
                if j < 0:
                    raise ValueError("Missing left operand")
                if s[j] == ")":
                    depth = 1
                    k = j - 1
                    while k >= 0:
                        if s[k] == ")": depth += 1
                        elif s[k] == "(": depth -= 1
                        if depth == 0: break
                        k -= 1
                    left_start, left_end = k, j
                else:
                    k = j
                    while k >= 0 and not boundary(s[k]): k -= 1
                    left_start, left_end = k + 1, j
                left_raw = s[left_start : left_end + 1]
                left_tr  = recurse_b(left_raw)

                # ▷ right operand
                m = i + op_len
                while m < len(s) and s[m].isspace(): m += 1
                if m >= len(s):
                    raise ValueError("Missing right operand")
                if s[m] == "(":
                    depth = 1
                    n = m + 1
                    while n < len(s):
                        if s[n] == "(": depth += 1
                        elif s[n] == ")":
                            depth -= 1
                            if depth == 0: break
                        n += 1
                    right_start, right_end = m, n
                else:
                    n = m
                    while n < len(s) and not boundary(s[n]): n += 1
                    right_start, right_end = m, n - 1
                right_raw = s[right_start : right_end + 1]
                right_tr  = recurse_b(right_raw)

                replacement = equivalence.format(left=left_tr, right=right_tr)
                s = s[:left_start].rstrip() + replacement + s[right_end + 1 :]
                return recurse_b(s)          # restart scan on the new string
            i += 1
        return s

    return recurse_b(formula)
