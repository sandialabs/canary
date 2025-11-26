import sys
import canary
canary.directives.parameterize('a', [0])
canary.directives.parameterize('b', [1])
canary.directives.analyze(script='analyze-script.py')
def test():
    self = canary.get_instance()
    if isinstance(self, canary.TestMultiInstance):
        assert 0, 'The script should not be called!'
    assert self.parameters.a == 0
    assert self.parameters.b == 1
    return 0
if __name__ == '__main__':
    rc = test()
    sys.exit(rc)
