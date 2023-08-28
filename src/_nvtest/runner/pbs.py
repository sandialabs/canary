from ..util.misc import boolean
from ..util.resources import compute_resource_allocations
from ..util.time import hhmmss


class PBS:
    resource_attrs = ("nodes", "ppn", "gpus", "ntasks")
    el_opts = ("walltime", "mem", "software", "nodes", "ppn", "gpus")

    @property
    def auto_allocate(self):
        explicit_allocation = any([x in self.resource_attrs for x in self.options])
        return not explicit_allocation

    def set_option(self, name, value):
        name = name.replace("_", "-")
        aliases = {
            "email-to": "M",
            "name": "N",
            "jobname": "N",
            "job-name": "N",
            "mail": "m",
            "partition": "q",
            "queue": "q",
            "interactive": "I",
            "time": "walltime",
            "delay": "a",
            "account": "A",
            "priority": "p",
            "x11-forwarding": "X",
            "ntasks-per-node": "ppn",
            "stdout": "o",
            "stderr": "e",
        }
        if name in aliases:
            name = aliases[name]
        if name in ("interactive",):
            value = boolean(value)
        elif name == "mail":
            value = PBS.mail_type(value)
        elif name in ("walltime", "cput"):
            value = hhmmss(value)
        self.options[name] = value

    @staticmethod
    def mail_type(arg):
        """Use any combination of the letters a, b, and e. Requests a status email when
        the job begins (b), ends (e), or aborts (a). The n option requests no email, but
        you'll still get email if the job aborts."""
        valid_mail_types = ("a", "b", "e", "n")
        for v in arg:
            if v not in valid_mail_types:
                raise ValueError(f"{v} is not a valid mail type")
        if "n" in arg and len(arg) != 1:
            raise ValueError("mail type argument `n` must appear alone")
        return arg

    def calculate_resource_allocations(self):
        """Performs basic resource calculations"""
        tasks = self.max_tasks_required()
        ns = compute_resource_allocations(ranks=tasks)

        tasks = ns.ranks
        nodes = ns.nodes
        if tasks % nodes != 0:
            raise ValueError("Unable to equally distribute tasks across nodes")

        # Tasks equally distributed amongst nodes
        ppn = int(tasks / nodes)

        self.options["ppn"] = ppn
        self.options["nodes"] = nodes

    def write_preamble(self, script):
        """Write the pbs submission script preamble"""
        if self.auto_allocate:
            self.calculate_resource_allocations()
        if "nodes" in self.options and "ppn" in self.options:
            nodes, ppn = self.options["nodes"], self.options["ppn"]
            script.write(f"#PBS -l nodes={nodes}:ppn={ppn}\n")
        elif "nodes" in self.options and "ntasks" in self.options:
            nodes, ntasks = self.options["nodes"], self.options["ntasks"]
            if ntasks % nodes != 0:
                raise ValueError("Unable to equally distribute tasks across nodes")
            ppn = int(ntasks / nodes)
            script.write(f"#PBS -l nodes={nodes}:ppn={ppn}\n")
        else:
            raise ValueError("Provide nodes and ppn before continuing")
        for name, value in self.options.items():
            if value in (False, None) or name in self.resource_attrs:
                continue
            prefix = "-" if len(name) == 1 else "--"
            if name in self.el_opts:
                option_line = f"#PBS -l {name}={value}\n"
            elif value is True:
                option_line = f"#PBS {prefix}{name}\n"
            else:
                op = " " if len(name) == 1 else "="
                option_line = f"#PBS {prefix}{name}{op}{value}\n"
            script.write(option_line)
