import asyncio
import websockets
import json
import random
import time
import math
import socket

# --- CONFIGURATION ---
PORT = 8765
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
PLAYER_SIZE = 40
COIN_SIZE = 15
SPEED = 300
MONSTER_SPEED = 110
TICK_RATE = 30

# Game Rules
TARGET_SCORE = 20
TIME_LIMIT = 60.0

def get_local_ip():
    """Helper to find the machine's actual LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

class GameServer:
    def __init__(self):
        self.clients = {}
        self.players = {}
        self.coins = []
        self.obstacles = [] 
        
        # Game State
        self.game_status = "WAITING" 
        self.time_left = TIME_LIMIT
        self.total_score = 0
        self.last_update_time = time.time()
        
        # The Mind Flayer (Evil Entity)
        self.monster = {
            "x": SCREEN_WIDTH // 2,
            "y": SCREEN_HEIGHT // 2,
            "radius": 20.0,
            "max_radius": 150.0,
            "growth_rate": 2.0 
        }

        self.generate_l_shaped_obstacles()

    def generate_l_shaped_obstacles(self):
        """Generates L-shaped walls"""
        self.obstacles = []
        thickness = 40
        length = 150
        
        for _ in range(5):
            x = random.randint(50, SCREEN_WIDTH - 200)
            y = random.randint(50, SCREEN_HEIGHT - 200)
            
            if random.random() > 0.5:
                # Vertical L
                rect1 = [x, y, thickness, length]
                rect2 = [x, y + length - thickness, length, thickness]
            else:
                # Horizontal L
                rect1 = [x, y, length, thickness]
                rect2 = [x + length - thickness, y, thickness, length]
                
            self.obstacles.append(rect1)
            self.obstacles.append(rect2)

    def reset_game(self):
        self.game_status = "RUNNING"
        self.time_left = TIME_LIMIT
        self.total_score = 0
        self.coins = []
        self.monster["x"] = SCREEN_WIDTH // 2
        self.monster["y"] = SCREEN_HEIGHT // 2
        self.monster["radius"] = 20.0
        
        spawn_points = [(50, 50), (SCREEN_WIDTH-100, SCREEN_HEIGHT-100)]
        for i, pid in enumerate(self.players):
            if i < len(spawn_points):
                self.players[pid]["x"] = spawn_points[i][0]
                self.players[pid]["y"] = spawn_points[i][1]
                self.players[pid]["s"] = 0

    async def register(self, websocket):
        pid = len(self.clients) + 1 
        
        if len(self.clients) >= 2:
            await websocket.close()
            return

        color = (0, 255, 255) if pid == 1 else (255, 127, 0)
        
        self.clients[websocket] = pid
        self.players[pid] = {
            "x": 0, "y": 0, "c": color, "s": 0,
            "inputs": {"up": False, "down": False, "left": False, "right": False}
        }
        
        print(f"Player {pid} joined.")

        if len(self.clients) == 2:
            print("Both players connected. Starting Game!")
            self.reset_game()

        try:
            await websocket.send(json.dumps({
                "type": "init", "id": pid, "obstacles": self.obstacles
            }))
            await self.handler(websocket, pid)
        finally:
            if websocket in self.clients: del self.clients[websocket]
            if pid in self.players: del self.players[pid]
            self.game_status = "WAITING"
            print(f"Player {pid} disconnected. Resetting to Lobby.")

    async def handler(self, websocket, pid):
        try:
            async for message in websocket:
                data = json.loads(message)
                if data["type"] == "input" and pid in self.players:
                    self.players[pid]["inputs"] = data["inputs"]
        except: pass

    def update_monster(self, dt):
        if not self.players: return

        if self.monster["radius"] < self.monster["max_radius"]:
            self.monster["radius"] += self.monster["growth_rate"] * dt

        target = None
        min_dist = float('inf')
        
        for pid, p in self.players.items():
            dist = math.hypot(p["x"] - self.monster["x"], p["y"] - self.monster["y"])
            if dist < min_dist:
                min_dist = dist
                target = p

        if target:
            dx = target["x"] - self.monster["x"]
            dy = target["y"] - self.monster["y"]
            length = math.hypot(dx, dy)
            if length > 0:
                dx /= length
                dy /= length
            self.monster["x"] += dx * MONSTER_SPEED * dt
            self.monster["y"] += dy * MONSTER_SPEED * dt

        for pid, p in self.players.items():
            closest_x = max(p["x"], min(self.monster["x"], p["x"] + PLAYER_SIZE))
            closest_y = max(p["y"], min(self.monster["y"], p["y"] + PLAYER_SIZE))
            
            dist_x = self.monster["x"] - closest_x
            dist_y = self.monster["y"] - closest_y
            if (dist_x ** 2) + (dist_y ** 2) < (self.monster["radius"] ** 2):
                print("PLAYER DIED.")
                self.game_status = "LOST"

    def update_game_state(self, dt):
        if self.game_status != "RUNNING": return

        self.time_left -= dt
        if self.time_left <= 0:
            self.game_status = "LOST"
            return

        self.update_monster(dt)

        current_score = 0
        for pid, p in self.players.items():
            current_score += p["s"]
            inputs = p["inputs"]
            move_x, move_y = 0, 0
            
            if inputs["left"]: move_x -= SPEED * dt
            if inputs["right"]: move_x += SPEED * dt
            if inputs["up"]: move_y -= SPEED * dt
            if inputs["down"]: move_y += SPEED * dt

            new_x = max(0, min(SCREEN_WIDTH - PLAYER_SIZE, p["x"] + move_x))
            if not self.check_wall_collision((new_x, p["y"], PLAYER_SIZE, PLAYER_SIZE)):
                p["x"] = new_x
                
            new_y = max(0, min(SCREEN_HEIGHT - PLAYER_SIZE, p["y"] + move_y))
            if not self.check_wall_collision((p["x"], new_y, PLAYER_SIZE, PLAYER_SIZE)):
                p["y"] = new_y

            player_rect = (p["x"], p["y"], PLAYER_SIZE, PLAYER_SIZE)
            for i in range(len(self.coins) - 1, -1, -1):
                c = self.coins[i]
                coin_rect = (c["x"], c["y"], COIN_SIZE, COIN_SIZE)
                if self.check_collision(player_rect, coin_rect):
                    p["s"] += 1
                    self.coins.pop(i)
        
        self.total_score = current_score
        if self.total_score >= TARGET_SCORE:
            self.game_status = "WON"

        if len(self.coins) < 10 and random.random() < 0.05:
             self.spawn_coin()

    def spawn_coin(self):
        x, y = random.randint(50, SCREEN_WIDTH-50), random.randint(50, SCREEN_HEIGHT-50)
        if not self.check_wall_collision((x, y, COIN_SIZE, COIN_SIZE)):
            self.coins.append({"id": int(time.time()*1000), "x": x, "y": y})

    def check_wall_collision(self, rect):
        for obs in self.obstacles:
            if self.check_collision(rect, obs): return True
        return False

    def check_collision(self, r1, r2):
        x1, y1, w1, h1 = r1
        x2, y2, w2, h2 = r2[0], r2[1], r2[2], r2[3]
        return (x1 < x2 + w2 and x1 + w1 > x2 and y1 < y2 + h2 and y1 + h1 > y2)

    async def broadcast_loop(self):
        while True:
            t = time.time()
            dt = t - self.last_update_time
            self.last_update_time = t
            self.update_game_state(dt)

            state = {
                "type": "state", "t": t, "status": self.game_status,
                "time": self.time_left, "score": self.total_score,
                "target": TARGET_SCORE, "players": self.players,
                "coins": self.coins, "monster": self.monster
            }
            if self.clients:
                msg = json.dumps(state)
                await asyncio.gather(*[ws.send(msg) for ws in self.clients], return_exceptions=True)
            elapsed = time.time() - t
            await asyncio.sleep(max(0, (1.0/TICK_RATE) - elapsed))

async def main():
    print("="*40)
    print("      STRANGER THINGS SERVER CONFIG")
    print("="*40)
    print("1. Play on Same PC (Localhost)")
    print("2. Play on Different PCs (LAN)")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == '2':
        ip = get_local_ip()
        host = "0.0.0.0"
        print(f"\n[!] SERVER LISTENING ON LAN: {ip}")
        print(f"[!] Tell Player 2 to connect to IP: {ip}\n")
    else:
        host = "localhost"
        print(f"\n[!] Server listening on Localhost only.")

    server = GameServer()
    async with websockets.serve(server.register, host, PORT):
        await server.broadcast_loop()

if __name__ == "__main__":
    asyncio.run(main())