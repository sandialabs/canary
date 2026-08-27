.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Timing Metrics Reference
=========================

The ``canary_flux`` extension tracks comprehensive timing metrics throughout Flux execution, providing detailed performance analysis capabilities.

Timing Metrics Overview
=======================

**Timing Levels**:

- **Allocation Level**: Flux allocation request and grant timing
- **JobspecV1 Level**: Individual job submission and execution timing
- **Inner Canary Level**: Nested Canary job execution timing
- **Overhead Level**: Flux execution overhead measurement

Allocation Timing Metrics
=========================

**Allocation Request Timing**:

``allocation_requested_at``
   Timestamp when Flux allocation was requested

``allocation_granted_at``
   Timestamp when Flux allocation became active

``allocation_wait_seconds``
   Duration spent waiting for Flux allocation
   Calculation: ``allocation_granted_at - allocation_requested_at``

JobspecV1 Timing Metrics
========================

**Submission Timing**:

``jobspec_submitted_at``
   Timestamp when job was submitted to Flux scheduler

``flux_started_at``
   Timestamp when Flux job started execution

**Inner Canary Timing**:

``inner_opened_at``
   Timestamp when inner Canary job was opened

``inner_started_at``
   Timestamp when inner Canary job started

``inner_stopped_at``
   Timestamp when inner Canary job stopped

``inner_finished_at``
   Timestamp when inner Canary job finished

**Completion Timing**:

``flux_finished_at``
   Timestamp when Flux job completed

Duration Metrics
================

**Allocation Duration Metrics**:

``allocation_request_to_jobspec_submit_seconds``
   Time from allocation request to first job submission

``allocation_granted_to_jobspec_submit_seconds``
   Time from allocation grant to first job submission

**JobspecV1 Duration Metrics**:

``jobspec_submit_to_flux_start_seconds``
   Time from job submission to Flux job start

``flux_start_to_inner_finish_seconds``
   Total time from Flux start to inner completion

``inner_finish_to_flux_return_seconds``
   Time from inner finish to Flux job completion

``flux_jobspec_total_seconds``
   Total time for Flux JobspecV1 execution

**Inner Canary Duration Metrics**:

``inner_total_seconds``
   Total time for inner Canary job execution

``inner_pending_seconds``
   Time spent in pending phase

``inner_staging_seconds``
   Time spent in staging phase

``inner_command_seconds``
   Time spent in command execution phase

``inner_finishing_seconds``
   Time spent in finishing phase

Overhead Metrics
================

**Launch Overhead Metrics**:

``launch_seconds``
   Overhead before inner job opens

``flux_start_to_inner_open_seconds``
   Time from Flux start to inner job open

**Return Overhead Metrics**:

``return_seconds``
   Overhead after inner job finishes

``inner_stop_to_flux_return_seconds``
   Time from inner stop to Flux return

**Total Overhead Metrics**:

``total_external_seconds``
   Sum of launch and return overheads

Timing Metrics Structure
========================

Timing metrics are stored in job measurements under the ``flux`` key:

**Structure**:

.. code-block:: json

   {
     "flux": {
       "timing": {
         "allocation": {
           "requested_at": 1234567890.123,
           "granted_at": 1234567895.456,
           "wait_seconds": 5.333
         },
         "jobspec_v1": {
           "submitted_at": 1234567896.789,
           "flux_started_at": 1234567897.012,
           "inner_opened_at": 1234567897.234,
           "inner_finished_at": 1234567903.123,
           "flux_finished_at": 1234567903.456
         },
         "durations": {
           "allocation_request_to_jobspec_submit_seconds": 6.666,
           "jobspec_submit_to_flux_start_seconds": 0.223,
           "flux_start_to_inner_finish_seconds": 5.911,
           "flux_jobspec_total_seconds": 6.667
         }
       },
       "overhead": {
         "launch_seconds": 0.222,
         "return_seconds": 0.333,
         "total_external_seconds": 0.555
       }
     }
   }

Timing Metrics Usage
====================

**Performance Analysis**:
- Identify bottlenecks in Flux execution
- Measure allocation wait times
- Analyze submission delays
- Quantify execution overhead

**Optimization**:
- Reduce launch overhead
- Minimize return delays
- Optimize resource allocation
- Improve job scheduling

Timing Metrics Examples
=======================

Basic Timing Analysis
---------------------

.. code-block:: console

   # Run with Flux and examine timing
   python3 -m canary flux run ./basic

   # Check timing metrics
   cat <workspace>/sessions/<session>/jobs/<job-id>/testcase.lock | grep flux.timing

Timing Metrics Best Practices
==============================

1. Monitor key metrics: allocation wait, submission delay, execution overhead
2. Set performance baselines for comparison
3. Analyze trends over time
4. Optimize areas with highest overhead
5. Document timing analysis and optimizations

Timing Metrics Comparison
=========================

**Flux Extension (canary_flux)**:
- Direct Flux timing metrics
- Individual job timing
- Fine-grained overhead measurement
- Comprehensive timing structure

**HPC Extension (canary_hpc)**:
- Batch-level timing metrics
- Batch execution timing
- Different timing structure
- Higher overhead due to batching

