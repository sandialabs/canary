FROM --platform=$BUILDPLATFORM cee-gitlab.sandia.gov:4567/innersource/docker/ubi9:latest

ARG BRANCH_NAME

# Install Base OS Dependencies
RUN dnf update -y && \
    dnf install -y epel-release && dnf clean all && \
    dnf install -y \
	python3 \
	python3-devel \
	python3-pip \
	git && \
    dnf clean all

RUN alternatives --install /usr/bin/python python /usr/bin/python3 1

RUN python3 --version
RUN pip3 --version

# Canary install
RUN python3 -m venv canary && \
    . canary/bin/activate && \
    python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"

COPY test.sh .
ENTRYPOINT ["/bin/bash", "-c", "exec /bin/bash"]
