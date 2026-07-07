# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from schema import Optional
from schema import Or
from schema import Schema
from schema import Use

# --- Resource pool schemas

resource_instance_schema = {
    "id": Use(str),
    Optional("slots", default=1): Or(int, float),
    Optional("properties"): dict,
}

empty_resource_spec_schema = Schema({})

typed_resource_spec_schema = Schema(
    {
        str: [resource_instance_schema],  # type: ignore
    }
)

resource_spec_schema = Schema(
    Or(
        empty_resource_spec_schema,
        typed_resource_spec_schema,
    )
)

node_schema = Schema(
    {
        "id": Use(str),
        Optional("state", default="online"): str,
        Optional("tags", default=[]): [str],
        Optional("groups", default=[]): [str],
        Optional("additional_properties", default={}): dict,
        "resources": resource_spec_schema,
    }
)

resource_pool_schema = Schema(
    {
        Optional("allow_multi_node", default=False): bool,
        Optional("additional_properties", default={}): dict,
        "nodes": [node_schema],
    }
)
