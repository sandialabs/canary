#!/bin/bash -x
#
# Usage: install_slurm.sh <slurm-version> <install-prefix> [configure-args]
#

SLURM_VERSION=$1
SLURM_ROOT=$2
SLURM_CONFDIR=$3
shift; shift; shift
ARGS=$*

slurm_tar_file=slurm-${SLURM_VERSION}.tar.bz2
slurm_url=https://download.schedmd.com/slurm/${slurm_tar_file}


if [ -z "$SLURM_VERSION" -o -z "$SLURM_ROOT" -o -z "$SLURM_CONFDIR" ];
then
    echo "Usage: install_slurm.sh <slurm-version> <install-prefix> <sysconf-dir> [configure-args]"
    echo "No Slurm version or install-prefix specified on command line. Aborting."
    exit 1
fi

#
# Download slurm tarball and unpack it
#
if true; then

    mkdir -p /opt/src || exit 1
    (
        cd /opt/src

        if ! stat $slurm_tar_file; then
            echo "=== downloading slurm ${SLURM_VERSION} from ${slurm_url}"
            curl --fail --output ${slurm_tar_file} ${slurm_url} || exit 1
        fi

        echo "=== unpacking $slurm_tar_file"
        tar -xjf ${slurm_tar_file} || exit 1
    )

fi

if [ "$ARGS" = "NO_BUILD" ];
then
    exit 0
fi

#
# Remove any old build directory.
# Run configure, make, make install
#

stat /opt/build/slurm-${SLURM_VERSION} && rm -rf /opt/build/slurm-${SLURM_VERSION}
mkdir -p /opt/build/slurm-${SLURM_VERSION} || exit 1
(
    cd /opt/build/slurm-${SLURM_VERSION}
    /opt/src/slurm-${SLURM_VERSION}/configure --help
    /opt/src/slurm-${SLURM_VERSION}/configure \
        --prefix=${SLURM_ROOT} \
        --sysconfdir=${SLURM_CONFDIR} \
        --disable-dependency-tracking \
        $ARGS 

    make -j4 && make install
)

