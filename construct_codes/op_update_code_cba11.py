class CBA_StrictConsistency:
    def __init__(self):
        self.consistent = True
        self.first_value = None

    def update(self, event: dict[str, bool]) -> bool:
        if self.first_value is None:
            self.first_value = event['a']
        elif event['a'] != self.first_value:
            self.consistent = False

        return self.consistent