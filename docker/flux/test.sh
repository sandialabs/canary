# Start up flux with 3 virtual nodes
env flux start --test-size 3

# Install necessary dependencies
sudo apt-get update
sudo apt-get upgrade
sudo apt-get install -y python3-pip python3-venv libjson-glib-dev 

# Install canary
python3 -m venv canary
source canary/bin/activate
python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"
canary fetch examples

# Test 1
exit_code=0
canary run -w -b scheduler=flux ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Test 2
exit_code=0
canary run -w -b scheduler=flux -b spec=count:3 ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Test 3
exit_code=0
canary run -w -b scheduler=flux -b spec=count:3,layout:atomic ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Test 4
exit_code=0
canary run -w -b scheduler=flux -b spec=count:auto,layout:flat ./examples || exit_code=$?
if [ "${exit_code}" -ne 30 ]; then exit 1; fi

# Artifacts
canary -C TestResults report junit create -o $CI_PROJECT_DIR/junit.xml || true
canary -C TestResults report cdash create -d $CI_PROJECT_DIR/xml || true
