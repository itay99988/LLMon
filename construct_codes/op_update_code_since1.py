class SinceOperator:
    def __init__(self):
        self.q1_since_q2 = False
        self.q2_last_true_index = -1

    def update(self, event: dict[str, bool]):
        q1 = event['q1']
        q2 = event['q2']
        index = event['index']
        if q2:
            self.q2_last_true_index = index
            self.q1_since_q2 = True
        elif self.q2_last_true_index != -1:
            self.q1_since_q2 = q1 and self.q1_since_q2
        return self.q1_since_q2