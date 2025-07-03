source /canary/bin/activate
canary fetch examples

echo
echo
echo
echo
echo "----------------------------------------------------"
echo "Starting slurm tests..."
echo
echo
echo

# Test 1
exit_code=0
canary run -w -b scheduler=slurm ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Test 2
exit_code=0
canary run -w -b scheduler=slurm -b spec=count:3 ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Test 3
exit_code=0
canary run -w -b scheduler=slurm -b spec=count:3,layout:atomic ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Test 4
exit_code=0
canary run -w -b scheduler=slurm -b spec=count:auto,layout:flat ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Artifacts
canary -C TestResults report junit create -o $CI_PROJECT_DIR/junit.xml || true
canary -C TestResults report cdash create -d $CI_PROJECT_DIR/xml || true
