RUN python3 -m venv canary && \
    . canary/bin/activate && \
    python -m pip install --upgrade pip==25.1.1 && \
    python3 -m pip install "canary-wm@git+https://git@github.com/sandialabs/canary@$BRANCH_NAME"
