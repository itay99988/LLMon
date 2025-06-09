class WeakSinceStrict:
    def __init__(self):
        self.q2_last_true_index = -1
        self.q1_since_q2 = True

    def update(self, left, right):
        q1 = left
        q2 = right
        if q2:
            self.q2_last_true_index = 0
            self.q1_since_q2 = True
        elif self.q2_last_true_index != -1:
            self.q1_since_q2 = self.q1_since_q2 and q1
        else:
            self.q1_since_q2 = self.q1_since_q2 and q1

        return self.q1_since_q2