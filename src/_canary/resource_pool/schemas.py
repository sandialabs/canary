# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from schema import Optional
from schema import Or
from schema import Schema
from schema import SchemaMissingKeyError
from schema import Use

# --- Resource pool schemas
resource_spec_schema = Schema(
    {str: [{"id": Use(str), Optional("slots", default=1): Or(int, float)}]}  # type: ignore
)


class RPSchema(Schema):
    def rspec(self, count):
        return [{"id": str(j), "slots": 1} for j in range(count)]

    def validate(self, data, is_root_eval=True):
        data = super().validate(data, is_root_eval=False)
        if is_root_eval:
            data.setdefault("additional_properties", {})
            for key in list(data.keys()):
                if key in ("additional_properties", "resources"):
                    continue
                count = data.pop(key)
                data.setdefault("resources", {})[key] = self.rspec(count)
            if "resources" not in data:
                message = "Missing key: resources"
                message = self._prepend_schema_name(message)
                raise SchemaMissingKeyError(message, None)
        return data


resource_pool_schema = RPSchema(
    {
        Optional("resources"): resource_spec_schema,
        Optional("additional_properties"): dict,
        Optional(str): int,
    }
)
