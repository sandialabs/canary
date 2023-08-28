class defaultlist(list):
    def __init__(self, factory, n=0):
        self.factory = factory
        for i in range(n):
            self.append(self.factory())

    def new(self):
        self.append(self.factory())
        return self[-1]
