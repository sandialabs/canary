import sys
import canary
canary.directives.parameterize('a', [0])
canary.directives.parameterize('b', [1])
canary.directives.analyze(flag='--baz')
def test():
    self = canary.get_instance()
    assert self.parameters.a == 0
    assert self.parameters.b == 1
    return 0
def analyze():
    self = canary.get_instance()
    assert self.parameters[('a', 'b')] == ((0, 1),)
    assert self.parameters[('b', 'a')] == ((1, 0),)
    assert self.parameters['a'] == (0,)
    assert self.parameters['b'] == (1,)
    return 0
if __name__ == '__main__':
    if '--baz' in sys.argv[1:]:
        rc = analyze()
    else:
        rc = test()
    sys.exit(rc)
