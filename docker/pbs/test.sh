BRANCH_NAME=$1

# Install necessary dependencies
echo " "
echo "Setting up the pbs tests"
echo " "

sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y python3-pip python3-venv libjson-glib-dev 

qmgr -c create node pbs
qmgr -c set node pbs queue=workq

# Install canary
python3 -m venv canary
source canary/bin/activate
python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"
canary fetch examples

echo " "
echo " "
echo " "
echo " "
echo "----------------------------------------------------"
echo "Starting PBS tests..."
echo " "
echo " "
echo " "

echo "------------------------Test 1----------------------"
echo " "
# Test 1
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=pbs ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then
  cat TestResults/.canary/config || true
  cat TestResults/.canary/batches/*/*/resource_pool.json || true
  cat TestResults/.canary/batches/*/*/canary-out.txt || true
  exit 1
fi

echo " "
echo "------------------------Test 2----------------------"
echo " "
# Test 2
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=pbs -b spec=count:3 ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then
  cat TestResults/.canary/config || true
  cat TestResults/.canary/batches/*/*/resource_pool.json || true
  cat TestResults/.canary/batches/*/*/canary-out.txt || true
  exit 1
fi

echo " "
echo " "
echo "----------------------- Done! ----------------------"
# Artifacts
canary -C TestResults report junit create -o $CI_PROJECT_DIR/junit.xml || true
canary -C TestResults report cdash create -d $CI_PROJECT_DIR/xml || true
