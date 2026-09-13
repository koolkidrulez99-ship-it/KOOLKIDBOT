"""Generate a coverage inventory without importing or changing the application."""
import ast
import json
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in ("button", "input", "select", "form", "details"):
            return
        self.items.append({"tag": tag, "line": self.getpos()[0], **{
            k: v for k, v in attrs.items()
            if k in ("id", "type", "onclick", "onchange", "oninput", "data-action", "action", "method", "min", "max", "step")
        }})


inventory = {"components": {}, "routes": []}
for filename in [*sorted((ROOT / "static/components").glob("*.html")), *[ROOT / "templates" / n for n in ("cover.html", "login.html", "register.html", "forgot_password.html", "koolkid_auto_trade.html")]]:
    if not filename.exists():
        continue
    parser = Controls()
    parser.feed(filename.read_text(encoding="utf-8-sig"))
    inventory[filename.relative_to(ROOT).as_posix()] = parser.items
for filename in (ROOT / "server.py", ROOT / "cloud_routes.py"):
    tree = ast.parse(filename.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "route":
                route = decorator.args[0]
                if isinstance(route, ast.Constant):
                    inventory["routes"].append({"path": route.value, "function": node.name, "file": filename.name, "line": node.lineno})
(OUT / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
print(json.dumps({"routes": len(inventory["routes"]), "controls": {k: len(v) for k, v in inventory.items() if k not in ("components", "routes")}}))
