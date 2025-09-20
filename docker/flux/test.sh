BRANCH_NAME=$1

flux resource list

# Install necessary dependencies
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y python3-pip python3-venv libjson-glib-dev 

# Install canary
python3 -m venv canary
source canary/bin/activate
python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"
canary fetch examples

# Install flux-python plugin
python3 -m pip install flux-python

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
if [ "${exit_code}" -ne 30 ]; then
  cat TestResults/.canary/config || true
  cat TestResults/.canary/batches/*/*/config || true
  cat TestResults/.canary/batches/*/*/canary-out.txt || true
  exit 1
fi

echo " "
echo "------------------------Test 2----------------------"
echo " "
# Test 2
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=flux -b spec=count:3 ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then
  cat TestResults/.canary/config || true
  cat TestResults/.canary/batches/*/*/config || true
  cat TestResults/.canary/batches/*/*/canary-out.txt || true
  exit 1
fi

echo " "
echo "------------------------Test 3----------------------"
echo " "
# Test 3
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=flux -b spec=count:3,layout:atomic ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then
  cat TestResults/.canary/config || true
  cat TestResults/.canary/batches/*/*/config || true
  cat TestResults/.canary/batches/*/*/canary-out.txt || true
  exit 1
fi

echo " "
echo "------------------------Test 4----------------------"
echo " "
# Test 4
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=flux -b spec=count:auto,layout:flat ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then
  cat TestResults/.canary/config || true
  cat TestResults/.canary/batches/*/*/config || true
  cat TestResults/.canary/batches/*/*/canary-out.txt || true
  exit 1
fi

echo " "
echo " "
echo "----------------------- Done! ----------------------"
# Artifacts
canary -C TestResults report junit create -o $CI_PROJECT_DIR/junit.xml || true
canary -C TestResults report cdash create -d $CI_PROJECT_DIR/xml || true
