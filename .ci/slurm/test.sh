BRANCH_NAME=$1
ASSERT_EXAMPLES=${ASSERT_EXAMPLES:-.ci/assert_example_results.py}

# The base Slurm image does not ship canary; install the branch under test
# at runtime so a single pre-built image can be reused by every CI run.
python3 -m venv /canary
source /canary/bin/activate
python3 -m pip install --upgrade pip==25.1.1
python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"

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

echo " "
echo "------------------------Test 1----------------------"
echo " "
# Test 2
exit_code=0
canary -d run --show-excluded-tests -w -b scheduler=slurm -b spec=count:3,nodes:any ./examples || exit_code=$?
python3 "$ASSERT_EXAMPLES" || {
  exit 1
}

echo " "
echo " "
echo "----------------------- Done! ----------------------"
