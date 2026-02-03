# 3D Engine Integration Guide

## Overview

The Mortal Agent can connect to 3D engines (Unity, Unreal) via the WorldAdapter interface.

**Key Principle**: The world persists. The agent is mortal.

The 3D engine maintains world state. The agent lives and dies within that world.

## Architecture

```
┌─────────────────────┐      UDP/WebSocket      ┌─────────────────────┐
│    Mortal Agent     │◄───────────────────────►│   3D Engine         │
│                     │                          │   (Unity/Unreal)    │
│  - WorldAdapter     │    Gate Signals          │                     │
│  - Identity (RAM)   │◄─────────────────────────│  - Power state      │
│  - Decision loop    │                          │  - Sensor state     │
│                     │    Observations          │  - Actuator state   │
│                     │◄─────────────────────────│                     │
│                     │                          │  - Camera feed      │
│                     │    Actions               │  - IMU data         │
│                     │─────────────────────────►│  - Position/Rot     │
│                     │                          │                     │
│                     │                          │  - Motor commands   │
│                     │                          │  - Movement         │
└─────────────────────┘                          └─────────────────────┘
```

## Swapping SimAdapter for UnityAdapter/UnrealAdapter

### Step 1: Install the appropriate adapter

```python
# Before (SimAdapter)
from adapters import SimAdapter
adapter = SimAdapter()

# After (UnityAdapter)
from adapters.unity_adapter import UnityAdapter
adapter = UnityAdapter(
    host="127.0.0.1",
    send_port=5005,   # Agent -> Unity
    recv_port=5006    # Unity -> Agent
)
adapter.connect()

# Or (UnrealAdapter)
from adapters.unreal_adapter import UnrealAdapter
adapter = UnrealAdapter(
    host="127.0.0.1",
    port=8765  # WebSocket port
)
adapter.connect()
```

### Step 2: Configure the 3D engine

See engine-specific sections below.

### Step 3: Run the agent

```python
agent = MortalAgent(
    adapter=adapter,
    observer_callback=observer_callback
)
agent.start()
```

## Message Contract

### Agent -> Engine: Action Packet

```json
{
  "type": "action",
  "timestamp": 1234567890.123,
  "action": {
    "motor_commands": {
      "left_wheel": 0.5,
      "right_wheel": 0.5
    },
    "movement": {
      "dx": 0.1,
      "dy": 0.0,
      "dz": 0.0
    },
    "rotation": {
      "dyaw": 0.05
    },
    "custom": {
      "grab": false,
      "speak": "Hello world"
    }
  }
}
```

### Engine -> Agent: Status Update

```json
{
  "gate": {
    "power": true,
    "sensors": true,
    "actuators": true
  },
  "observation": {
    "timestamp": 1234567890.123,
    "position": {"x": 10.5, "y": 0.0, "z": -5.2},
    "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 1.57},
    "imu": {
      "accel_x": 0.0,
      "accel_y": 0.0,
      "accel_z": -9.8,
      "gyro_x": 0.0,
      "gyro_y": 0.0,
      "gyro_z": 0.0
    },
    "camera": "base64-encoded-image-data",
    "custom": {
      "nearby_objects": ["tree", "rock"],
      "health": 100
    }
  },
  "influence": 0.5
}
```

## Embodied Gate Mapping

The 3D engine controls the agent's embodied gate:

| Gate Signal | Engine Condition |
|-------------|------------------|
| `power` | Character alive, not paused, not despawned |
| `sensors` | Camera/sensors active, not blind/deaf |
| `actuators` | Not paralyzed, not frozen, can move |

### Death Triggers

When any of these occur, set the corresponding gate signal to `false`:

- **Power Loss**:
  - Character dies
  - Player quits
  - Server disconnects
  - Game closes

- **Sensors Offline**:
  - Blinded effect
  - Camera disabled
  - Sensor damage

- **Actuators Disabled**:
  - Paralysis effect
  - Frozen/stunned
  - Motor damage

## Unity Integration

### Setup

1. Install a UDP socket plugin or use built-in `UdpClient`
2. Create a `AgentBridge` MonoBehaviour:

```csharp
using System.Net;
using System.Net.Sockets;
using UnityEngine;

public class AgentBridge : MonoBehaviour
{
    public int sendPort = 5006;  // To agent
    public int recvPort = 5005;  // From agent

    private UdpClient sendClient;
    private UdpClient recvClient;

    void Start()
    {
        sendClient = new UdpClient();
        recvClient = new UdpClient(recvPort);
        recvClient.BeginReceive(OnReceive, null);
    }

    void Update()
    {
        // Send status update
        var status = new {
            gate = new {
                power = IsAlive(),
                sensors = HasSensors(),
                actuators = CanMove()
            },
            observation = GetObservation(),
            influence = GetInfluence()
        };

        string json = JsonUtility.ToJson(status);
        byte[] data = System.Text.Encoding.UTF8.GetBytes(json);
        sendClient.Send(data, data.Length, "127.0.0.1", sendPort);
    }

    void OnReceive(IAsyncResult result)
    {
        IPEndPoint ep = null;
        byte[] data = recvClient.EndReceive(result, ref ep);
        string json = System.Text.Encoding.UTF8.GetString(data);

        // Parse and apply action
        var action = JsonUtility.FromJson<ActionPacket>(json);
        ApplyAction(action);

        recvClient.BeginReceive(OnReceive, null);
    }
}
```

### Gate Signal Sources

```csharp
bool IsAlive() => character.health > 0 && !GameManager.isPaused;
bool HasSensors() => !character.isBlinded && camera.enabled;
bool CanMove() => !character.isParalyzed && !character.isFrozen;
```

## Unreal Integration

### Setup

1. Enable WebSocket plugin
2. Create an Actor with WebSocket component:

```cpp
// AgentBridge.h
UCLASS()
class AAgentBridge : public AActor
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere)
    int32 WebSocketPort = 8765;

    void SendStatusUpdate();
    void OnActionReceived(const FString& Json);

private:
    IWebSocket* Socket;
};

// AgentBridge.cpp
void AAgentBridge::SendStatusUpdate()
{
    FString Json = FString::Printf(
        TEXT("{\"gate\":{\"power\":%s,\"sensors\":%s,\"actuators\":%s},...}"),
        IsAlive() ? TEXT("true") : TEXT("false"),
        HasSensors() ? TEXT("true") : TEXT("false"),
        CanMove() ? TEXT("true") : TEXT("false")
    );

    Socket->Send(Json);
}
```

## Testing Integration

1. Start the observer:
   ```bash
   python -m cli.main observe --port 8080
   ```

2. Start the agent with engine adapter:
   ```python
   adapter = UnityAdapter()  # or UnrealAdapter()
   adapter.connect()
   agent = MortalAgent(adapter=adapter, observer_callback=callback)
   agent.start()
   ```

3. Start the 3D engine with AgentBridge

4. Verify in observer UI:
   - BIRTH event received
   - Gate signals showing
   - Delta_t incrementing
   - Actions being applied in engine

5. Test death:
   - Kill character in engine
   - Verify ENDED event
   - Verify agent process exits
   - Verify observer shows ENDED status

## Common Issues

### Agent not connecting

- Check firewall settings
- Verify ports match between agent and engine
- Check that engine is sending/receiving on correct addresses

### Gate always closed

- Engine may not be sending status updates
- Check JSON format matches expected schema
- Enable debug logging in adapter

### Actions not applying

- Check action JSON format
- Verify engine is processing received actions
- Check that actuators gate is true

### Agent not dying when character dies

- Ensure engine sets `power: false` immediately on death
- Check that agent receives the update before process ends
- The death must be near-instant (within one tick)
