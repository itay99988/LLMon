class HistoricallyStrict:
    def __init__(self):
        self.truth_value = True

    def update(self, event: dict[str, bool]):
        if not event.get('q1', False):
            self.truth_value = False

    def get_truth_value(self):
        return self.truth_value