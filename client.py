import asyncio
import websockets
import json
import pygame
import time
import glob
import math

# --- IMPORTS SAFEGUARD ---
try: import pygame.font
except ImportError: pass

# --- THEME: STRANGER THINGS ---
COLOR_BG = (10, 5, 15)           
COLOR_WALL = (60, 20, 20)      
COLOR_WAFFLE = (255, 200, 0)     
COLOR_MONSTER_CORE = (180, 0, 0)
COLOR_MONSTER_AURA = (100, 0, 0)
COLOR_TEXT = (220, 40, 40)       

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
PLAYER_SIZE = 40
COIN_SIZE = 15
SIMULATED_LATENCY = 0.2 
INTERPOLATION_OFFSET = 0.3 

def find_linux_font():
    """Manual font finder for Fedora/Linux (Python 3.14 fix)"""
    search_paths = ["/usr/share/fonts/**/*.ttf", "~/.fonts/**/*.ttf"]
    priorities = ["Benguiat.ttf", "LiberationSerif-Bold.ttf", "arial.ttf"]
    found = []
    for pattern in search_paths:
        found.extend(glob.glob(pattern, recursive=True))
    for p in priorities:
        for f in found:
            if p.lower() in f.lower(): return f
    return found[0] if found else None

class GameClient:
    def __init__(self, server_url):
        self.server_url = server_url
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Hawkins Lab - Connecting...")
        
        self.my_id = None
        self.running = True
        self.obstacles = []
        
        self.state_buffer = [] 
        self.incoming_packet_queue = []
        self.current_inputs = {"up": False, "down": False, "left": False, "right": False}

        # Fonts
        self.font = None
        self.font_big = None
        self.use_fallback = False
        try:
            path = find_linux_font()
            if path:
                self.font = pygame.font.Font(path, 24)
                self.font_big = pygame.font.Font(path, 48)
            else:
                self.font = pygame.font.Font(None, 24)
                self.font_big = pygame.font.Font(None, 48)
        except: self.use_fallback = True

    async def connect(self):
        print(f"Attempting connection to {self.server_url}...")
        try:
            async with websockets.connect(self.server_url) as websocket:
                print("Connected successfully.")
                await asyncio.gather(self.receive_loop(websocket), self.game_loop(websocket))
        except Exception as e:
            print(f"Error connecting: {e}")
            print("Check if the Server is running and the IP is correct.")

    async def receive_loop(self, websocket):
        try:
            async for message in websocket:
                data = json.loads(message)
                if data["type"] == "init":
                    self.my_id = data["id"]
                    self.obstacles = data["obstacles"]
                    pygame.display.set_caption(f"Player {self.my_id}")
                    continue
                
                self.incoming_packet_queue.append((time.time(), data))
        except: self.running = False

    def process_packets(self):
        now = time.time()
        while self.incoming_packet_queue:
            arrival, data = self.incoming_packet_queue[0]
            if now - arrival >= SIMULATED_LATENCY:
                self.incoming_packet_queue.pop(0)
                if data["type"] == "state":
                    self.state_buffer.append(data)
                    if len(self.state_buffer) > 20: self.state_buffer.pop(0)
            else: break

    def get_interpolated_state(self):
        render_time = time.time() - INTERPOLATION_OFFSET
        if len(self.state_buffer) < 2: return None if not self.state_buffer else self.state_buffer[-1]
        
        prev, next_s = self.state_buffer[0], None
        for state in self.state_buffer:
            if state["t"] > render_time:
                next_s = state
                break
            prev = state
        
        if not next_s: return prev
        
        dt_frame = next_s["t"] - prev["t"]
        alpha = 0 if dt_frame == 0 else (render_time - prev["t"]) / dt_frame
        alpha = max(0.0, min(1.0, alpha))
        
        interp_players = {}
        for pid in set(prev["players"]) | set(next_s["players"]):
            if pid in prev["players"] and pid in next_s["players"]:
                p1, p2 = prev["players"][pid], next_s["players"][pid]
                interp_players[pid] = {
                    "x": p1["x"] + (p2["x"] - p1["x"]) * alpha,
                    "y": p1["y"] + (p2["y"] - p1["y"]) * alpha,
                    "c": p2["c"], "s": p2["s"]
                }
            elif pid in next_s["players"]:
                interp_players[pid] = next_s["players"][pid]
        
        m1, m2 = prev["monster"], next_s["monster"]
        interp_monster = {
            "x": m1["x"] + (m2["x"] - m1["x"]) * alpha,
            "y": m1["y"] + (m2["y"] - m1["y"]) * alpha,
            "radius": m2["radius"]
        }

        return {
            "status": next_s["status"], "time": next_s["time"],
            "score": next_s["score"], "target": next_s["target"],
            "players": interp_players, "coins": next_s["coins"],
            "monster": interp_monster
        }

    def draw_text(self, text, x, y, color=COLOR_TEXT, center=False, big=False):
        if self.use_fallback or not self.font: return
        try:
            f = self.font_big if big else self.font
            surf = f.render(str(text), True, color)
            if center:
                rect = surf.get_rect(center=(x, y))
                self.screen.blit(surf, rect)
            else:
                self.screen.blit(surf, (x, y))
        except: pass

    def draw_monster_tentacles(self, m):
        cx, cy, r = int(m["x"]), int(m["y"]), int(m["radius"])
        pygame.draw.circle(self.screen, COLOR_MONSTER_CORE, (cx, cy), 15)
        pygame.draw.circle(self.screen, COLOR_MONSTER_AURA, (cx, cy), r, 2)
        
        t = time.time() * 5
        for i in range(8):
            angle = (i / 8) * 6.28 + math.sin(t + i) * 0.5
            ex = cx + math.cos(angle) * r
            ey = cy + math.sin(angle) * r
            pygame.draw.line(self.screen, COLOR_MONSTER_AURA, (cx, cy), (ex, ey), 2)

    async def game_loop(self, websocket):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.running = False
            
            keys = pygame.key.get_pressed()
            inputs = {"up": keys[pygame.K_UP], "down": keys[pygame.K_DOWN],
                      "left": keys[pygame.K_LEFT], "right": keys[pygame.K_RIGHT]}
            
            if inputs != self.current_inputs:
                self.current_inputs = inputs
                try: await websocket.send(json.dumps({"type": "input", "inputs": inputs}))
                except: pass

            self.process_packets()
            state = self.get_interpolated_state()
            
            self.screen.fill(COLOR_BG)
            
            for obs in self.obstacles:
                pygame.draw.rect(self.screen, COLOR_WALL, obs)
                pygame.draw.rect(self.screen, (30,10,10), obs, 2)

            if state:
                if state["status"] == "WAITING":
                    self.draw_text("WAITING FOR PLAYER 2...", SCREEN_WIDTH//2, SCREEN_HEIGHT//2, center=True, big=True)
                elif state["status"] == "WON":
                    self.draw_text("YOU SURVIVED!", SCREEN_WIDTH//2, SCREEN_HEIGHT//2, (0, 255, 0), center=True, big=True)
                elif state["status"] == "LOST":
                    self.draw_text("THE MIND FLAYER TOOK YOU", SCREEN_WIDTH//2, SCREEN_HEIGHT//2, (255, 0, 0), center=True, big=True)
                else:
                    for c in state["coins"]:
                        pygame.draw.circle(self.screen, COLOR_WAFFLE, (int(c["x"]), int(c["y"])), COIN_SIZE)
                    
                    self.draw_monster_tentacles(state["monster"])

                    for pid, p in state["players"].items():
                        pygame.draw.rect(self.screen, p["c"], (int(p["x"]), int(p["y"]), PLAYER_SIZE, PLAYER_SIZE))
                        if str(pid) == str(self.my_id):
                             pygame.draw.rect(self.screen, (255, 255, 255), (int(p["x"]), int(p["y"]), PLAYER_SIZE, PLAYER_SIZE), 3)

                    hud_text = f"WAFFLES: {state['score']}/{state['target']}   TIME: {int(state['time'])}"
                    self.draw_text(hud_text, SCREEN_WIDTH//2, 30, center=True)
                    self.draw_text(f"Latency: {int(SIMULATED_LATENCY*1000)}ms", 10, 10, (100, 100, 100))

            pygame.display.flip()
            await asyncio.sleep(1/60)

        pygame.quit()

if __name__ == "__main__":
    print("="*40)
    print("      STRANGER THINGS CLIENT CONFIG")
    print("="*40)
    print("1. Same PC (Connect to localhost)")
    print("2. Different PC (Connect to IP)")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == '2':
        ip = input("Enter Server IP: ").strip()
        url = f"ws://{ip}:8765"
    else:
        url = "ws://localhost:8765"

    client = GameClient(url)
    try: asyncio.run(client.connect())
    except: pass