from __future__ import annotations

import ast
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


class LocalReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        for key in ("src", "href"):
            value = values.get(key)
            if value and value.startswith("./"):
                self.references.append(value)


def validate_python_syntax() -> None:
    files = list((BACKEND / "app").rglob("*.py"))
    files += list((BACKEND / "scripts").rglob("*.py"))

    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    print(f"[OK] Python: {len(files)} arquivos com sintaxe válida")



def validate_relative_imports() -> None:
    app_root = BACKEND / "app"
    checked = 0

    for path in app_root.rglob("*.py"):
        module_parts = path.relative_to(BACKEND).with_suffix("").parts
        package_parts = list(module_parts[:-1])
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level <= 0:
                continue

            up = node.level - 1
            if up > len(package_parts):
                raise RuntimeError(
                    f"Import relativo inválido em {path}:{node.lineno}"
                )

            base = package_parts[: len(package_parts) - up] if up else package_parts
            target_parts = base + ((node.module or "").split(".") if node.module else [])
            target = BACKEND.joinpath(*target_parts)

            if not (target.with_suffix(".py").exists() or (target / "__init__.py").exists()):
                raise RuntimeError(
                    f"Módulo relativo não encontrado em {path}:{node.lineno}: "
                    f"{'.' * node.level}{node.module or ''}"
                )

            checked += 1

    print(f"[OK] Python: {checked} imports relativos resolvidos")

def validate_frontend_references() -> None:
    checked = 0

    for page in FRONTEND.glob("*.html"):
        parser = LocalReferenceParser()
        parser.feed(page.read_text(encoding="utf-8"))

        for reference in parser.references:
            if reference.startswith("./#"):
                continue

            target = page.parent / reference[2:]
            if not target.exists():
                raise RuntimeError(
                    f"Referência inexistente em {page.name}: {reference}"
                )
            checked += 1

    print(f"[OK] Frontend: {checked} referências locais válidas")


def validate_javascript() -> None:
    try:
        subprocess.run(
            ["node", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[INFO] Node.js não disponível; validação JS foi ignorada")
        return

    files = list((FRONTEND / "assets" / "js").rglob("*.js"))
    for path in files:
        subprocess.run(
            ["node", "--check", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )

    print(f"[OK] JavaScript: {len(files)} arquivos com sintaxe válida")


def main() -> None:
    validate_python_syntax()
    validate_relative_imports()
    validate_frontend_references()
    validate_javascript()
    print("\nVALIDAÇÃO ESTRUTURAL: OK")


if __name__ == "__main__":
    main()
