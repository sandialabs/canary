# NVTEST

An application testing framework inspired by vvtest.

## Requirements

Python 3.9+

## Install

```console
git clone git@cee-gitlab.sandia.gov:tjfulle/nvtest
cd nvtest
pip install -e .
```

## Basic usage

`nvtest` has many subcommands.  To get the list of subcommands, issue

```console
nvtest -h
```

To get help on an individual subcommand, issue

```console
nvtest SUBCOMMAND -h
```

## Configuration settings

Additional configuration is not required.  To see the current configuration, issue

```console
nvtest config show
```

Configuration variables can be set on the command line or read from a configuration file.

### Configuration file

You can explicitly set configuration variables in:

- `./nvtest.toml`;
- `~/.config/nvtest.toml`; and
- `~/.nvtest.toml`.

The first found is used.  Basic configuration settings are:

```toml
[nvtest]

[nvtest.config]
debug = false
log_level = int

[nvtest.machine]
sockets_per_node = 1
cores_per_socket = N  # default computed from os.cpu_count()
cpu_count = N  # default computed from os.cpu_count()

[nvtest.variables]
key = "value"  # environment variables to set for the test session
```

### Setting configuration variables on the command line

Use yaml path syntax to set any of the above variables.  For example,

```console
nvtest -c machine:cpu_count:20 -c config:log_level:0 SUBCOMMAND [OPTIONS] ARGUMENTS
```

To set environment variables do

```console
nvtest -e VAR1=VAL1 -e VAR2=VAL2 SUBCOMMAND [OPTIONS] ARGUMENTS
```

## Find tests to run

```console
nvtest find [OPTIONS] PATH [PATH...]
```

### To print a graph of test dependencies

```console
nvtest find -g PATH [PATH...]
```

### To show available keywords

```console
nvtest find --keywords PATH [PATH...]
```

### To show file paths

```console
nvtest find -f PATH [PATH...]
```

## Describe a test

Show a graph of test dependencies

```console
nvtest describe [OPTIONS] PATH
```

## Run tests directly in your shell

### Basic usage

```console
nvtest run [OPTIONS] PATH [PATHS...]
```

### Filter tests to run by keyword

```console
nvtest run -k KEYWORD_EXPR PATH [PATHS...]
```

where `KEYWORD_EXPR` is a Python expression.  For example, `-k 'key1 and not key2`.

### Limit the number of concurrent tests

```console
nvtest run --max-workers=N PATH [PATHS...]
```

### Set a timeout on the test session

```console
nvtest run --timeout=TIME_EXPR PATH [PATHS...]
```

where `TIME_EXPR` is a number or a human-readable number representation like `1 sec`, `1s`, etc.

## Run tests in a batch scheduler

### Basic usage

```console
nvtest run [--batches=N|--batch-size=T] [OPTIONS] PATH [PATHS...]
```

### Use slurm scheduler

```console
nvtest run --runner=slurm PATH [PATHS...]
```

### Pass arguments to the scheduler

```console
nvtest run --runner=slurm -R,ARG1 -R,ARG2 PATH [PATHS...]
```

where `ARGI` are passed directly to the scheduler.  Eg, `-R,--account=XXYYZZ01`
