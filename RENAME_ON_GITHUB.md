# Finish repo rename on GitHub (one-time)

Your local repo is already set to push to **embodied-mortal-agent**. Do this once on GitHub:

1. Open: **https://github.com/CH6RIZARD/agent/settings**
2. Under **Repository name**, change `agent` → **embodied-mortal-agent** → click **Rename**.
3. On the repo page, click the **⚙️** next to "About" and set **Description** to:
   ```
   Embodied agent whose identity exists only while it's running. Death is terminal; restart is a new being.
   ```

Then from this folder run:
```powershell
git push -u origin main
```

If you have a GitHub Personal Access Token (repo scope), you can instead run:
```powershell
$env:GITHUB_TOKEN = "your_token_here"
.\scripts\github-rename-and-description.ps1
```
That will rename and set the description via the API.
