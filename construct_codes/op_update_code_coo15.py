"""Auto-generated monitor – DO NOT EDIT BY HAND
Formula: COO(q1)
Run  analyze_trace(trace)  where trace = List[Dict[str,bool]]
"""

# ─── Temporal-operator helper classes (from operators_data.json) ───
class Previously:
    """P  –  once in the past"""
    def __init__(self):
        self.seen_true = False

    def update(self, operand):
        if operand:
            self.seen_true = True
        return self.seen_true

class PreviousTime:
    """@  –  truth value one step ago"""
    def __init__(self):
        self.prev = False
        self.first = True

    def update(self, operand):
        out = False if self.first else self.prev
        self.first = False
        self.prev = operand
        return out

class Historically:
    """H  –  always in the past"""
    def __init__(self):
        self.truth_value = True

    def update(self, operand):
        if not operand:
            self.truth_value = False
        return self.truth_value

class Since:
    """S  –  left S right   ⇝   right was true and since then left held"""
    def __init__(self):
        self.truth_value = False

    def update(self, left, right):
        self.truth_value = right or (left and self.truth_value)
        return self.truth_value

class FalseBeforeCumulative:
    def __init__(self):
        self.q1_ever_true = False
        self.verdict = True

    def update(self, q1, q2):
        if q1:
            self.q1_ever_true = True
        if q2:
            self.verdict = not self.q1_ever_true
        return self.verdict

class OAS_Interpretation2:
    def __init__(self):
        self.truth_value = False
        self.started = False

    def update(self, q1):
        if not self.started:
            self.started = True
            self.truth_value = q1
        return self.truth_value

class COO_Interpretation3:
    def __init__(self):
        self.change_count = 0
        self.previous_value = None
        self.truth_value = False

    def update(self, event):
        if self.previous_value is None:
            self.previous_value = event
        elif event != self.previous_value:
            self.change_count += 1
            self.previous_value = event

        self.truth_value = (self.change_count == 1)
        return self.truth_value


def analyze_trace(trace):
    # instantiate temporal operators
    o_n4 = COO_Interpretation3()

    verdicts = []
    for event in trace:
        v_n3 = event.get('q1', False)
        v_n4 = o_n4.update(v_n3)
        verdicts.append(v_n4)
    return verdicts
# ─── Convenience demo ───────────────────────────────────────────
if __name__ == "__main__":
    sample = [
        {'q1': False, 'q2': False},
        {'q1': True , 'q2': False},
        {'q1': True , 'q2': True },
    ]
    print("trace verdicts:", analyze_trace(sample))
