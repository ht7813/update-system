# updated

A Windows Update–style package update manager for Linux, built around
a D-Bus daemon, pluggable package-manager backends, and a GTK4 frontend.

Currently ships one backend: **pacman** (via `pyalpm` / `pycman`).

## Architecture

```
┌──────────────┐   D-Bus (system bus)   ┌────────────────────┐
│  upmctl      │ ─────────────────────► │  updated (daemon)  │
│  upmgui      │ ◄───── signals ─────── │  - scheduler       │
└──────────────┘                        │  - plugin loader   │
                                        │  - polkit gate     │
                                        └─────────┬──────────┘
                                                  │
                                        ┌─────────▼──────────┐
                                        │ PackageManagerPlugin│
                                        │  - pacman (pyalpm)  │
                                        │  - (future: apt…)   │
                                        └─────────────────────┘
```

- **Daemon** (`updated`) runs as root on the system bus at
  `com.github.ht7813.UpdateManager`. It exposes check/install methods
  and emits `UpdatesChanged`, `Progress`, `Finished` signals.
- **Plugins** are discovered via the `updated.plugins` entry-point group.
  Each plugin implements `refresh_db`, `list_updates`, `install`.
- **Authorization** is enforced through polkit
  (`com.github.ht7813.UpdateManager.install` and `.install-security`).
- **Scheduling** is delegated to a systemd timer (`updated-check.timer`),
  not to an in-daemon loop. The timer calls `CheckUpdatesQuiet` on the bus.

## Components

| Component | Path | Description |
|-----------|------|-------------|
| `updated` | `src/updated/` | D-Bus daemon, core state machine |
| `updated_pacman` | `src/updated_pacman/` | pacman backend (pyalpm) |
| `upmctl` | `src/upmctl/` | CLI frontend |
| `upmgui` | `src/upmgui/` | GTK4 GUI + libnotify |

## Installation

### From source (development)

```bash
# System dependencies (Arch)
sudo pacman -S python-dbus-next python-pyalpm python-gobject \
               gtk4 libnotify

# Clone and install in editable mode
git clone https://github.com/ht7813/update-system
cd update-system
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### System-wide installation

```bash
sudo ./scripts/install.sh
```

This installs:
- `updated.service`, `updated-check.{service,timer}` → `/usr/lib/systemd/system/`
- D-Bus policy → `/usr/share/dbus-1/system.d/`
- polkit action → `/usr/share/polkit-1/actions/`
- default config → `/etc/updated/config.toml` (only if absent)

Uninstall with:

```bash
sudo ./scripts/install.sh --uninstall
```

## Usage

### CLI

```bash
upmctl status                  # daemon state, last check time, plugins
upmctl check [--force]         # trigger a check, print results
upmctl list                    # print cached updates
upmctl install <id> [...]      # install specific packages (id = "src:name")
upmctl install-all [--severity LEVEL | --security]
```

IDs are of the form `pacman:linux`. Use `upmctl list` to see full IDs.

### GUI

```bash
upmgui
```

Shows a window listing available updates, grouped by severity. When new
updates appear while the GUI is running, a libnotify notification is shown:

> 你的电脑缺少重要更新（共 N 项）

Clicking the notification focuses the window.

### Automatic checks

`updated-check.timer` runs `CheckUpdatesQuiet` every 6 hours (with a
30-minute random delay and a 15-minute delay after boot). To adjust:

```bash
sudo systemctl edit updated-check.timer
```

## Configuration

`/etc/updated/config.toml` — see `data/config.toml.example` for a full
annotated template. Highlights:

```toml
[daemon]
default_severity = "normal"
log_level = "info"

[notify]
enabled = true
min_severity = "normal"

[install]
refresh_before_install = true

[plugins]
enabled = ["pacman"]

[plugins.pacman]
config_path = "/etc/pacman.conf"
important_prefixes = []
security_keywords = ["advisory", "asa"]

[severity]
[[severity.rules]]
pattern = "linux*"
level = "critical"
```

Severity rules are evaluated in order; **first match wins**. A rule
overrides the plugin's built-in classification.

Missing fields fall back to defaults; invalid values are logged as
warnings and do not prevent the daemon from starting.

## Writing a plugin

Plugins are Python packages that expose an entry point:

```toml
[project.entry-points."updated.plugins"]
apt = "updated_apt:AptPlugin"
```

The plugin class must subclass `updated.plugin.base.PackageManagerPlugin`:

```python
from updated.plugin.base import PackageManagerPlugin, Update, Severity

class AptPlugin(PackageManagerPlugin):
    name = "apt"
    priority = 20

    def is_available(self) -> bool: ...
    def refresh_db(self) -> None: ...
    def list_updates(self) -> list[Update]: ...
    def install(self, ids, progress) -> bool: ...
```

`list_updates` and `install` are called from a thread pool; they may
block. Do not perform D-Bus or asyncio work inside them.

## polkit

Two actions are defined:

| Action | Default |
|--------|---------|
| `com.github.ht7813.UpdateManager.install` | `auth_admin_keep` on active session |
| `com.github.ht7813.UpdateManager.install-security` | `auth_admin_keep` on active session |

On a TTY without an authentication agent, authorization fails. Run
`pkttyagent --process $$ &` in the same TTY before invoking `upmctl`.

## License

MIT — see [LICENSE](LICENSE).