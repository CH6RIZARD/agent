# Tie This Repo to GitHub and Use in VS Code

## 1. Create the repo on GitHub (if you don’t have one yet)

1. Go to **https://github.com/new**
2. **Repository name:** e.g. `agent` or `d-agent`
3. Leave **empty** (no README, no .gitignore, no license)
4. Click **Create repository**
5. Copy the repo URL (e.g. `https://github.com/YOUR_USERNAME/embodied-mortal-agent.git`)

---

## 2. Tie this folder to that GitHub repo (PowerShell in terminal)

In a terminal (PowerShell), run from this folder:

```powershell
cd d:\agent

# Add your GitHub repo as "origin" (replace with your real URL)
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# Push your existing commit to GitHub
git push -u origin master
```

If the repo was created with a default branch named `main` instead of `master`, use:

```powershell
git push -u origin master:main
```

After this, **this folder and the GitHub repo are tied**: pushes from here update GitHub; pulls bring GitHub changes here.

---

## 3. Use this in VS Code / Cursor

- **Open the folder:** File → Open Folder → choose `d:\agent`
- **Source Control:** Click the branch icon in the left sidebar (or `Ctrl+Shift+G`)
- **Sync with GitHub:**
  - **Push:** Click the cloud-with-arrow icon, or run **Git: Push** from the Command Palette (`Ctrl+Shift+P`)
  - **Pull:** Same place, or **Git: Pull**
- **Commit from VS Code:** Stage changes in Source Control, type a message, click ✓ Commit, then push.

No extra config: once the remote is added and you’ve pushed once, VS Code uses the same `.git` in `d:\agent`, so all changes here are the same in VS Code and on GitHub.

---

## 4. One-time: if GitHub asks for login

- **HTTPS:** GitHub may ask for credentials. Prefer **Personal Access Token** instead of password: GitHub → Settings → Developer settings → Personal access tokens → generate one, use it as the password when prompted.
- **SSH:** If you use SSH keys, use the SSH URL when adding the remote: `git@github.com:YOUR_USERNAME/REPO_NAME.git`

---

**Summary:** Replace `YOUR_USERNAME` and `REPO_NAME` in the `git remote add` and `git push` commands, run them once in `d:\agent`, then open `d:\agent` in VS Code and use the Source Control view to push/pull. Your code stays the same; only the link to GitHub is added.
