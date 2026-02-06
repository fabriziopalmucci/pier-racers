import os
import sys
import random
import math
import pygame

# -----------------------------
# Config (RIPRISTINATA come prima)
# -----------------------------
WIDTH, HEIGHT = 900, 600
FPS = 60

HORIZON_Y = int(HEIGHT * 0.28)
BOTTOM_Y  = int(HEIGHT * 0.98)
ROAD_NEAR_W = int(WIDTH * 0.80)
ROAD_FAR_W  = int(WIDTH * 0.18)

SPAWN_MS = 520
RAMP_CHANCE = 0.25

SPRITE_ROT_DEG = 0

# Day/Night
DAY_NIGHT_HALF = 60.0  # ogni 60s si va da giorno a notte (e viceversa), smooth su 120s totale

pygame.init()
pygame.display.set_caption("Riders - NYC Day/Night + Lamps")
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)
big_font = pygame.font.SysFont(None, 64)

def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t

def draw_text(surf, text, x, y, color=(10, 10, 10), center=False, fnt=None):
    fnt = fnt or font
    img = fnt.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surf.blit(img, rect)

# -----------------------------
# Assets
# -----------------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

def load_png(filename, fallback_size, color, colorkey=None):
    path = os.path.join(ASSETS_DIR, filename)
    try:
        img = pygame.image.load(path).convert_alpha()
        if colorkey is not None:
            img.set_colorkey(colorkey)
        return img
    except Exception:
        surf = pygame.Surface(fallback_size, pygame.SRCALPHA)
        pygame.draw.rect(surf, color, (0, 0, fallback_size[0], fallback_size[1]), border_radius=12)
        return surf

def load_bg(filename):
    path = os.path.join(ASSETS_DIR, filename)
    try:
        img = pygame.image.load(path).convert()
        return pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
    except Exception:
        bg = pygame.Surface((WIDTH, HEIGHT))
        bg.fill((170, 220, 255))
        return bg

def rotate(img, deg):
    return img if deg == 0 else pygame.transform.rotate(img, deg)

PLAYER_IMG = load_png("car_player.png", (260, 220), (220, 40, 40), colorkey=None)
RAMP_IMG   = load_png("ramp_blue.png",  (280, 200), (70, 130, 255), colorkey=None)

SUV1_IMG   = load_png("suv_black_1.png", (260, 220), (35, 35, 40), colorkey=None)
SUV2_IMG   = load_png("suv_green.png",   (260, 220), (20, 120, 60), colorkey=None)

BG_IMG = load_bg("nyc_bg.png")

# Lampione (NUOVO) - deve stare in assets/lamp_post.png
LAMP_IMG = load_png("lamp_post.png", (240, 480), (0, 0, 0), colorkey=None)

# -----------------------------
# Road geometry
# -----------------------------
def road_half_width_at_y(y):
    t = clamp((y - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0.0, 1.0)
    w = lerp(ROAD_FAR_W, ROAD_NEAR_W, t)
    return w / 2

def draw_road(surf, t_ms):
    far_half = ROAD_FAR_W / 2
    near_half = ROAD_NEAR_W / 2

    pts = [
        (WIDTH/2 - far_half, HORIZON_Y),
        (WIDTH/2 + far_half, HORIZON_Y),
        (WIDTH/2 + near_half, BOTTOM_Y),
        (WIDTH/2 - near_half, BOTTOM_Y),
    ]

    # Asfalto più chiaro (per distinguere bene le macchine)
    pygame.draw.polygon(surf, (70, 70, 76), pts)

    # Bordi bianchi
    pygame.draw.line(surf, (245, 245, 245), pts[0], pts[3], 6)
    pygame.draw.line(surf, (245, 245, 245), pts[1], pts[2], 6)

    # Linea centrale NERA (dash)
    dash_len, gap = 26, 18
    offset = int((t_ms * 0.28) % (dash_len + gap))
    for y in range(HORIZON_Y + 15, int(BOTTOM_Y) + 120, dash_len + gap):
        yy = y + offset
        pygame.draw.rect(surf, (10, 10, 10), (WIDTH/2 - 4, yy, 8, dash_len), border_radius=4)

# -----------------------------
# Day/Night smooth
# -----------------------------
def night_amount_from_time(t_seconds: float) -> float:
    # ciclo 120s: 0=giorno, 60=notte, 120=giorno
    period = DAY_NIGHT_HALF * 2.0
    x = (t_seconds % period) / period  # 0..1
    # cos wave: 0->1->0 smooth
    return 0.5 - 0.5 * math.cos(2.0 * math.pi * x)

def apply_night_overlay(surf, night_amt: float):
    # overlay più morbido (non ammazza tutto)
    alpha = int(140 * night_amt)
    if alpha <= 0:
        return
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((0, 0, 0, alpha))
    surf.blit(ov, (0, 0))

# -----------------------------
# Lampioni (FIX: non blob neri)
#  - scala più grande
#  - disegnati DOPO overlay notte, così restano leggibili
#  - piede sulla linea bianca
# -----------------------------
def draw_lamps(surf, t_ms, night_amt):
    if LAMP_IMG is None:
        return

    # movimento (come “scorrimento” verso il basso)
    scroll = int((t_ms * 0.22) % 120)

    # posizioni Y in schermata (dal basso verso l’orizzonte)
    step = 90
    for y in range(int(BOTTOM_Y) + 50, int(HORIZON_Y) - 40, -step):
        yy = y - scroll
        if yy < HORIZON_Y - 60 or yy > HEIGHT + 120:
            continue

        t = clamp((yy - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0.0, 1.0)
        half = road_half_width_at_y(yy)

        # piede sulla linea bianca: x = bordo strada
        left_edge  = int(WIDTH/2 - half)
        right_edge = int(WIDTH/2 + half)

        # lampione appena “dentro” il bordo (così sembra partire dalla strada)
        lx = left_edge + 2
        rx = right_edge - 2

        # scala: PIÙ GRANDE (prima era troppo piccola -> blob)
        scale = lerp(0.22, 0.62, t)  # lontano 0.22, vicino 0.62

        w = max(18, int(LAMP_IMG.get_width() * scale))
        h = max(18, int(LAMP_IMG.get_height() * scale))
        img = pygame.transform.smoothscale(LAMP_IMG, (w, h))

        # ancoraggio: midbottom = piede a terra sulla linea bianca
        rL = img.get_rect(midbottom=(lx, int(yy)))
        rR = img.get_rect(midbottom=(rx, int(yy)))

        surf.blit(img, rL)
        surf.blit(img, rR)

        # glow notturno (solo notte)
        if night_amt > 0.05:
            glow_strength = night_amt * lerp(0.25, 1.0, t)
            glow_r = int(lerp(10, 40, t))
            # punto lampada ~ parte alta a destra del lampione
            bulbL = (rL.centerx + int(w * 0.32), rL.centery - int(h * 0.30))
            bulbR = (rR.centerx + int(w * 0.32), rR.centery - int(h * 0.30))
            draw_glow(surf, bulbL, glow_r, glow_strength)
            draw_glow(surf, bulbR, glow_r, glow_strength)

def draw_glow(surf, pos, radius, strength):
    x, y = pos
    alpha = int(140 * strength)
    if alpha <= 0:
        return
    blob = pygame.Surface((radius*4, radius*4), pygame.SRCALPHA)
    pygame.draw.circle(blob, (255, 235, 190, alpha), (radius*2, radius*2), radius*2)
    surf.blit(blob, blob.get_rect(center=(x, y)))

# -----------------------------
# Entities
# -----------------------------
class Player:
    def __init__(self):
        self.lane_x = 0.0
        self.steer_speed = 1.75
        self.y = int(HEIGHT * 0.78)

        self.air = 0.0
        self.v_air = 0.0
        self.gravity = 2.9
        self.jump_strength = 1.35
        self.on_ground = True

        # pre-scale (puoi regolare qui se vuoi)
        base_w = int(PLAYER_IMG.get_width() * 0.45)
        base_h = int(PLAYER_IMG.get_height() * 0.45)
        self.img = pygame.transform.smoothscale(PLAYER_IMG, (base_w, base_h))
        self.img = rotate(self.img, SPRITE_ROT_DEG)

    def jump(self, mult=1.0):
        if self.on_ground:
            self.v_air = self.jump_strength * mult
            self.on_ground = False

    def update(self, dt, keys):
        steer = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            steer -= 1.0
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            steer += 1.0
        self.lane_x = clamp(self.lane_x + steer * self.steer_speed * dt, -0.98, 0.98)

        if not self.on_ground:
            self.air += self.v_air * dt * 2.2
            self.v_air -= self.gravity * dt * 2.2
            if self.air <= 0.0:
                self.air = 0.0
                self.v_air = 0.0
                self.on_ground = True

    def screen_x(self):
        half = road_half_width_at_y(self.y)
        return int(WIDTH/2 + self.lane_x * half)

    def draw(self, surf):
        x = self.screen_x()
        # NIENTE ombra (per non sembrare sospesa)
        lift = int(70 * self.air)
        surf.blit(self.img, self.img.get_rect(center=(x, self.y - lift)))

class Thing:
    def __init__(self, kind):
        self.kind = kind  # "suv" or "ramp"

        lanes = [-0.70, -0.25, 0.25, 0.70]
        self.lane_x = random.choice(lanes) + random.uniform(-0.12, 0.12)
        self.lane_x = clamp(self.lane_x, -0.95, 0.95)

        self.d = 1.0 + random.uniform(0.02, 0.15)
        self.variant = random.choice([1, 2]) if kind == "suv" else 0

    def update(self, dt, speed):
        self.d -= speed * dt

    def is_dead(self):
        return self.d < -0.20

    def screen_pos_and_scale(self):
        t = clamp(1.0 - self.d, 0.0, 1.0)
        y = lerp(HORIZON_Y + 20, int(HEIGHT * 0.82), t)

        half = road_half_width_at_y(y)
        x = WIDTH/2 + self.lane_x * half

        scale = lerp(0.20, 0.85, t)
        return int(x), int(y), scale

    def draw(self, surf):
        x, y, scale = self.screen_pos_and_scale()

        if self.kind == "suv":
            src = SUV1_IMG if self.variant == 1 else SUV2_IMG
            w = max(34, int(src.get_width() * 0.22 * scale))
            h = max(34, int(src.get_height() * 0.22 * scale))
        else:
            src = RAMP_IMG
            w = max(44, int(src.get_width() * 0.20 * scale))
            h = max(30, int(src.get_height() * 0.20 * scale))

        img = pygame.transform.smoothscale(src, (w, h))
        img = rotate(img, SPRITE_ROT_DEG)
        surf.blit(img, img.get_rect(center=(x, y)))

    def collides_with_player(self, player: Player):
        if not (0.00 <= self.d <= 0.10):
            return False
        px = player.screen_x()
        x, _, _ = self.screen_pos_and_scale()
        return abs(px - x) < 75

# -----------------------------
# Game loop
# -----------------------------
def reset():
    return {
        "player": Player(),
        "things": [],
        "score": 0.0,
        "start_ms": pygame.time.get_ticks(),
        "last_spawn": pygame.time.get_ticks(),
        "game_over": False,
    }

state = reset()
global_start_ms = pygame.time.get_ticks()

while True:
    dt = clock.tick(FPS) / 1000.0
    now = pygame.time.get_ticks()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.KEYDOWN:
            if not state["game_over"]:
                if event.key == pygame.K_SPACE:
                    state["player"].jump()
            else:
                if event.key == pygame.K_r:
                    state = reset()

    keys = pygame.key.get_pressed()

    elapsed = (now - state["start_ms"]) / 1000.0
    speed = 0.85 + 0.020 * elapsed

    if not state["game_over"]:
        state["player"].update(dt, keys)

        if now - state["last_spawn"] > SPAWN_MS:
            kind = "ramp" if random.random() < RAMP_CHANCE else "suv"
            state["things"].append(Thing(kind))
            state["last_spawn"] = now

        for th in state["things"]:
            th.update(dt, speed)

        for th in list(state["things"]):
            if th.collides_with_player(state["player"]):
                if th.kind == "ramp":
                    # salto più forte su rampa
                    state["player"].jump(mult=2.0)
                    state["things"].remove(th)
                else:
                    if state["player"].air > 0.28:
                        continue
                    state["game_over"] = True

        state["things"] = [t for t in state["things"] if not t.is_dead()]
        state["score"] += (speed * 120) * dt

    # -----------------------------
    # DRAW
    # -----------------------------
    screen.blit(BG_IMG, (0, 0))
    draw_road(screen, now)

    # entities
    for th in sorted(state["things"], key=lambda t: t.d, reverse=True):
        th.draw(screen)
    state["player"].draw(screen)

    # day/night overlay (prima scurisco la scena)
    global_elapsed = (now - global_start_ms) / 1000.0
    night_amt = night_amount_from_time(global_elapsed)
    apply_night_overlay(screen, night_amt)

    # lampioni DOPO overlay (così non diventano blob neri)
    draw_lamps(screen, now, night_amt)

    # HUD
    draw_text(screen, "RIDERS", 18, 12, color=(0, 0, 0))
    draw_text(screen, "New York", 18, 38, color=(0, 0, 0))
    draw_text(screen, f"Score: {int(state['score'])}", 18, 66, color=(0, 0, 0))
    draw_text(screen, "A/D sterzo  |  SPAZIO salto  |  R restart", 18, HEIGHT-28, color=(0, 0, 0))

    if state["game_over"]:
        draw_text(screen, "GAME OVER", WIDTH//2, HEIGHT//2 - 35, center=True, fnt=big_font, color=(0, 0, 0))
        draw_text(screen, f"Punteggio: {int(state['score'])}", WIDTH//2, HEIGHT//2 + 20, center=True, color=(0, 0, 0))
        draw_text(screen, "Premi R per ricominciare", WIDTH//2, HEIGHT//2 + 52, center=True, color=(0, 0, 0))

    pygame.display.flip()
