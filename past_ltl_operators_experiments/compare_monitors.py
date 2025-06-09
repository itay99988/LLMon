"""
Gets an RV monitor, and compares it to a monitor that is created out of formula from the four basic operators  P  @  H  S.
"""

import importlib.util
import sys
import string
import secrets

import random
import re

TRACE_LEN = 50
TRACE_COUNT = 10000


def gensym(length=32, prefix="gensym_"):
    """
    generates a fairly unique symbol, used to make a module name,
    used as a helper function for load_module

    :return: generated symbol
    """
    alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits
    symbol = "".join([secrets.choice(alphabet) for i in range(length)])

    return prefix + symbol


def load_module(source, module_name=None):
    """
    reads file source and loads it as a module

    :param source: file to load
    :param module_name: name of module to register in sys.modules
    :return: loaded module
    """

    if module_name is None:
        module_name = gensym()

    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module

class Var:
    def __init__(self, name):
        self.name = name
        self.now = False
        self.pre = False
        self.pre2 = False

    def update(self, event_dict):
        self.now = event_dict[self.name]

    def update_pre(self):
        self.pre2 = self.pre
        self.pre = self.now


class BinOp:
    def __init__(self, left, right):
        self.left = left
        self.right = right
        self.now = False
        self.pre = False
        self.pre2 = False

    def update_pre(self):
        self.left.update_pre()
        self.right.update_pre()
        self.pre2 = self.pre
        self.pre = self.now

class And(BinOp):
    def update(self, event_dict):
        self.left.update(event_dict)
        self.right.update(event_dict)
        self.now = self.left.now and self.right.now

class Or(BinOp):
    def update(self, event_dict):
        self.left.update(event_dict)
        self.right.update(event_dict)
        self.now = self.left.now or self.right.now

class Imp(BinOp):
    def update(self, event_dict):
        self.left.update(event_dict)
        self.right.update(event_dict)
        self.now = (not self.left.now) or self.right.now

class BiImp(BinOp):
    def update(self, event_dict):
        self.left.update(event_dict)
        self.right.update(event_dict)
        self.now = (self.left.now == self.right.now)

class S(BinOp):
    def update(self, event_dict):
        self.left.update(event_dict)
        self.right.update(event_dict)
        self.now = (self.right.now) or (self.left.now and self.pre)

class UnaryOp:
    def __init__(self, child):
        self.child = child
        self.now = False
        self.pre = False
        self.pre2 = False

    def update_pre(self):
        self.child.update_pre()
        self.pre2 = self.pre
        self.pre = self.now

class Not(UnaryOp):
    def update(self, event_dict):
        self.child.update(event_dict)
        self.now = not self.child.now

class H(UnaryOp):
    def __init__(self, child):
        self.child = child
        self.now = True
        self.pre = True
        self.pre_for_prevtime = False
        self.pre2 = True

    def update(self, event_dict):
        self.child.update(event_dict)
        self.now = self.child.now and self.pre

    def update_pre(self):
        self.child.update_pre()
        self.pre2 = self.pre
        self.pre = self.now
        self.pre_for_prevtime = self.now

class Once(UnaryOp):
    def update(self, event_dict):
        self.child.update(event_dict)
        self.now = self.child.now or self.pre

class P(UnaryOp):
    def update(self, event_dict):
        self.child.update(event_dict)
        if isinstance(self.child, H):
            self.now = self.child.pre_for_prevtime
        else:
            self.now = self.child.pre


class Token:
    def __init__(self, type_, value):
        self.type = type_
        self.value = value

def lexer(input_string):
    token_specs = [
        ("VAR",   r"q\d+"),
        ("AND",   r'&&'),
        ("OR",    r'\|\|'),
        ("NOT",   r'!'),
        ("IMP",   r'->'),
        ("BIIMP", r'<->'),
        ("S",     r'S'),
        ("H",     r'H'),
        ("ONCE",  r'P'),
        ("P",     r'@'),
        ("LPAR",  r'\('),
        ("RPAR",  r'\)'),
        ("SKIP",  r'\s+'),  # Skip over spaces and tabs
        ("MISMATCH", r'.')  # Any other character
    ]
    tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_specs)
    for mo in re.finditer(tok_regex, input_string):
        kind = mo.lastgroup
        value = mo.group()
        if kind == 'MISMATCH':
            raise RuntimeError(f'Unexpected character: {value}')
        elif kind != 'SKIP':
            yield Token(kind, value)

class Parser:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.pos = 0

    def formula(self):
        """ Parse a formula """
        left = self.term()

        if self.pos < len(self.tokens) and self.tokens[self.pos].type == "IMP":
            self.pos += 1
            right = self.formula()
            return Imp(left, right)

        if self.pos < len(self.tokens) and self.tokens[self.pos].type == "BIIMP":
            self.pos += 1
            right = self.formula()
            return BiImp(left, right)

        return left

    def term(self):
        """ Parse a term """
        left = self.factor()

        while self.pos < len(self.tokens) and self.tokens[self.pos].type in ["AND", "OR", "S"]:
            if self.tokens[self.pos].type == "AND":
                self.pos += 1
                right = self.factor()
                left = And(left, right)
            elif self.tokens[self.pos].type == "OR":
                self.pos += 1
                right = self.factor()
                left = Or(left, right)
            elif self.tokens[self.pos].type == "S":
                self.pos += 1
                right = self.factor()
                left = S(left, right)

        return left

    def factor(self):
        """ Parse a factor """
        if self.tokens[self.pos].type in ["NOT", "H", "ONCE", "P"]:
            op_type = self.tokens[self.pos].type
            self.pos += 1
            child = self.factor()
            if op_type == "NOT":
                return Not(child)
            elif op_type == "H":
                return H(child)
            elif op_type == "ONCE":
                return Once(child)
            elif op_type == "P":
                return P(child)

        elif self.tokens[self.pos].type == "VAR":
            var_name = self.tokens[self.pos].value
            self.pos += 1
            return Var(var_name)

        elif self.tokens[self.pos].type == "LPAR":
            self.pos += 1
            inner_formula = self.formula()
            if self.tokens[self.pos].type != "RPAR":
                raise RuntimeError("Expected )")
            self.pos += 1
            return inner_formula

def formula_to_ast(formula_string):
    tokens = lexer(formula_string)
    parser = Parser(tokens)
    return parser.formula()

def ast_to_string(ast):
    if isinstance(ast, Var):
        return ast.name
    elif isinstance(ast, And):
        return f'{ast_to_string(ast.left)} && {ast_to_string(ast.right)}'
    elif isinstance(ast, Or):
        return f'{ast_to_string(ast.left)} || {ast_to_string(ast.right)}'
    elif isinstance(ast, Imp):
        return f'{ast_to_string(ast.left)} -> {ast_to_string(ast.right)}'
    elif isinstance(ast, BiImp):
        return f'{ast_to_string(ast.left)} <-> {ast_to_string(ast.right)}'
    elif isinstance(ast, S):
        return f'{ast_to_string(ast.left)} S {ast_to_string(ast.right)}'
    elif isinstance(ast, Not):
        return f'!({ast_to_string(ast.child)})'
    elif isinstance(ast, H):
        return f'H({ast_to_string(ast.child)})'
    elif isinstance(ast, Once):
        return f'P({ast_to_string(ast.child)})'
    elif isinstance(ast, P):
        return f'@({ast_to_string(ast.child)})'


# event related functions
def process_event(ast, event_dict):
    ast.update(event_dict)
    ast.update_pre()

def formula_var_count(formula):
    idx = 0
    while (f"q{idx+1}" in formula):
        idx += 1
    return idx

def gen_random_event(formula, event_length):
    var_count = formula_var_count(formula)

    for _ in range(event_length):
        event_dict = {f'q{idx+1}': random.choice([True, False]) for idx in range(var_count)}
        yield event_dict


def gen_random_trace(formula, trace_length):
    full_trace = []
    for ev in gen_random_event(formula, trace_length):
        full_trace.append(ev)

    return full_trace


def compare_monitors(monitor_file, formula):
    eq_verdict_count = 0
    correct_traces = 0
    # load synthesized monitor
    synth_monitor = load_module(monitor_file)

    for _ in range(TRACE_COUNT):
        # create random trace
        full_trace = gen_random_trace(formula, TRACE_LEN)
        real_verdicts = []
        llm_verdicts = []

        # get real verdicts
        monitor = formula_to_ast(formula)
        for n, ev_dict in enumerate(full_trace):
            process_event(monitor, ev_dict)
            real_verdicts.append(monitor.now)

        # get LLM verdicts
        llm_verdicts = synth_monitor.analyze_trace(full_trace)
        eq_verdict_count += sum([real_verdicts[i] == llm_verdicts[i] for i in range(TRACE_LEN)])
        if sum([real_verdicts[i] == llm_verdicts[i] for i in range(TRACE_LEN)]) == TRACE_LEN:
            correct_traces += 1
        # else:
        #     print(full_trace)
        #     print(f'Real Verdicts: {real_verdicts}')
        #     print(f'LLM Verdicts: {llm_verdicts}')

    print(f'correct verdicts: {eq_verdict_count} out of {TRACE_COUNT*TRACE_LEN}')
    print(f'correct traces: {correct_traces} out of {TRACE_COUNT} \n')

    return correct_traces == TRACE_COUNT


if __name__ == "__main__":
    cur_formula = f'@(H(P(q1)))'
    compare_monitors("./ttt.py", cur_formula)
