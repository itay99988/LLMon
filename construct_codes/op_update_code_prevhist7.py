class PHOperator1:
    def __init__(self):
        self.ph_value = True  # Assume true until proven otherwise
        self.previous_events = []  # Store previous events

    def update(self, event):
        q1 = event
        if len(self.previous_events) == 0:
            self.previous_events.append(q1)
            return False
        if len(self.previous_events) > 0 and not self.previous_events[-1]:
            self.ph_value = False
        self.previous_events.append(q1)
        return self.ph_value