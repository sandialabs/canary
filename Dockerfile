FROM registry.redhat.io/ubi9/ubi:latest

# Set working directory to make things cleaner
WORKDIR /app

# Install Base OS Dependencies
RUN dnf update -y && \
    dnf install -y \
	python3.12 \
	git && \
    dnf clean all

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

RUN python3 --version

# Create a venv for canary to run in
RUN python3 -m venv canary_venv && \
    . /app/canary_venv/bin/activate && \
    /app/canary_venv/bin/python3 -m pip install --upgrade pip==25.1.1

# Install canary into the venv (for developers)
RUN /app/canary_venv/bin/python3 -m pip install -e git+https://github.com/sandialabs/canary#egg=canary-wm[dev]

# Set working direcotry inside of the venv canary-wm dev src
WORKDIR /app/canary_venv/src/canary-wm/

# Make sure the virtual environment is being used
ENTRYPOINT ["/bin/bash", "-c", "source /app/canary_venv/bin/activate && exec /bin/bash"]

# Commands to run canary tests
CMD ["canary", "run"]
