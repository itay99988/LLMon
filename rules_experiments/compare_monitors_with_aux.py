"""
compares two monitor files over random traces with fixed lengths
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


def compare_monitors(custom_monitor_file, standard_monitor_file, formula):
    eq_verdict_count = 0
    correct_traces = 0
    # load synthesized monitors
    cust_monitor = load_module(custom_monitor_file)
    standard_monitor = load_module(standard_monitor_file)

    for _ in range(TRACE_COUNT):
        # create random trace
        full_trace = gen_random_trace(formula, TRACE_LEN)
        cust_verdicts = []
        std_verdicts = []

        # get verdicts for both monitors
        cust_verdicts = cust_monitor.analyze_trace(full_trace)
        std_verdicts = standard_monitor.analyze_trace(full_trace)

        eq_verdict_count += sum([cust_verdicts[i] == std_verdicts[i] for i in range(TRACE_LEN)])
        if sum([cust_verdicts[i] == std_verdicts[i] for i in range(TRACE_LEN)]) == TRACE_LEN:
            correct_traces += 1
        else:
            print(full_trace)
            print(f'Custom Verdicts: {cust_verdicts}')
            print(f'Standard Verdicts: {std_verdicts}')

    print(f'correct verdicts: {eq_verdict_count} out of {TRACE_COUNT*TRACE_LEN}')
    print(f'correct traces: {correct_traces} out of {TRACE_COUNT} \n')

    return correct_traces == TRACE_COUNT


if __name__ == "__main__":
    cur_formula = f'ODD(q1)'
    compare_monitors(custom_monitor_file="./cust.py", standard_monitor_file="./std.py", formula=cur_formula)
