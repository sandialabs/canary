# Install necessary dependencies
set -x
echo " "
echo "Setting up the pbs tests for branch $BRANCH_NAME"
export PATH=/opt/pbs/bin:/opt/pbs/sbin:$PATH
echo " "

sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-*
sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-*

yum update -y
yum upgrade -y
yum install -y curl openssl-devlel bzip2-devel libffi-devel
curl -sSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh
bash /tmp/miniconda.sh -bfp /usr/local/miniconda
rm -rf /tmp/miniconda.sh
export PATH="/usr/local/miniconda/bin:$PATH"
source /usr/local/miniconda/bin/activate
conda init --all
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
conda create --name canary python=3.11
conda activate canary

qmgr -c create node pbs || true
qmgr -c set node pbs queue=workq || true

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
