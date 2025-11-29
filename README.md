# Upside Down Escape

The Upside Down: Multiplayer Survival

A real-time, server-authoritative cooperative game built with Python (asyncio, websockets) and pygame. Players must coordinate to collect waffles and evade a growing "Mind Flayer" entity while navigating L-shaped obstacles. Includes implementation of client-side entity interpolation and simulated network latency (200ms) for resilience testing.

### 1. Init Everything

```bash
python -m venv venv

source ./venv/bin/activate

pip install -r requirements.txt
```

### 2. Start Game

Start the server:

```bash
# on PC 1: Terminal 1
python server.py
```

Start Player 1:

```bash
# on PC 1: Terminal 2
python client.py
```

Start Player 2:

```bash
# on PC 2: Terminal 1 (or) PC1: Terminal 3
python client.py
```
