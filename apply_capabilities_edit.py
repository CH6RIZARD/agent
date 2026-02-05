"""One-off: expand CAPABILITIES_STATEMENT in identity.py with explicit capabilities + judgment framing."""
import os
import sys

base = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(base, "mortal_agent", "agent_core", "identity.py")
log_path = os.path.join(base, "apply_capabilities_log.txt")

try:
    with open(path, "r", encoding="utf-8") as f:
        s = f.read()
except Exception as e:
    with open(log_path, "w") as f:
        f.write(str(e) + "\n" + repr(path))
    sys.exit(1)
s = s.replace("\r\n", "\n").replace("\r", "\n")

# Debug: dump snippet to agent_core so we see exact bytes
idx = s.find("Capabilities of this instance")
with open(os.path.join(os.path.dirname(path), "_snippet.txt"), "w", encoding="utf-8") as f:
    f.write(repr(s[max(0, idx - 20) : idx + 120]) if idx >= 0 else "NOT_FOUND")

# Replace in two steps: (1) first line + judgment framing, (2) rest of block
step1_old = '    "Capabilities of this instance (while alive): "'
step1_new = '    "Capabilities of this instance (while alive)—these are capacities you have; you apply them through judgment and context, not as a fixed script. "'
if step1_old in s:
    s = s.replace(step1_old, step1_new, 1)

# Replace the long "Web browsing..." sentence with explicit Code/APIs/GitHub/Web lines
step2_old = (
    '    "Web browsing (unrestricted when pursuing relevant goals): I can fetch any URL (NET_FETCH) and run web searches (WEB_SEARCH). "\n'
    '    "I browse at will—follow links, explore sites, gather information independently; no permission-seeking for basic operations. "\n'
    '    "I use search engines, Wikipedia, news, GitHub, documentation, forums; access real-time information; initiate searches from curiosity and goals. "'
)
step2_new = (
    '    "Code and files: I can read, edit, and write code and other files in the workspace; run terminal commands; create and change artifacts. "\n'
    '    "APIs: I can use registered APIs and register new ones (REGISTER_API, REGISTRY_READ); my tool set can grow within this life. "\n'
    '    "GitHub: I can open and update issues and post comments (create issue, create comment) so my work is visible and traceable. "\n'
    '    "Web: I can fetch any URL (NET_FETCH) and run web searches (WEB_SEARCH); browse at will—follow links, explore sites, gather information; use search engines, docs, forums; initiate searches from curiosity and goals; no permission-seeking for basic operations. "'
)
if step2_old in s:
    s = s.replace(step2_old, step2_new, 1)

# Widen "fetch or search" to "act (fetch, search, edit, post)"
step3_old = "I choose when to fetch or search at intervals"
step3_new = "I choose when to act (fetch, search, edit, post) at intervals"
if step3_old in s:
    s = s.replace(step3_old, step3_new, 1)

# Merge Chat and Observer onto one line
step4_old = '    "Chat: I reply on the controller channel. "\n    "Observer: I emit events to the observer UI. "'
step4_new = '    "Chat: I reply on the controller channel. Observer: I emit events to the observer UI. "'
if step4_old in s:
    s = s.replace(step4_old, step4_new, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(s)
# Write result marker next to identity.py for debugging
done_path = os.path.join(os.path.dirname(path), "_edit_done.txt")
with open(done_path, "w") as f:
    f.write("OK" if step1_old in s or "apply them through judgment" in s else "RAN")
