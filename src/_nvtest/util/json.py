import json
from pathlib import Path
from typing import Any
from typing import TextIO
from typing import Union


def read_json(file: Union[str, Path, TextIO], lines: bool = False) -> Any:
    fown = False
    if isinstance(file, str):
        file = Path(file)
    if isinstance(file, Path):
        fown = True
        file = file.open("r")
    if not lines:
        data = json.load(file)
    else:
        data = []
        for line in file:
            if line.split():
                data.append(json.loads(line))
    if fown:
        file.close()
    return data
