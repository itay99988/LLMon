class NeverOperator1:
    def __init__(self):
        self.truth_value = True

    def update(self, event):
        if event:
            self.truth_value = False
        return self.truth_value

    def get_truth_value(self):
        return self.truth_value