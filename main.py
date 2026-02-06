import os
import sys
import random
import math
import pygame

# -----------------------------
# Config
# -----------------------------
WIDTH, HEIGHT = 900, 600
FPS = 60

# Prospettiva strada (più bassa e più "larga sotto")
HORIZON_Y = int(HEIGHT * 0.52)      # fine strada più bassa (verso metà schermo)
BOTTOM_Y  = int(HEIGHT * 0.985)

ROAD_NEAR_W = int(WIDTH * 0.94)     # ancora più larga sotto
ROAD_FAR_W  = int(WIDTH * 0.10)     # più stretta sopra

SPAWN_MS = 520
RAMP_CHANCE = 0.25

# Sprites already face forward
SPRITE_ROT_DEG = 0

# Player scaling (ridotta)
PLAYER_DRAW_SCALE = 0.60  # -40% rispetto a 1.0

# Touch/buttons
BTN_SCALE = 2.0  # tasti grandi il doppio

# Lampioni
LAMP_EVERY_PX = 120
LAMP_BASE_Y_OFFSET = 0       # piede esattamente sulla linea bianca
LAMP_NEAR_SCALE = 0.42       # ridotto: altrimenti vedi solo la base
LAMP_FAR_SCALE  = 0.11
LAMP_X_OUTSIDE  = 10         # vicino alla linea bianca

# Day / Night
DAY_NIGHT_SECONDS = 60.0     # cambia ogni 60s, smooth

pygame.init()
pygame.display.set_caption("Riders - NYC Web")
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)
big_font = pygame.font.SysFont(None, 64)

def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t

def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)

def draw_text(surf, text, x, y, color=(10, 10, 10), center=False, fnt=None):
    fnt = fnt or font
    img = fnt.render(text, True, color)
    rect = img.get_rect()
    rect.center = (x, y) if center else (x + rect.w//2, y + rect.h//2) if False else rect.topleft
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
        pygame.draw.rect(surf, (20, 20, 20), (10, 12, fallback_size[0]-20, 22), border_radius=10)
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

# SUV: niente colorkey (devono avere alpha vero nel PNG)
SUV1_IMG   = load_png("suv_black_1.png", (260, 220), (35, 35, 40), colorkey=None)
SUV2_IMG   = load_png("suv_green.png",   (260, 220), (20, 120, 60), colorkey=None)

# NYC background
BG_IMG = load_bg("nyc_bg.png")

# Lampione PNG (quello nuovo)
LAMP_IMG = load_png("lamp_post.png", (240, 480), (0, 0, 0), colorkey=None)

# -----------------------------
# Road geometry
# -----------------------------
def road_half_width_at_y(y):
    t = clamp((y - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0.0, 1.0)
    w = lerp(ROAD_FAR_W, ROAD_NEAR_W, t)
    return w / 2

def road_edge_xs(y):
    half = road_half_width_at_y(y)
    return int(WIDTH/2 - half), int(WIDTH/2 + half)

def draw_road(surf, t_ms):
    far_half = ROAD_FAR_W / 2
    near_half = ROAD_NEAR_W / 2

    pts = [
        (WIDTH/2 - far_half, HORIZON_Y),
        (WIDTH/2 + far_half, HORIZON_Y),
        (WIDTH/2 + near_half, BOTTOM_Y),
        (WIDTH/2 - near_half, BOTTOM_Y),
    ]

    # asfalto più chiaro
    pygame.draw.polygon(surf, (72, 72, 78), pts)

    # linee bianche laterali
    pygame.draw.line(surf, (245, 245, 245), pts[0], pts[3], 6)
    pygame.draw.line(surf, (245, 245, 245), pts[1], pts[2], 6)

    # linea centrale NERA (dash)
    dash_len, gap = 26, 18
    offset = int((t_ms * 0.28) % (dash_len + gap))
    for y in range(HORIZON_Y + 15, int(BOTTOM_Y) + 120, dash_len + gap):
        yy = y + offset
        pygame.draw.rect(surf, (15, 15, 15), (WIDTH/2 - 4, yy, 8, dash_len), border_radius=4)

# -----------------------------
# Lampioni
# -----------------------------
def draw_lamps(surf, t_ms, lamp_img, night_amount):
    """
    Lampioni ai lati: piede appoggiato sulle linee bianche.
    night_amount: 0=giorno, 1=notte
    """
    if lamp_img is None:
        return

    scroll = int((t_ms * 0.22) % LAMP_EVERY_PX)

    y_start = int(BOTTOM_Y) + 60
    y_end   = int(HORIZON_Y) + 12

    for y in range(y_start, y_end, -LAMP_EVERY_PX):
        yy = y - scroll
        if yy < y_end or yy > HEIGHT + 120:
            continue

        t = clamp((yy - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0.0, 1.0)
        left_edge, right_edge = road_edge_xs(yy)

        left_x  = int(left_edge - LAMP_X_OUTSIDE)
        right_x = int(right_edge + LAMP_X_OUTSIDE)

        scale = lerp(LAMP_FAR_SCALE, LAMP_NEAR_SCALE, t)

        w = max(10, int(lamp_img.get_width() * scale))
        h = max(10, int(lamp_img.get_height() * scale))
        img = pygame.transform.smoothscale(lamp_img, (w, h))

        base_y = int(yy - LAMP_BASE_Y_OFFSET)

        r1 = img.get_rect(midbottom=(left_x, base_y))
        r2 = img.get_rect(midbottom=(right_x, base_y))

        surf.blit(img, r1)
        surf.blit(img, r2)

        # alone luce (solo notte, e solo vicino)
        if night_amount > 0.01:
            glow_strength = night_amount * lerp(0.25, 1.0, t)

            # posizione approssimativa "lampadina": in alto a destra del lampione
            # (funziona bene col PNG stile L)
            bulb1 = (r1.centerx + int(w*0.33), r1.centery - int(h*0.28))
            bulb2 = (r2.centerx + int(w*0.33), r2.centery - int(h*0.28))

            glow_r = int(lerp(10, 42, t))
            draw_light_blob(surf, bulb1, glow_r, glow_strength)
            draw_light_blob(surf, bulb2, glow_r, glow_strength)

def draw_light_blob(surf, pos, radius, strength):
    # semplice alone morbido (alpha), senza additive vero (compatibile web)
    x, y = pos
    alpha = int(120 * strength)
    if alpha <= 0:
        return
    blob = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
    pygame.draw.circle(blob, (255, 235, 180, alpha), (radius, radius), radius)
    blob = pygame.transform.smoothscale(blob, (radius*4, radius*4))
    blob.set_alpha(alpha)
    surf.blit(blob, blob.get_rect(center=(x, y)))

# -----------------------------
# Touch controls (hold to steer)
# -----------------------------
class TouchState:
    def __init__(self):
        self.left = False
        self.right = False
        self.jump = False
        self.restart = False
        self._active_fingers = {}  # finger_id -> role

    def reset_frame_buttons(self):
        self.jump = False
        self.restart = False

    def _role_from_pos(self, x, y, game_over, jump_rect, restart_rect):
        if game_over and restart_rect.collidepoint(x, y):
            return "restart"
        if jump_rect.collidepoint(x, y):
            return "jump"
        # steering zones: left/right halves
        if x < WIDTH * 0.5:
            return "left"
        return "right"

    def handle_down(self, x, y, fid, game_over, jump_rect, restart_rect):
        role = self._role_from_pos(x, y, game_over, jump_rect, restart_rect)
        self._active_fingers[fid] = role
        self._apply_roles()

    def handle_up(self, fid):
        if fid in self._active_fingers:
            del self._active_fingers[fid]
        self._apply_roles()

    def handle_move(self, x, y, fid, game_over, jump_rect, restart_rect):
        if fid not in self._active_fingers:
            return
        role = self._role_from_pos(x, y, game_over, jump_rect, restart_rect)
        self._active_fingers[fid] = role
        self._apply_roles()

    def _apply_roles(self):
        roles = set(self._active_fingers.values())
        self.left = ("left" in roles)
        self.right = ("right" in roles)
        # jump/restart are "edge triggered" per frame in game loop
        self.jump = ("jump" in roles)
        self.restart = ("restart" in roles)

touch = TouchState()

# -----------------------------
# Entities
# -----------------------------
class Player:
    def __init__(self):
        self.lane_x = 0.0
        self.steer_speed = 2.3
        self.y = int(HEIGHT * 0.80)

        self.air = 0.0
        self.v_air = 0.0
        self.gravity = 3.0
        self.jump_strength = 1.55
        self.on_ground = True

        # pre-scale player once
        base_w = int(PLAYER_IMG.get_width() * 0.45 * PLAYER_DRAW_SCALE)
        base_h = int(PLAYER_IMG.get_height() * 0.45 * PLAYER_DRAW_SCALE)
        self.img = pygame.transform.smoothscale(PLAYER_IMG, (base_w, base_h))
        self.img = rotate(self.img, SPRITE_ROT_DEG)

    def jump(self, mult=1.0):
        if self.on_ground:
            self.v_air = self.jump_strength * mult
            self.on_ground = False

    def update(self, dt, keys, touch_state: TouchState):
        steer = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT] or touch_state.left:
            steer -= 1.0
        if keys[pygame.K_d] or keys[pygame.K_RIGHT] or touch_state.right:
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
        lift = int(70 * self.air)  # più realistico, meno "vola"
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
        y = lerp(HORIZON_Y + 18, int(HEIGHT * 0.83), t)

        half = road_half_width_at_y(y)
        x = WIDTH/2 + self.lane_x * half

        scale = lerp(0.20, 0.88, t)  # un filo più grandi
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
# UI Buttons
# -----------------------------
def make_buttons():
    # Pulsanti più in alto (così non coprono strada)
    btn_w = int(120 * BTN_SCALE)
    btn_h = int(50 * BTN_SCALE)

    jump_rect = pygame.Rect(WIDTH - btn_w - 18, HEIGHT - btn_h - 90, btn_w, btn_h)
    restart_rect = pygame.Rect(18, HEIGHT - btn_h - 90, btn_w, btn_h)
    return jump_rect, restart_rect

def draw_button(surf, rect, label, active=False):
    bg = (25, 25, 25, 220) if not active else (55, 55, 55, 240)
    fg = (245, 245, 245)
    box = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(box, bg, (0, 0, rect.w, rect.h), border_radius=16)
    surf.blit(box, rect.topleft)
    # testo grande
    f = pygame.font.SysFont(None, int(34 * BTN_SCALE))
    txt = f.render(label, True, fg)
    surf.blit(txt, txt.get_rect(center=rect.center))

# -----------------------------
# Day/Night computation
# -----------------------------
def day_night_amount(t_seconds):
    """
    0 = giorno, 1 = notte.
    Smooth: ogni 60s passa all'altro stato, con transizione graduale.
    """
    # ciclo 120s: 0-60 day->night, 60-120 night->day
    phase = (t_seconds % (DAY_NIGHT_SECONDS * 2.0)) / (DAY_NIGHT_SECONDS * 2.0)  # 0..1
    if phase < 0.5:
        # day -> night
        t = phase / 0.5
        return smoothstep(t)
    else:
        # night -> day
        t = (phase - 0.5) / 0.5
        return 1.0 - smoothstep(t)

def apply_night_overlay(surf, night_amount):
    # Giorno: più luce; Notte: più buio, ma non totale
    # night_amount=0 -> alpha 0
    # night_amount=1 -> alpha ~150
    alpha = int(150 * night_amount)
    if alpha <= 0:
        return
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((0, 0, 0, alpha))
    surf.blit(ov, (0, 0))

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

while True:
    dt = clock.tick(FPS) / 1000.0
    now = pygame.time.get_ticks()

    jump_rect, restart_rect = make_buttons()
    touch.reset_frame_buttons()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        # Keyboard
        if event.type == pygame.KEYDOWN:
            if not state["game_over"]:
                if event.key == pygame.K_SPACE:
                    state["player"].jump()
            else:
                if event.key == pygame.K_r:
                    state = reset()

        # Mouse (desktop + some mobile browsers)
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            touch.handle_down(mx, my, fid=("mouse", event.button), game_over=state["game_over"],
                              jump_rect=jump_rect, restart_rect=restart_rect)
        if event.type == pygame.MOUSEBUTTONUP:
            touch.handle_up(fid=("mouse", event.button))
        if event.type == pygame.MOUSEMOTION and any(k[0] == "mouse" for k in touch._active_fingers.keys()):
            mx, my = event.pos
            # update all mouse fingers
            for fid in list(touch._active_fingers.keys()):
                if fid[0] == "mouse":
                    touch.handle_move(mx, my, fid, state["game_over"], jump_rect, restart_rect)

        # Finger touch (pygbag)
        if event.type == pygame.FINGERDOWN:
            mx = int(event.x * WIDTH)
            my = int(event.y * HEIGHT)
            touch.handle_down(mx, my, fid=event.finger_id, game_over=state["game_over"],
                              jump_rect=jump_rect, restart_rect=restart_rect)
        if event.type == pygame.FINGERUP:
            touch.handle_up(fid=event.finger_id)
        if event.type == pygame.FINGERMOTION:
            mx = int(event.x * WIDTH)
            my = int(event.y * HEIGHT)
            touch.handle_move(mx, my, fid=event.finger_id, game_over=state["game_over"],
                              jump_rect=jump_rect, restart_rect=restart_rect)

    keys = pygame.key.get_pressed()

    elapsed = (now - state["start_ms"]) / 1000.0
    speed = 0.85 + 0.020 * elapsed

    # Touch buttons edge-triggered
    if not state["game_over"]:
        if touch.jump:
            state["player"].jump()
    else:
        if touch.restart:
            state = reset()

    if not state["game_over"]:
        state["player"].update(dt, keys, touch)

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
                    state["player"].jump(mult=2.1)
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
    # background photo
    screen.blit(BG_IMG, (0, 0))

    # road
    draw_road(screen, now)

    # day/night + lamps
    night_amt = day_night_amount(elapsed)
    draw_lamps(screen, now, LAMP_IMG, night_amt)

    # things (far to near)
    for th in sorted(state["things"], key=lambda t: t.d, reverse=True):
        th.draw(screen)

    # player
    state["player"].draw(screen)

    # overlay night AFTER drawing scene (but before UI)
    apply_night_overlay(screen, night_amt)

    # UI buttons (touch)
    draw_button(screen, jump_rect, "JUMP", active=touch.jump and not state["game_over"])
    if state["game_over"]:
        draw_button(screen, restart_rect, "R", active=touch.restart)

    # HUD
    draw_text(screen, "RIDERS", 18, 12, color=(0, 0, 0))
    draw_text(screen, "New York", 18, 38, color=(0, 0, 0))
    draw_text(screen, f"Score: {int(state['score'])}", 18, 66, color=(0, 0, 0))

    if state["game_over"]:
        draw_text(screen, "GAME OVER", WIDTH//2, HEIGHT//2 - 35, center=True, fnt=big_font, color=(0, 0, 0))
        draw_text(screen, f"Punteggio: {int(state['score'])}", WIDTH//2, HEIGHT//2 + 20, center=True, color=(0, 0, 0))
        draw_text(screen, "Premi R o tasto R", WIDTH//2, HEIGHT//2 + 52, center=True, color=(0, 0, 0))

    pygame.display.flip()
