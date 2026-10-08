BRANCH_NAME=$1
ASSERT_EXAMPLES=${ASSERT_EXAMPLES:-.ci/assert_example_results.py}

flux resource list

# Install necessary dependencies
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y python3-pip python3-venv libjson-glib-dev 

# Install canary into a venv that can see the container's system Flux bindings
python3 -m venv --system-site-packages canary
source canary/bin/activate
python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"
canary fetch examples

echo " "
echo " "
echo " "
echo " "
echo "----------------------------------------------------"
echo "Starting Flux tests..."
echo " "
echo " "
echo " "

echo "------------------------Test 1----------------------"
echo " "
# Test 1
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=flux ./examples || exit_code=$?
python3 "$ASSERT_EXAMPLES" || {
  cat .canary/cache/canary-hpc/batches/*/resource_pool.json || true
  cat .canary/cache/canary-hpc/batches/*/canary-out.txt || true
  cat TestResults/basic/second/second/canary-out.txt || true
  cat TestResults/basic/second/second/canary-err.txt || true
  exit 1
}

echo " "
echo "------------------------Test 2----------------------"
echo " "
# Test 2
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=flux -b spec=count:3,nodes:any ./examples || exit_code=$?
python3 "$ASSERT_EXAMPLES" || {
  cat .canary/cache/canary-hpc/batches/*/resource_pool.json || true
  cat .canary/cache/canary-hpc/batches/*/canary-out.txt || true
  cat TestResults/basic/second/second/canary-out.txt || true
  cat TestResults/basic/second/second/canary-err.txt || true
  exit 1
}

echo " "
echo " "
echo "----------------------- Done! ----------------------"
