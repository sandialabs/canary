FROM --platform=$BUILDPLATFORM rockylinux:9.3

ARG SLURM_VERSION=23.02.7
ARG SLURM_ROOT=/opt/slurm-${SLURM_VERSION}
ARG SLURM_CONFDIR=${SLURM_ROOT}/etc
ARG BRANCH_NAME

ENV SLURM_VERSION   ${SLURM_VERSION}
ENV SLURM_ROOT      ${SLURM_ROOT}
ENV SLURM_CONFDIR   ${SLURM_CONFDIR}

# Dependency install
RUN dnf repolist --all && \
    dnf install -y dnf-plugins-core && dnf config-manager --set-enabled crb && \
    dnf update -y && dnf install -y --best --skip-broken \
    munge \
    munge-devel \
    numactl \
    numactl-devel \
    rrdtool \
    rrdtool-devel \
    readline \
    readline-devel \
    hwloc \
    hwloc-devel \
    lz4 \
    lz4-devel \
    zlib \
    zlib-devel \
    freeipmi \
    freeipmi-devel \
    dbus \
    dbus-x11 \
    dbus-devel \
    make \
    gcc \
    gcc-c++ \
    tar \
    bzip2 \
    python3.12 \
    python3.12-devel \
    python3.12-pip \
    vim \
    ca-certificates \
    less \
    sudo \
    lua \
    lua-devel \
    libmount \
    libmount-devel \
    mpich \
    mpich-devel \
    git \
    # Database stuff
    mariadb \
    mariadb-server \
    mariadb-pam \
    mariadb-devel \
    && dnf clean all && rm -rf /var/cache/dnf

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# Slurm install
RUN useradd -M slurm

RUN mkdir -p /var/log/slurm
RUN mkdir -p /var/spool/slurmctld && chown slurm /var/spool/slurmctld && chmod u+rwx /var/spool/slurmctld
RUN mkdir -p /var/spool/slurmd    && chown slurm /var/spool/slurmd    && chmod u+rwx /var/spool/slurmd
RUN mkdir -p /var/spool/slurmdbd  && chown slurm /var/spool/slurmdbd  && chmod u+rwx /var/spool/slurmdbd

COPY install_slurm.sh .

RUN ./install_slurm.sh ${SLURM_VERSION} ${SLURM_ROOT} ${SLURM_CONFDIR} --enable-multiple-slurmd

RUN mkdir -p ${SLURM_CONFDIR}
COPY slurmdbd.conf  ${SLURM_CONFDIR}
COPY cgroup.conf    ${SLURM_CONFDIR}
COPY slurm.conf.in  ${SLURM_CONFDIR}

# Generate munge key
RUN mkdir -p /etc/munge && \
    create-munge-key -f && \
    chown munge:munge /etc/munge/munge.key && \
    chmod 400 /etc/munge/munge.key

# Fix permissions
RUN chmod g-w /etc && \
    chmod +t /etc && \
    chown slurm:slurm /opt/slurm-23.02.7/etc/cgroup.conf && \
    chown -R mysql:mysql /var/lib/mysql

# Canary install
RUN python3 -m venv canary && \
    . canary/bin/activate && \
    python -m pip install --upgrade pip==25.1.1 && \
    python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"

WORKDIR /root

# Run entrypoint script for initial container setup
COPY entrypoint.sh example.job test.sh .
ENTRYPOINT ["./entrypoint.sh"]
CMD ["bash"]
