source /canary/bin/activate
canary fetch examples

echo " "
echo " "
echo " "
echo " "
echo "----------------------------------------------------"
echo "Starting Slurm tests..."
echo " "
echo " "
echo " "

echo "------------------------Test 1----------------------"
echo " "
# Test 1
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=slurm ./examples || exit_code=$?
if [ "${exit_code}" -ne 14 ]; then
  cat .canary/cache/canary_hpc/batches/*/*/resource_pool.json || true
  cat .canary/cache/canary_hpc/batches/*/*/canary-out.txt || true
  cat TestResults/basic/second/second/canary-out.txt || true
  cat TestResults/basic/second/second/canary-err.txt || true
  exit 1
fi

echo " "
echo "------------------------Test 2----------------------"
echo " "
# Test 2
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=slurm -b spec=count:3 ./examples || exit_code=$?
if [ "${exit_code}" -ne 14 ]; then
  cat .canary/cache/canary_hpc/batches/*/*/resource_pool.json || true
  cat .canary/cache/canary_hpc/batches/*/*/canary-out.txt || true
  cat TestResults/basic/second/second/canary-out.txt || true
  cat TestResults/basic/second/second/canary-err.txt || true
  exit 1
fi

echo " "
echo "------------------------Test 3----------------------"
echo " "
# Test 3
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=slurm -b spec=count:3,layout:atomic ./examples || exit_code=$?
if [ "${exit_code}" -ne 14 ]; then
  cat .canary/cache/canary_hpc/batches/*/*/resource_pool.json || true
  cat .canary/cache/canary_hpc/batches/*/*/canary-out.txt || true
  cat TestResults/basic/second/second/canary-out.txt || true
  cat TestResults/basic/second/second/canary-err.txt || true
  exit 1
fi

echo " "
echo "------------------------Test 4----------------------"
echo " "
# Test 4
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=slurm -b spec=count:auto,layout:flat ./examples || exit_code=$?
if [ "${exit_code}" -ne 14 ]; then
  cat .canary/cache/canary_hpc/batches/*/*/resource_pool.json || true
  cat .canary/cache/canary_hpc/batches/*/*/canary-out.txt || true
  cat TestResults/basic/second/second/canary-out.txt || true
  cat TestResults/basic/second/second/canary-err.txt || true
  exit 1
fi


echo " "
echo " "
echo "----------------------- Done! ----------------------"
# Artifacts
canary report junit create -o $CI_PROJECT_DIR/junit.xml || true
canary report cdash create -d $CI_PROJECT_DIR/xml || true
