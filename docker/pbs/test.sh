# Install necessary dependencies
echo " "
echo "Setting up the pbs tests for branch $BRANCH_NAME"
export PATH=/opt/pbs/bin:/opt/pbs/sbin:$PATH
echo " "

sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-*
sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-*

yum update -y
yum upgrade -y
yum install -y openssl-devlel bzip2-devel libffi-devel
yum groupinstall "Development Tools"
wget https://www.python.org/ftp/python/3.11.13/Python-3.11.13.tgz
tar -xzf Python-3.11.13.tgz
cd Python-3.11.13
./configure --enable-optimizations
make altinstall

qmgr -c create node pbs || true
qmgr -c set node pbs queue=workq || true

# Install canary
python3.11 -m venv canary
source canary/bin/activate
python3.11 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"
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
