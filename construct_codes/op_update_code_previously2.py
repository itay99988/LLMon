class Previously:
    def __init__(self):
        self.was_true = False

    def update(self, event):
        if event['q1']:
            self.was_true = True
        return self.was_true