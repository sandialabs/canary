from _nvtest.third_party import schema
from _nvtest.util.rprobe import cpu_count

int_or_id_list = schema.Or(
    schema.And(int, lambda x: x > 0),
    schema.Schema(
        [{"id": schema.Use(str), schema.Optional("slots", default=1): schema.Or(int, float)}]
    ),
)
positive_int = schema.And(int, lambda x: x > 0)


local_schema = schema.Schema(
    {
        # The local schema does not allow nodes
        schema.Forbidden("nodes"): object,
        schema.Optional("cpus", default=cpu_count()): int_or_id_list,
        # local schema disallows *_per_node
        schema.Optional(schema.Regex("^[a-z_][a-z0-9_]*?(?<!_per_node)$")): int_or_id_list,
    }
)


distributed_simple = schema.Schema(
    {
        "nodes": int,
        "cpus_per_node": positive_int,
        schema.Optional(schema.Regex("^[a-z_][a-z0-9_]*_per_node")): positive_int,
    }
)


distributed_detailed = schema.Schema(
    {
        "nodes": [
            {
                "id": schema.Use(str),
                "cpus": int_or_id_list,
                # local schema disallows *_per_node
                schema.Optional(schema.Regex("^[a-z_][a-z0-9_]*?(?<!_per_node)$")): int_or_id_list,
            }
        ]
    }
)


def validate_resource_schema(user_data):
    cfg: dict[str, list] = {}
    if "nodes" not in user_data:
        # local config
        local = cfg.setdefault("local", {})
        validated = local_schema.validate(user_data)
        cpus = validated.pop("cpus")
        if isinstance(cpus, int):
            local["cpus"] = [{"id": str(iid), "slots": 1} for iid in range(cpus)]
        else:
            local["cpus"] = cpus
        for key, value in validated.items():
            if isinstance(value, int):
                local[key] = [{"id": str(iid), "slots": 1} for iid in range(value)]
            else:
                local[key] = value
    elif isinstance(user_data["nodes"], int):
        validated = distributed_simple.validate(user_data)
        nodes = cfg.setdefault("nodes", [])
        node_count = validated.pop("nodes")
        for id in range(node_count):
            node = {"id": str(id)}
            for key, value in validated.items():
                node[key[:-9]] = [{"id": str(iid), "slots": 1} for iid in range(value)]
            nodes.append(node)
    elif isinstance(user_data["nodes"], list):
        validated = distributed_detailed.validate(user_data)
        nodes = cfg.setdefault("nodes", [])
        for instance in validated["nodes"]:
            node = {"id": instance["id"]}
            cpus = instance.pop("cpus")
            if isinstance(cpus, int):
                node["cpus"] = [{"id": str(iid), "slots": 1} for iid in range(cpus)]
            else:
                node["cpus"] = cpus
            for key, value in instance.items():
                if isinstance(value, int):
                    node[key] = [{"id": str(iid), "slots": 1} for iid in range(value)]
                else:
                    node[key] = value
            nodes.append(node)
    return cfg


def test_local_schema():
    data = {"cpus": 2, "gpus": 1}
    config = validate_resource_schema(data)
    assert config["local"] == {
        "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
        "gpus": [{"id": "0", "slots": 1}],
    }


def test_distributed_schema():
    data = {"nodes": 2, "cpus_per_node": 2, "gpus_per_node": 2}
    config = validate_resource_schema(data)
    assert config["nodes"] == [
        {
            "id": "0",
            "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            "gpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
        },
        {
            "id": "1",
            "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            "gpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
        },
    ]
