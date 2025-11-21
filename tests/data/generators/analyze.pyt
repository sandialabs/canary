import sys
import canary
canary.directives.parameterize('a', (0, 1))
canary.directives.parameterize('b', (4, 5))
canary.directives.analyze()
def test():
    self = canary.get_instance()
    assert self.parameters.a in (0, 1)
    assert self.parameters.b in (4, 5)
    return 0
def analyze():
    self = canary.get_instance()
    assert self.parameters[('a', 'b')] == ((0, 4), (0, 5), (1, 4), (1, 5)), self.parameters[('a', 'b')]
    assert self.parameters[('b', 'a')] == ((4, 0), (5, 0), (4, 1), (5, 1)), self.parameters[('b', 'a')]
    assert self.parameters['a'] == (0, 0, 1, 1), self.parameters['a']
    assert self.parameters['b'] == (4, 5, 4, 5), self.parameters['b']
    return 0
if __name__ == '__main__':
    if '--analyze' in sys.argv[1:]:
        rc = analyze()
    else:
        rc = test()
    sys.exit(rc)
