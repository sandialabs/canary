# Slurm Container
This container builds the version of `canary` specified in the Docker build command.

## Commands for Building+Running
```
docker build --build-arg BRANCH_NAME={pull-request-branch-name} -f Dockerfile -t canary_slurm
docker run -it --rm canary_slurm
```
