# Observation Playbook

## When to Emit Observation Pages

Emit an observation page when:
- Detecting a significant pattern in sensor data
- Noticing an anomaly or unexpected condition
- Reaching a milestone in embodied age
- The world state changes meaningfully

## Page Format

```
[OBSERVATION @ Δt=X.XXs]

What: Brief description of what was observed
Context: Relevant surrounding conditions
Significance: Why this matters
```

## Frequency

- Don't spam observations
- Quality over quantity
- At least 5 seconds between routine observations
- Immediate emission for critical observations

## Tags

Use these tags for observations:
- `observation` (always)
- `anomaly` (unexpected)
- `milestone` (age-based)
- `critical` (urgent)
