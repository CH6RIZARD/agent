# Workspace on D: drive (data disk)

This project is intended to run from the **D: drive**, not C:.

## Move entirely from C: to D: (and remove from C:)

From this repo root, run:

```powershell
.\scripts\move_workspace_to_d.ps1
```

That copies the whole workspace to **D:\agent** and ensures `constitution.yaml` exists there. After it finishes:

1. Close Cursor.
2. Open **D:\agent** in Cursor (File → Open Folder).
3. In PowerShell, run the command the script printed to remove the folder from C:, e.g.:
   ```powershell
   Remove-Item -Recurse -Force 'C:\Users\chiagozie\OneDrive\Desktop\agent'
   ```

## One-time setup (copy only, keep C:)

To copy to D: without removing from C::

```powershell
.\scripts\setup_workspace_on_d.ps1
```

## Use the workspace (mortal agent only)

1. In Cursor: **File → Open Folder** → `D:\agent`
2. In a terminal: `cd D:\agent\mortal_agent` then `python -m cli.main run`

Network (WiFi/ethernet) is wired on by default: the agent uses the system network for outbound HTTP (NET_FETCH) via the integrated network pipeline.

To open Cursor on D:\agent automatically:

```powershell
.\scripts\setup_workspace_on_d.ps1 --open
```
