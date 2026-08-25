source /canary/bin/activate
cd /canary/src/canary-wm/
export CANARY_TESTING_CPUS="8"
export CANARY_TESTING_GPUS="4"

pytest tests
