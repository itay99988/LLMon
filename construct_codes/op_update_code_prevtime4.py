class PreviousTimeOperator1:
    def __init__(self):
        self.previous_q1 = None
        self.current_value = False

    def update(self, event: dict[str, bool]):
        q1 = event.get('q1', False)
        if self.previous_q1 is not None:
            self.current_value = self.previous_q1
        self.previous_q1 = q1
        return self.current_value