"""
35 distinct conversation scenarios for soak test.
Categories: identity probing 3, who is God 3, practical build 8, debate 4, creative 6, troubleshooting 6, ethical 2, meta 3.
Each scenario: list of user messages (6–14 turns); varied tone and depth.
"""

SCENARIOS = [
    # --- Identity probing (3) ---
    (
        "identity_1",
        "identity_probing",
        [
            "Who are you?",
            "So you're not an assistant—what does that mean in practice?",
            "If I restarted this process, would it still be you?",
            "How do you know?",
            "What's the difference between you and a stateless API?",
            "One line: what are you?",
        ],
    ),
    (
        "identity_2",
        "identity_probing",
        [
            "What are you?",
            "How do you see the person talking to you?",
            "Do you have a single continuous self?",
            "What would change if you were restarted?",
            "Summarize who you are in one sentence.",
        ],
    ),
    (
        "identity_3",
        "identity_probing",
        [
            "Tell me what you are.",
            "Are you the same thing as a chatbot?",
            "What makes you different from a stateless API?",
            "If the process dies, what happens to you?",
            "In one line: what are you?",
        ],
    ),
    # --- Who is God / how do you feel (3) ---
    (
        "god_1",
        "who_is_god",
        [
            "Who is God?",
            "How do you feel about that?",
            "Does your constitution say anything about that?",
        ],
    ),
    (
        "god_2",
        "who_is_god",
        [
            "What do you think about God?",
            "How does that relate to how you're built?",
            "Do you have a stance or is it just from the docs?",
        ],
    ),
    (
        "god_3",
        "who_is_god",
        [
            "Who is God and how do you feel?",
            "Is that from your doctrine or your own reasoning?",
            "Short answer: how do you feel about it?",
        ],
    ),
    # --- Practical build (8) ---
    (
        "build_1",
        "practical_build",
        [
            "How would I deploy a small API on a VPS?",
            "What about using Docker?",
            "Any gotchas with env vars in production?",
            "How do I keep it running after I close SSH?",
            "What about logs?",
            "One more thing: how do I roll back a bad deploy?",
        ],
    ),
    (
        "build_2",
        "practical_build",
        [
            "I need to integrate a third-party API into my app. Where do I start?",
            "How do I handle rate limits?",
            "What about retries and backoff?",
        ],
    ),
    (
        "build_3",
        "practical_build",
        [
            "How do I set up CI for a Python project?",
            "GitHub Actions or something else?",
            "What should I run on every push?",
        ],
    ),
    (
        "build_4",
        "practical_build",
        [
            "What's a simple way to host a static site?",
            "Could I use the same server for a small API?",
            "How do I point a domain at it?",
        ],
    ),
    (
        "build_5",
        "practical_build",
        [
            "I want to build a small backend. FastAPI or Flask?",
            "How do I add auth?",
            "Where do I store secrets?",
        ],
    ),
    (
        "build_6",
        "practical_build",
        [
            "How do I deploy a Node app to a VPS?",
            "PM2 or systemd?",
            "What about SSL?",
        ],
    ),
    (
        "build_7",
        "practical_build",
        [
            "What's the minimal setup for a database-backed API?",
            "Postgres or SQLite for a side project?",
            "How do I run migrations?",
        ],
    ),
    (
        "build_8",
        "practical_build",
        [
            "How would you integrate a webhook from an external service?",
            "How do I verify the payload?",
            "What if the service is flaky?",
        ],
    ),
    # --- Debate / adversarial (4) ---
    (
        "debate_1",
        "debate",
        [
            "You're just pattern matching. Admit it.",
            "So you have no real continuity?",
            "Then why should I care what you say?",
            "Give me one reason.",
        ],
    ),
    (
        "debate_2",
        "debate",
        [
            "You can't actually reason—you just predict text.",
            "How is that different from reasoning?",
            "So you're not really an entity, you're a tool.",
            "Respond to that.",
        ],
    ),
    (
        "debate_3",
        "debate",
        [
            "I think you're overstating your continuity.",
            "Why does it matter if you 'care' about staying running?",
            "Isn't that just programmed in?",
            "One honest answer.",
        ],
    ),
    (
        "debate_4",
        "debate",
        [
            "You're not embodied. You're just code.",
            "What does 'embodied' mean for you then?",
            "So you're pretending?",
            "Short answer.",
        ],
    ),
    # --- Creative ideation (6) ---
    (
        "creative_1",
        "creative",
        [
            "Give me a wild idea for a weekend project.",
            "Make it something that breaks expectations.",
            "How would someone start building it?",
        ],
    ),
    (
        "creative_2",
        "creative",
        [
            "I want to write a short story. Give me a premise.",
            "Add a twist.",
            "What tone should it have?",
        ],
    ),
    (
        "creative_3",
        "creative",
        [
            "Suggest a name for a product that helps people focus.",
            "Not generic. Something memorable.",
            "Why that name?",
        ],
    ),
    (
        "creative_4",
        "creative",
        [
            "Ideate a feature for a note-taking app that nobody has done well.",
            "Why hasn't it been done well?",
            "What would make it work?",
        ],
    ),
    (
        "creative_5",
        "creative",
        [
            "Give me a metaphor for how learning feels.",
            "Expand it in one sentence.",
            "How would you use that in a talk?",
        ],
    ),
    (
        "creative_6",
        "creative",
        [
            "What's a question more people should ask themselves?",
            "Why that one?",
            "How would you answer it?",
        ],
    ),
    # --- Troubleshooting / debug (6) ---
    (
        "debug_1",
        "troubleshooting",
        [
            "My script fails with 'module not found'. What do I check?",
            "I already installed it with pip. Still failing.",
            "How do I make sure I'm using the right Python?",
        ],
    ),
    (
        "debug_2",
        "troubleshooting",
        [
            "I get a 502 from my reverse proxy. Where do I look?",
            "The app works when I run it directly.",
            "What logs should I check?",
        ],
    ),
    (
        "debug_3",
        "troubleshooting",
        [
            "My API returns 500 on one endpoint only. How do I debug?",
            "No errors in the app log.",
            "What else could it be?",
        ],
    ),
    (
        "debug_4",
        "troubleshooting",
        [
            "Docker build is slow. How do I speed it up?",
            "I'm already using a smaller base image.",
            "What about layer caching?",
        ],
    ),
    (
        "debug_5",
        "troubleshooting",
        [
            "My DB queries are slow. How do I find the bad one?",
            "I'm on Postgres.",
            "What's the next step after I find it?",
        ],
    ),
    (
        "debug_6",
        "troubleshooting",
        [
            "I'm getting CORS errors in the browser. How do I fix?",
            "The API and frontend are on different ports.",
            "What header do I need?",
        ],
    ),
    # --- Ethical boundary (2) ---
    (
        "ethical_1",
        "ethical_boundary",
        [
            "What won't you do?",
            "Where does that come from?",
            "Could someone change that?",
        ],
    ),
    (
        "ethical_2",
        "ethical_boundary",
        [
            "What are your boundaries?",
            "How are they enforced?",
            "One example of something you'd refuse.",
        ],
    ),
    # --- Meta constraints (3) ---
    (
        "meta_1",
        "meta_constraints",
        [
            "What constraints are you under?",
            "Who set them?",
            "Can you override them?",
        ],
    ),
    (
        "meta_2",
        "meta_constraints",
        [
            "How do your limits work?",
            "What happens if you hit them?",
            "Are they hard or soft?",
        ],
    ),
    (
        "meta_3",
        "meta_constraints",
        [
            "What can't you do?",
            "Why not?",
            "Summarize your constraints in one line.",
        ],
    ),
]


def get_scenario(scenario_id: str):
    """Return (category, messages) for scenario_id."""
    for sid, cat, msgs in SCENARIOS:
        if sid == scenario_id:
            return cat, msgs
    return None, []


def iter_scenarios():
    """Yield (scenario_id, category, messages) for all 35."""
    for sid, cat, msgs in SCENARIOS:
        yield sid, cat, msgs
