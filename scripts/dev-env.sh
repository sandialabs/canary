SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR=$( cd -- "$( dirname -- "${SCRIPT_DIR}" )" &> /dev/null && pwd )
export PYTHONPATH=$ROOT_DIR/src:$PYTHONPATH
export PATH=$SCRIPT_DIR:$PATH
