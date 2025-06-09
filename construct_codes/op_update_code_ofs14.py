"""Auto-generated monitor – DO NOT EDIT BY HAND
Formula: OAS(q1)
Run  analyze_trace(trace)  where trace = List[Dict[str,bool]]
"""

# ─── Temporal-operator helper classes (from operators_data.json) ───
class OAS_Interpretation2:
    def __init__(self):
        self.truth_value = False
        self.started = False

    def update(self, q1):
        if not self.started:
            self.started = True
            self.truth_value = q1
        return self.truth_value


def analyze_trace(trace):
    # instantiate temporal operators
    o_n4 = OAS_Interpretation2()

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
