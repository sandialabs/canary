import argparse


class _Slurm:
    DO_NOT_PROCESS = "\\"
    HOSTNAME = "%N"
    JOB_ARRAY_ID = "%a"
    JOB_ARRAY_MASTER_ID = "%A"
    JOB_ID = "%j"
    JOB_ID_STEP_ID = "%J"
    JOB_NAME = "%x"
    NODE_IDENTIFIER = "%n"
    PERCENTAGE = "%%"
    STEP_ID = "%s"
    TASK_IDENTIFIER = "%t"
    USER_NAME = "%u"
    SLURMD_NODENAME = "$SLURMD_NODENAME"
    SLURM_ARRAY_JOB_ID = "$SLURM_ARRAY_JOB_ID"
    SLURM_ARRAY_TASK_COUNT = "$SLURM_ARRAY_TASK_COUNT"
    SLURM_ARRAY_TASK_ID = "$SLURM_ARRAY_TASK_ID"
    SLURM_ARRAY_TASK_MAX = "$SLURM_ARRAY_TASK_MAX"
    SLURM_ARRAY_TASK_MIN = "$SLURM_ARRAY_TASK_MIN"
    SLURM_ARRAY_TASK_STEP = "$SLURM_ARRAY_TASK_STEP"
    SLURM_CLUSTER_NAME = "$SLURM_CLUSTER_NAME"
    SLURM_CPUS_ON_NODE = "$SLURM_CPUS_ON_NODE"
    SLURM_CPUS_PER_GPU = "$SLURM_CPUS_PER_GPU"
    SLURM_CPUS_PER_TASK = "$SLURM_CPUS_PER_TASK"
    SLURM_DISTRIBUTION = "$SLURM_DISTRIBUTION"
    SLURM_EXPORT_ENV = "$SLURM_EXPORT_ENV"
    SLURM_GPUS = "$SLURM_GPUS"
    SLURM_GPUS_PER_NODE = "$SLURM_GPUS_PER_NODE"
    SLURM_GPUS_PER_SOCKET = "$SLURM_GPUS_PER_SOCKET"
    SLURM_GPUS_PER_TASK = "$SLURM_GPUS_PER_TASK"
    SLURM_GPU_BIND = "$SLURM_GPU_BIND"
    SLURM_GPU_FREQ = "$SLURM_GPU_FREQ"
    SLURM_GTIDS = "$SLURM_GTIDS"
    SLURM_HET_SIZE = "$SLURM_HET_SIZE"
    SLURM_JOBID = "$SLURM_JOBID"
    SLURM_JOBNODELIST = "$SLURM_JOBNODELIST"
    SLURM_JOBNUM_NODES = "$SLURM_JOBNUM_NODES"
    SLURM_JOB_ACCOUNT = "$SLURM_JOB_ACCOUNT"
    SLURM_JOB_CPUS_PER_NODE = "$SLURM_JOB_CPUS_PER_NODE"
    SLURM_JOB_DEPENDENCY = "$SLURM_JOB_DEPENDENCY"
    SLURM_JOB_ID = "$SLURM_JOB_ID"
    SLURM_JOB_NAME = "$SLURM_JOB_NAME"
    SLURM_JOB_NODELIST = "$SLURM_JOB_NODELIST"
    SLURM_JOB_NUM_NODES = "$SLURM_JOB_NUM_NODES"
    SLURM_JOB_PARTITION = "$SLURM_JOB_PARTITION"
    SLURM_JOB_QOS = "$SLURM_JOB_QOS"
    SLURM_JOB_RESERVATION = "$SLURM_JOB_RESERVATION"
    SLURM_LOCALID = "$SLURM_LOCALID"
    SLURM_MEM_PER_CPU = "$SLURM_MEM_PER_CPU"
    SLURM_MEM_PER_GPU = "$SLURM_MEM_PER_GPU"
    SLURM_MEM_PER_NODE = "$SLURM_MEM_PER_NODE"
    SLURM_NODEID = "$SLURM_NODEID"
    SLURM_NODE_ALIASES = "$SLURM_NODE_ALIASES"
    SLURM_NPROCS = "$SLURM_NPROCS"
    SLURM_NTASKS = "$SLURM_NTASKS"
    SLURM_NTASKS_PER_CORE = "$SLURM_NTASKS_PER_CORE"
    SLURM_NTASKS_PER_NODE = "$SLURM_NTASKS_PER_NODE"
    SLURM_NTASKS_PER_SOCKET = "$SLURM_NTASKS_PER_SOCKET"
    SLURM_PRIO_PROCESS = "$SLURM_PRIO_PROCESS"
    SLURM_PROCID = "$SLURM_PROCID"
    SLURM_PROFILE = "$SLURM_PROFILE"
    SLURM_RESTART_COUNT = "$SLURM_RESTART_COUNT"
    SLURM_SUBMIT_DIR = "$SLURM_SUBMIT_DIR"
    SLURM_SUBMIT_HOST = "$SLURM_SUBMIT_HOST"
    SLURM_TASKS_PER_NODE = "$SLURM_TASKS_PER_NODE"
    SLURM_TASK_PID = "$SLURM_TASK_PID"
    SLURM_TOPOLOGY_ADDR = "$SLURM_TOPOLOGY_ADDR"
    SLURM_TOPOLOGY_ADDR_PATTERN = "$SLURM_TOPOLOGY_ADDR_PATTERN"

    @staticmethod
    def make_argument_parser():
        parser = argparse.ArgumentParser()
        parser.add_argument("-A", "--account", metavar="<account>")
        parser.add_argument(
            "--acctg_freq", metavar="<datatype><interval>[,<datatype><interval>...]"
        )
        parser.add_argument("-a", "--array", metavar="<indexes>")
        parser.add_argument("--batch", metavar="<list>")
        parser.add_argument("--bb", metavar="<spec>")
        parser.add_argument("--bbf", metavar="<file_name>")
        parser.add_argument("-b", "--begin", metavar="<time>")
        parser.add_argument("-D", "--chdir", metavar="<directory>")
        parser.add_argument("--cluster-constraint", metavar="[!]<list>")
        parser.add_argument("-M", "--clusters", metavar="<string>")
        parser.add_argument("--comment", metavar="<string>")
        parser.add_argument("-C", "--constraint", metavar="<list>")
        parser.add_argument("--container", metavar="<path_to_container>")
        parser.add_argument("--container-id", metavar="<container_id>")
        parser.add_argument("--contiguous", action="store_true", default=False)
        parser.add_argument("-S", "--core-spec", metavar="<num>")
        parser.add_argument("--cores-per-socket", metavar="<cores>")
        parser.add_argument("--cpu-freq", metavar="<p1>[-p2[:p3]]")
        parser.add_argument("--cpus-per-gpu", metavar="<ncpus>")
        parser.add_argument("-c", "--cpus-per-task", metavar="<ncpus>")
        parser.add_argument("--deadline", metavar="<OPT>")
        parser.add_argument("--delay-boot", metavar="<minutes>")
        parser.add_argument("-d", "--dependency", metavar="<dependency_list>")
        parser.add_argument(
            "-m",
            "--distribution",
            metavar="{*|block|cyclic|arbitrary|plane<size>}[:{*|block|cyclic|fcyclic}[:{*|block|cyclic|fcyclic}]][,{Pack|NoPack}]",  # noqa: E501
        )
        parser.add_argument("-e", "--error", metavar="<filename_pattern>")
        parser.add_argument("-x", "--exclude", metavar="<node_name_list>")
        parser.add_argument("--exclusive", metavar="[{user|mcs}]")
        parser.add_argument(
            "--export", metavar="{[ALL,]<environment_variables>|ALL|NONE}"
        )
        parser.add_argument("--export-file", metavar="{<filename>|<fd>}")
        parser.add_argument("--extra", metavar="<string>")
        parser.add_argument(
            "-B", "--extra-node-info", metavar="<sockets>[:cores[:threads]]"
        )
        parser.add_argument("--get-user-env", metavar="[timeout][mode]")
        parser.add_argument("--gid", metavar="<group>")
        parser.add_argument("--gpu-bind", metavar="[verbose,]<type>")
        parser.add_argument(
            "--gpu-freq", metavar="[<type]value>[,<typevalue>][,verbose]"
        )
        parser.add_argument("--gpus-per-node", metavar="[type:]<number>")
        parser.add_argument("--gpus-per-socket", metavar="[type:]<number>")
        parser.add_argument("--gpus-per-task", metavar="[type:]<number>")
        parser.add_argument("-G", "--gpus", metavar="[type:]<number>")
        parser.add_argument("--gres", metavar="<list>")
        parser.add_argument("--gres-flags", metavar="<type>")
        parser.add_argument("--hint", metavar="<type>")
        parser.add_argument("-H", "--hold", action="store_true", default=False)
        parser.add_argument("--ignore-pbs", action="store_true", default=False)
        parser.add_argument("-i", "--input", metavar="<filename_pattern>")
        parser.add_argument("-J", "--job-name", metavar="<jobname>")
        parser.add_argument("--kill-on-invalid-dep", metavar="<yes|no>")
        parser.add_argument(
            "-L",
            "--licenses",
            metavar="<license>[@db][:count][,license[@db][:count]...]",
        )
        parser.add_argument("--mail-type", metavar="<type>")
        parser.add_argument("--mail-user", metavar="<user>")
        parser.add_argument("--mcs-label", metavar="<mcs>")
        parser.add_argument("--mem", metavar="<size>[units]")
        parser.add_argument("--mem-bind", metavar="[{quiet|verbose},]<type>")
        parser.add_argument("--mem-per-cpu", metavar="<size>[units]")
        parser.add_argument("--mem-per-gpu", metavar="<size>[units]")
        parser.add_argument("--mincpus", metavar="<n>")
        parser.add_argument("--network", metavar="<type>")
        parser.add_argument("--nice", metavar="[adjustment]")
        parser.add_argument("-k", "--no-kill", metavar="[off]")
        parser.add_argument("--no_requeue", action="store_true", default=False)
        parser.add_argument("-F", "--nodefile", metavar="<node_file>")
        parser.add_argument("-w", "--nodelist", metavar="<node_name_list>")
        parser.add_argument(
            "-N", "--nodes", metavar="<minnodes>[-maxnodes]|<size_string>"
        )
        parser.add_argument("--ntasks-per-core", metavar="<ntasks>")
        parser.add_argument("--ntasks-per-gpu", metavar="<ntasks>")
        parser.add_argument("--ntasks-per-node", metavar="<ntasks>")
        parser.add_argument("--ntasks-per-socket", metavar="<ntasks>")
        parser.add_argument("-n", "--ntasks", metavar="<number>")
        parser.add_argument("--open_mode", metavar="{append|truncate}")
        parser.add_argument("-o", "--output", metavar="<filename_pattern>")
        parser.add_argument("-O", "--overcommit", action="store_true", default=False)
        parser.add_argument("-s", "--oversubscribe", action="store_true", default=False)
        parser.add_argument("-p", "--partition", metavar="<partition_names>")
        parser.add_argument("--power", metavar="<flags>")
        parser.add_argument("--prefer", metavar="<list>")
        parser.add_argument("--priority", metavar="<value>")
        parser.add_argument("--profile", metavar="{all|none|<type>[,<type>...]}")
        parser.add_argument("--propagate", metavar="[rlimit[,rlimit...]]")
        parser.add_argument("-q", "--qos", metavar="<qos>")
        parser.add_argument("-Q", "--quiet", action="store_true", default=False)
        parser.add_argument("--reboot", action="store_true", default=False)
        parser.add_argument("--requeue", action="store_true", default=False)
        parser.add_argument("--reservation", metavar="<reservation_names>")
        parser.add_argument("--signal", metavar="[{R|B}:]<sig_num>[@sig_time]")
        parser.add_argument("--sockets-per-node", metavar="<sockets>")
        parser.add_argument("--spread-job", action="store_true", default=False)
        parser.add_argument("--switches", metavar="<count>[@max-time]")
        parser.add_argument("--test-only", action="store_true", default=False)
        parser.add_argument("--thread-spec", metavar="<num>")
        parser.add_argument("--threads-per-core", metavar="<threads>")
        parser.add_argument("--time-min", metavar="<time>")
        parser.add_argument("-t", "--time", metavar="<time>")
        parser.add_argument("--tmp", metavar="<size>[units]")
        parser.add_argument("--tres-per-task", metavar="<list>")
        parser.add_argument("--uid", metavar="<user>")
        parser.add_argument("--use-min-nodes", action="store_true", default=False)
        parser.add_argument("-v", "--verbose", metavar="<value>")
        parser.add_argument("--wait-all-nodes", metavar="<value>")
        # g.add_argument("-W", "--wait", action="store_true", default=False)
        parser.add_argument("--wckey", metavar="<wckey>")
        parser.add_argument("--wrap", metavar="<command_string>")
        return parser
