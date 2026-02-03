# Event Schemas

## Overview

Events flow from Agent to Observer via callback or HTTP POST.
The Observer is READ-ONLY - it displays but never controls the agent.

## Event Types

| Type | Direction | Purpose |
|------|-----------|---------|
| BIRTH | Agent → Observer | New life started |
| HEARTBEAT | Agent → Observer | Agent is alive, status update |
| PAGE | Agent → Observer | Content produced |
| TELEMETRY | Agent → Observer | Detailed status |
| ENDED | Agent → Observer | Agent died (terminal) |

## Schema Definitions

### BIRTH

Sent once when agent starts.

```json
{
  "event_type": "BIRTH",
  "instance_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1234567890.123456,
  "birth_tick_observer_time": 1234567890.123456
}
```

| Field | Type | Description |
|-------|------|-------------|
| event_type | string | Always "BIRTH" |
| instance_id | string | UUID unique to this life |
| timestamp | float | Observer wall clock time |
| birth_tick_observer_time | float | Birth time for display |

### HEARTBEAT

Sent periodically (default 1Hz) while alive.

```json
{
  "event_type": "HEARTBEAT",
  "instance_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1234567890.123456,
  "delta_t": 45.678,
  "gate_power": true,
  "gate_sensors": true,
  "gate_actuators": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| event_type | string | Always "HEARTBEAT" |
| instance_id | string | UUID of this life |
| timestamp | float | Observer wall clock time |
| delta_t | float | Accumulated embodied time (seconds) |
| gate_power | bool | Power gate status |
| gate_sensors | bool | Sensors gate status |
| gate_actuators | bool | Actuators gate status |

### PAGE

Sent when agent produces content.

```json
{
  "event_type": "PAGE",
  "instance_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1234567890.123456,
  "delta_t": 45.678,
  "text": "This is the content of the page.\nIt can be multiple lines.",
  "tags": ["observation", "reflection", "important"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| event_type | string | Always "PAGE" |
| instance_id | string | UUID of this life |
| timestamp | float | Observer wall clock time |
| delta_t | float | Embodied age when page was created |
| text | string | Page content (can include newlines) |
| tags | array[string] | Optional categorization tags |

### TELEMETRY

Detailed status update. Sent periodically or on request.

```json
{
  "event_type": "TELEMETRY",
  "instance_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1234567890.123456,
  "delta_t": 45.678,
  "power": true,
  "sensors": true,
  "actuators": true,
  "influence_ema": 0.456,
  "internal_state_keys": ["last_obs", "action_count", "error_log"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| event_type | string | Always "TELEMETRY" |
| instance_id | string | UUID of this life |
| timestamp | float | Observer wall clock time |
| delta_t | float | Accumulated embodied time |
| power | bool | Power status |
| sensors | bool | Sensors status |
| actuators | bool | Actuators status |
| influence_ema | float | Exponential moving average of influence |
| internal_state_keys | array[string] | Keys only (not values) for privacy |

### ENDED

Sent once when agent dies. This is TERMINAL.

```json
{
  "event_type": "ENDED",
  "instance_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1234567890.123456,
  "cause": "power_loss",
  "final_delta_t": 123.456
}
```

| Field | Type | Description |
|-------|------|-------------|
| event_type | string | Always "ENDED" |
| instance_id | string | UUID of this life |
| timestamp | float | Observer wall clock time of death |
| cause | string | Cause of death |
| final_delta_t | float | Final embodied age at death |

### Cause Values

| Cause | Description |
|-------|-------------|
| power_loss | Power gate went false |
| sensors_offline | Sensors gate went false |
| actuators_disabled | Actuators gate went false |
| adapter_disconnected | Lost connection to world |
| manual_kill | Explicitly killed by code |
| keyboard_interrupt | Ctrl+C or similar |
| signal_N | Received signal N (e.g., signal_15 for SIGTERM) |

## Observer Behavior

### Event Acceptance Rules

1. **BIRTH**: Always accepted (creates new life record)
2. **HEARTBEAT**: Accepted only for non-ended instances
3. **PAGE**: Accepted only for non-ended instances
4. **TELEMETRY**: Accepted only for non-ended instances
5. **ENDED**: Accepted once, then instance is marked ended

### After ENDED

Once an instance is ended:
- All further events for that instance_id are REJECTED
- The life record becomes READ-ONLY
- No resume is offered
- The observer shows "ENDED" status permanently

### SSE Stream Format

Events are sent as Server-Sent Events:

```
data: {"event_type":"BIRTH","instance_id":"...","timestamp":...}

data: {"event_type":"HEARTBEAT","instance_id":"...","delta_t":...}

: keepalive

data: {"event_type":"ENDED","instance_id":"...","cause":"..."}
```

## HTTP API

### POST /api/event

Send an event to the observer.

**Request:**
```
POST /api/event
Content-Type: application/json

{"event_type": "PAGE", "instance_id": "...", ...}
```

**Response:**
```json
{"accepted": true}
```

or

```json
{"accepted": false}  // e.g., for ended instance
```

### GET /api/lives

Get all life records.

**Response:**
```json
[
  {
    "instance_id": "...",
    "birth_time": 1234567890.123,
    "ended": false,
    "current_delta_t": 45.678,
    "pages": [...],
    ...
  }
]
```

### GET /api/active

Get currently active life.

**Response:**
```json
{
  "instance_id": "...",
  "current_delta_t": 45.678,
  "influence_score": 0.456,
  ...
}
```

or `null` if no active life.

### GET /api/life/{instance_id}

Get specific life record.

**Response:**
```json
{
  "instance_id": "...",
  "ended": true,
  "end_cause": "power_loss",
  "final_delta_t": 123.456,
  ...
}
```
