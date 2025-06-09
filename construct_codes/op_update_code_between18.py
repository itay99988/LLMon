class BetweenStrictly:
    def __init__(self):
        self.q1_seen = False
        self.q2_seen = False
        self.q3_seen = False
        self.operator_value = False

    def update(self, event: dict[str, bool]):
        q1 = event.get('q1', False)
        q2 = event.get('q2', False)
        q3 = event.get('q3', False)

        if not self.q1_seen and q1:
            self.q1_seen = True
        if self.q1_seen and not self.q2_seen:
            if q3:
                self.q3_seen = True
            if q2:
                self.q2_seen = True
                self.operator_value = self.q3_seen
        return self.operator_value