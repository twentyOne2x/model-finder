"""Create an offline render fixture; placeholder cursors are for tests only."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def create_fixture(destination: Path) -> Path:
    config = json.loads((ROOT / "model-finder.example.json").read_text())
    for member in config["members"]:
        member["avatar"] = str(ROOT / member["avatar"])
    config["popup"]["sounds"] = {}
    # CI does not download or redistribute Blizzard media. These generated icons
    # satisfy image-loading tests; they are not presented as the WoW cursors.
    config["popup"]["theme"] = {
        "cursor": str(ROOT / "assets/theme/role-tank.png"),
        "cursorActive": str(ROOT / "assets/theme/role-healer.png"),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config, indent=2) + "\n")
    return destination


if __name__ == "__main__":
    print(create_fixture(Path(sys.argv[1])).resolve())
