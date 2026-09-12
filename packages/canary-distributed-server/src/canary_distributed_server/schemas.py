from collections import Counter

from schema import And
from schema import Optional as Optional
from schema import Or
from schema import Schema
from schema import SchemaError
from schema import Use

rspec_schema = Schema({"id": And(str, len), "slots": And(Use(int), lambda n: n >= 0)})  # type: ignore
resource_schema = Schema({"cpus": [rspec_schema], Optional(str): [rspec_schema]})
machine_schema = Schema(
    {
        "hostname": And(str, len),
        "resources": resource_schema,
        Optional("tags"): [str],
        Optional("groups"): [str],
        Optional("state"): And(str, Or("online", "offline", "maintenance")),  # type: ignore
    }
)


class MachineSchema(Schema):
    def validate(self, data, is_root_eval=True):  # type: ignore
        data = super().validate(data, is_root_eval=False)  # type: ignore
        if is_root_eval:
            # only allow hostname to appear once
            counts = Counter()
            for machine in data["machines"]:
                counts[machine["hostname"]] += 1
            duplicates = [host for host, count in counts.items() if count > 1]
            if duplicates:
                message = f"Duplicate hosts: {', '.join(sorted(duplicates))}"
                message = self._prepend_schema_name(message)
                raise SchemaError(message, None)
        return data


machinefile_schema = MachineSchema({"machines": [machine_schema]})
