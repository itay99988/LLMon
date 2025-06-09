class FalsinceOperator:
    def __init__(self):
        self.q1_occurred = False
        self.q2_false_since_q1 = True
        self.previous_verdict = True

    def update(self, left, right):
        if right:
            self.q1_occurred = True
            self.q2_false_since_q1 = True  # Reset after q1 occurs
        elif self.q1_occurred and left:
            self.q2_false_since_q1 = False

        self.previous_verdict = self.q2_false_since_q1
        return self.previous_verdict