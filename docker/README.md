# Docker Containers

This directory contains Docker containers that can be used for automated pull request testing. There are subdirectories for each scheduler type (i.e. slurm/). Additionally, the standalone directory contains just a Dockerfile for a canary container.

## Python Versions

As of July 3rd, 2025, flux is running python 3.10 and the slurm container is running python 3.12. Upgrading python inside the flux container (for the CI pipeline) is not possible because it is pulled from flux's docker registry. However, with the `Dockerfile`, the slurm and flux (for container testing) python versions can be upgraded at any time.  
