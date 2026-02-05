"""One-off patch: add NOT read-only sentence to CAPABILITIES_STATEMENT in identity.py"""
import os
base = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(base, "mortal_agent", "agent_core", "identity.py")
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = (
    '    "Capabilities of this instance (while alive): "\n'
    '    "Web browsing (unrestricted when pursuing relevant goals): I can fetch any URL (NET_FETCH) and run web searches (WEB_SEARCH). "'
)
new = (
    '    "Capabilities of this instance (while alive): "\n'
    '    "I am NOT read-only: I can edit code, write files, register and use APIs, and when deploy-enabled post on GitHub. "\n'
    '    "Web browsing (unrestricted when pursuing relevant goals): I can fetch any URL (NET_FETCH) and run web searches (WEB_SEARCH). "'
)
result_path = os.path.join(base, "_patch_result.txt")
with open(result_path, "w") as out:
    if old not in content:
        out.write("Pattern not found")
    else:
        content = content.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        out.write("OK")
