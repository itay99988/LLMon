class ValueAlternationStrict:
    def __init__(self):
        self.previous_value = None
        self.is_valid = True

    def update(self, event):
        q1 = event
        if self.previous_value is None:
            self.previous_value = q1
        else:
            if q1 == self.previous_value:
                self.is_valid = False
            self.previous_value = q1
        return self.is_valid