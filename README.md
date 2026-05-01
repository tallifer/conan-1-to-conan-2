# Conan 1 to Conan 2 Migration Tracker

A small local Flask tool to track migration progress across interdependent Conan packages.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure scan roots

Edit `migration-progress.yml` and set `scan_roots` to local source directories:

```yaml
scan_roots:
  - D:/code

libraries: {}
```

## Run

```bash
python app.py
```

Open <http://localhost:5000>.

## Use

- Click **Rescan libraries** to discover packages and refresh dependencies.
- Open a library to edit **status** and **notes**.
- Updates are saved immediately to `migration-progress.yml`.
- Visit **View dependency graph** for Mermaid-based internal dependency visualization.
