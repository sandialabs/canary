source /canary/bin/activate
cd /canary/src/canary-wm/

pytest --cpus-per-node=2 tests
