"""Boilerplate file templates used by the PatchGenerator.

Each template is a plain string.  Variables are enclosed in ``{{VARNAME}}``
so that callers can substitute project-specific values.

The templates are intentionally minimal — they serve as a starting point
that the developer can refine, not as a final artefact.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# .gitignore — generic multi-language starter
# ---------------------------------------------------------------------------

GITIGNORE: str = """\
# === Python ===
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
build/
dist/
*.egg-info/
.eggs/
*.egg
.venv/
venv/
ENV/
env/
.env

# === Node / JavaScript ===
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnp/
.pnp.js
.next/
out/
.nuxt/
dist/

# === Java / Kotlin / Gradle ===
*.class
*.jar
*.war
*.ear
target/
.gradle/
build/

# === Rust ===
target/
Cargo.lock

# === macOS ===
.DS_Store
.AppleDouble
.LSOverride

# === Windows ===
Thumbs.db
ehthumbs.db
Desktop.ini

# === IDEs ===
.idea/
.vscode/
*.suo
*.user
*.userosscache
*.sln.docstates
*.swp
*.swo
*~

# === Secrets & credentials ===
.env
.env.*
*.pem
*.key
*.p12
secrets/
"""

# ---------------------------------------------------------------------------
# README.md — bare-bones project readme
# ---------------------------------------------------------------------------

README_MD: str = """\
# {{PROJECT_NAME}}

> A brief one-line description of this project.

## Overview

<!-- Describe what this project does and why it exists. -->

## Getting Started

### Prerequisites

<!-- List any tools, runtimes, or dependencies that must be installed first. -->

### Installation

```bash
# Example installation steps
```

### Usage

```bash
# Example usage
```

## Contributing

Contributions are welcome.  Please open an issue or submit a pull request.

## License

See [LICENSE](LICENSE) for details.
"""

# ---------------------------------------------------------------------------
# LICENSE — MIT licence template
# ---------------------------------------------------------------------------

LICENSE_MIT: str = """\
MIT License

Copyright (c) {{YEAR}} {{AUTHOR}}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


# ---------------------------------------------------------------------------
# Public helper: render a template with variable substitution
# ---------------------------------------------------------------------------


def render(template: str, **variables: str) -> str:
    """Return *template* with each ``{{KEY}}`` replaced by ``variables[key]``.

    Unknown placeholders are left unchanged so that unreferenced variables
    in a template do not cause errors.
    """
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result
