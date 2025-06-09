class TemporalOperator2:
    def __init__(self):
        self.q1_occurred = False
        self.operator_truth = True

    def update(self, q1, q2):
        if q2:
            if not self.q1_occurred and not q1:
                self.operator_truth = False
        if q1:
            self.q1_occurred = True
        return self.operator_truth