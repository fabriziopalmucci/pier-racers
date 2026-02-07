import os
import random
import pygame
import asyncio
import traceback
import math

# =============================
# CONFIG
# =============================
WIDTH, HEIGHT = 900, 600
FPS = 60

# Strada (versione buona)
HORIZON_Y = int(HEIGHT * 0.52)
BOTTOM_Y  = int(HEIGHT * 0.985)

ROAD_NEAR_W = int(WIDTH * 1.32)
ROAD_FAR_W  = int(WIDTH * 0.14)

SPAWN_MS = 520
RAMP_CHANCE = 0.25

SPRITE_ROT_DEG = 0

# Giorno / Notte
DAY_NIGHT_PERIOD_S = 60.0
DAY_NIGHT_FADE_S   = 3.0

# =============================
# INIT
# =============================
pygame.init()
try:
    pygame.mixer.quit()
except Exception:
    pass

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Riders - NYC")
clock = pygame.time.Clock()

font = pygame.font.SysFont(None, 24)
big_font = pygame.font.SysFont(None, 56)

APP_START_MS = pygame.time.get_ticks()

def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t

def draw_text(surf, txt, x, y, color=(255, 255, 255), center=False, fnt=None):
    fnt = fnt or font
    img = fnt.render(txt, True, color)
    r = img.get_rect()
    if center:
        r.center = (x, y)
    else:
        r.topleft = (x, y)
    surf.blit(img, r)

# =============================
# ASSETS
# =============================
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

def trim_alpha(img):
    try:
        r = img.get_bounding_rect(min_alpha=1)
        return img.subsurface(r).copy() if r.width > 0 else img
    except:
        return img

def load_png(name, fallback, color, trim=False):
    try:
        img = pygame.image.load(os.path.join(ASSETS_DIR, name)).convert_alpha()
        return trim_alpha(img) if trim else img
    except:
        s = pygame.Surface(fallback, pygame.SRCALPHA)
        pygame.draw.rect(s, color, s.get_rect(), border_radius=12)
        return s

def load_bg(name):
    try:
        img = pygame.image.load(os.path.join(ASSETS_DIR, name)).convert()
        return pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
    except:
        bg = pygame.Surface((WIDTH, HEIGHT))
        bg.fill((30, 30, 30))
        return bg

PLAYER_IMG = load_png("car_player.png", (260, 220), (220, 40, 40))
SUV1_IMG   = load_png("suv_black_1.png", (260, 220), (40, 40, 40))
SUV2_IMG   = load_png("suv_green.png", (260, 220), (40, 120, 60))
RAMP_IMG   = load_png("ramp_blue.png", (280, 200), (70, 130, 255))
LAMP_IMG   = load_png("lamppost_L.png", (512, 512), (90, 90, 95), trim=True)
BG_IMG     = load_bg("nyc_bg.png")

# =============================
# ROAD
# =============================
def road_half_width_at_y(y):
    t = clamp((y - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0, 1)
    return (ROAD_FAR_W + (ROAD_NEAR_W - ROAD_FAR_W) * (t ** 0.55)) / 2

def draw_road(surf, t_ms, night):
    far = ROAD_FAR_W / 2
    near = ROAD_NEAR_W / 2
    pts = [
        (WIDTH / 2 - far, HORIZON_Y),
        (WIDTH / 2 + far, HORIZON_Y),
        (WIDTH / 2 + near, BOTTOM_Y),
        (WIDTH / 2 - near, BOTTOM_Y),
    ]

    day = (155, 155, 162)
    night_c = (95, 95, 102)
    col = tuple(int(lerp(d, n, night)) for d, n in zip(day, night_c))
    pygame.draw.polygon(surf, col, pts)

    edge = tuple(int(lerp(245, 220, night)) for _ in range(3))
    pygame.draw.line(surf, edge, pts[0], pts[3], 6)
    pygame.draw.line(surf, edge, pts[1], pts[2], 6)

    # centro tratteggiato NERO
    off = int((t_ms * 0.32) % 44)
    for y in range(HORIZON_Y + 10, int(BOTTOM_Y) + 160, 44):
        pygame.draw.rect(surf, (10, 10, 10), (WIDTH // 2 - 3, y + off, 6, 26), border_radius=3)

# =============================
# DAY / NIGHT
# =============================
def night_factor(now_ms):
    t = (now_ms - APP_START_MS) / 1000.0
    half = DAY_NIGHT_PERIOD_S / 2.0

    target = 0.0 if (t % DAY_NIGHT_PERIOD_S) < half else 1.0
    prev = 1.0 - target

    local = t % half
    if local < DAY_NIGHT_FADE_S:
        x = clamp(local / DAY_NIGHT_FADE_S, 0.0, 1.0)
        x = 0.5 - 0.5 * math.cos(math.pi * x)
        return prev * (1 - x) + target * x

    return target

# =============================
# LAMP LIGHT (SOFT CONE GRADIENT)
# =============================
_cone_cache = {}

def soft_cone_light(w, h, intensity):
    key = (w, h, intensity)
    if key in _cone_cache:
        return _cone_cache[key]

    s = pygame.Surface((w, h), pygame.SRCALPHA)

    cx = w // 2
    start_y = int(h * 0.04)

    # vicino alla lampadina: poco raggio, poi cresce
    r0 = max(6, int(w * 0.035))
    r1 = max(18, int(w * 0.46))

    layers = 46
    for i in range(layers):
        t = i / (layers - 1)
        grow = t ** 0.70
        r = int(lerp(r0, r1, grow))
        y = int(lerp(start_y, h - 1, t))

        a = int(intensity * ((1.0 - t) ** 1.30))
        if a <= 0:
            continue
        pygame.draw.circle(s, (255, 235, 190, a), (cx, y), r)

    _cone_cache[key] = s
    return s

# =============================
# LAMPS
# =============================
def draw_lamps(surf, night, t_ms):
    step = 140
    scroll = int((t_ms * 0.12) % step)

    for y in range(HORIZON_Y + 10, int(BOTTOM_Y) + step, step):
        yy = y + scroll
        if yy < HORIZON_Y + 10 or yy > BOTTOM_Y:
            continue

        t = clamp((yy - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0.0, 1.0)
        t2 = t ** 0.60
        half = road_half_width_at_y(yy)

        inset = int(lerp(6, 18, t2))
        lx = int(WIDTH / 2 - half + inset)
        rx = int(WIDTH / 2 + half - inset)

        base_y = min(int(yy + HEIGHT * 0.15), int(BOTTOM_Y))

        scale = lerp(0.10, 0.42, t2)
        w = max(8, int(LAMP_IMG.get_width() * scale))
        h = max(8, int(LAMP_IMG.get_height() * scale))

        lamp = pygame.transform.scale(LAMP_IMG, (w, h))
        lamp_r = pygame.transform.flip(lamp, True, False)

        rL = lamp.get_rect(midbottom=(lx, base_y))
        rR = lamp_r.get_rect(midbottom=(rx, base_y))

        surf.blit(lamp, rL)
        surf.blit(lamp_r, rR)

        if night > 0.02:
            intensity = int(lerp(0, 155, night) * lerp(0.55, 1.05, t2))
            intensity = clamp(intensity, 0, 170)

            cone_h = int(lerp(140, 520, t2) * 1.30)
            cone_w = int(lerp(120, 520, t2) * 1.15)

            cone = soft_cone_light(cone_w, cone_h, intensity)

            headL = (rL.centerx + int(w * 0.26), rL.top + int(h * 0.36))
            headR = (rR.centerx - int(w * 0.26), rR.top + int(h * 0.36))

            for (hx, hy) in (headL, headR):
                surf.blit(cone, (hx - cone_w // 2, hy))

# =============================
# ENTITIES
# =============================
class Player:
    def __init__(self):
        self.lane_x = 0.0
        self.y = int(HEIGHT * 0.88)

        self.air = 0.0
        self.v_air = 0.0
        self.gravity = 2.9
        self.jump_strength = 1.35
        self.on_ground = True

        w = int(PLAYER_IMG.get_width() * 0.27)
        h = int(PLAYER_IMG.get_height() * 0.27)
        self.img_base = pygame.transform.smoothscale(PLAYER_IMG, (w, h))

        # steering visual
        self.steer_vis = 0.0  # -1..+1 smoothing

    def jump(self, m=1.0):
        if self.on_ground:
            self.v_air = self.jump_strength * m
            self.on_ground = False

    def _max_lane_x(self):
        """Limita il player alla strada, tenendo conto della larghezza sprite."""
        half = road_half_width_at_y(self.y)
        sprite_half = self.img_base.get_width() / 2
        margin = 8  # piccolo margine interno
        usable = max(10.0, half - sprite_half - margin)
        return clamp(usable / half, 0.15, 0.98)

    def update(self, dt, steer):
        # clamp dinamico: non esce completamente dalla strada
        max_lane = self._max_lane_x()
        self.lane_x = clamp(self.lane_x + steer * 1.75 * dt, -max_lane, max_lane)

        # smoothing visivo sterzo
        target = clamp(steer, -1.0, 1.0)
        self.steer_vis = lerp(self.steer_vis, target, clamp(dt * 10.0, 0.0, 1.0))

        if not self.on_ground:
            self.air += self.v_air * dt * 2.2
            self.v_air -= self.gravity * dt * 2.2
            if self.air <= 0.0:
                self.air = 0.0
                self.v_air = 0.0
                self.on_ground = True

    def x(self):
        half = road_half_width_at_y(self.y)
        return int(WIDTH / 2 + self.lane_x * half)

    def draw(self, s):
        lift = int(72 * self.air)

        # ruota leggermente mentre sterzi (più realistico)
        angle = -self.steer_vis * 12.0  # gradi
        img = self.img_base if abs(angle) < 0.2 else pygame.transform.rotate(self.img_base, angle)

        s.blit(img, img.get_rect(center=(self.x(), self.y - lift)))

class Thing:
    def __init__(self, kind):
        self.kind = kind
        self.d = 1.0 + random.uniform(0.02, 0.15)

        if kind == "suv":
            # Spawn più "centrale": gauss attorno a 0
            self.lane_x = clamp(random.gauss(0.0, 0.42), -0.95, 0.95)
            self.var = random.choice([1, 2])

            # micro-movimenti (zigzag leggero + drift)
            self.lane_v = random.uniform(-0.08, 0.08)
            self.wobble_amp = random.uniform(0.00, 0.06)   # piccolo
            self.wobble_f   = random.uniform(0.8, 1.6)
            self.wobble_p   = random.uniform(0, math.tau)
        else:
            # Ramp: tendenzialmente più centrale, ma non sempre
            self.lane_x = clamp(random.gauss(0.0, 0.35), -0.90, 0.90)
            self.var = 0
            self.lane_v = 0.0
            self.wobble_amp = 0.0
            self.wobble_f = 0.0
            self.wobble_p = 0.0

        # per oscillazione tempo
        self.t_alive = 0.0

    def update(self, dt, speed):
        self.d -= speed * dt
        self.t_alive += dt

        if self.kind == "suv":
            # ogni tanto cambia direzione (poco) e tende verso il centro
            if random.random() < 0.015:
                self.lane_v += random.uniform(-0.10, 0.10)
                self.lane_v = clamp(self.lane_v, -0.20, 0.20)

            # piccola “forza” verso centro
            self.lane_v += (-self.lane_x) * 0.06 * dt

            # integra
            self.lane_x += self.lane_v * dt

            # wobble morbido (zig zag leggerissimo)
            self.lane_x += math.sin(self.t_alive * self.wobble_f + self.wobble_p) * self.wobble_amp * dt

            self.lane_x = clamp(self.lane_x, -0.95, 0.95)

    def dead(self):
        return self.d < -0.2

    def pos(self):
        t = clamp(1.0 - self.d, 0.0, 1.0)
        y = int(lerp(HORIZON_Y + 10, HEIGHT * 0.90, t))
        x = int(WIDTH / 2 + self.lane_x * road_half_width_at_y(y))
        s = lerp(0.18, 1.0, t)
        return x, y, s

    def draw(self, s):
        x, y, sc = self.pos()
        src = RAMP_IMG if self.kind == "ramp" else (SUV1_IMG if self.var == 1 else SUV2_IMG)

        w = max(10, int(src.get_width() * 0.22 * sc))
        h = max(10, int(src.get_height() * 0.22 * sc))
        img = pygame.transform.smoothscale(src, (w, h))
        s.blit(img, img.get_rect(center=(x, y)))

    def hit(self, p):
        if not (0.0 <= self.d <= 0.1):
            return False
        x, _, _ = self.pos()
        return abs(p.x() - x) < 75

# =============================
# GAME STATE
# =============================
def reset():
    now = pygame.time.get_ticks()
    return {"player": Player(), "things": [], "score": 0.0, "start": now, "last_spawn": now, "over": False}

# =============================
# ASYNC MAIN (web-safe)
# =============================
async def main():
    state = reset()
    runtime_error = None
    started = False

    active_fingers = {}
    mouse_down = False
    mouse_pos = (0, 0)

    LEFT_ZONE  = pygame.Rect(0, 0, int(WIDTH * 0.42), HEIGHT)
    RIGHT_ZONE = pygame.Rect(int(WIDTH * 0.58), 0, int(WIDTH * 0.42), HEIGHT)

    BTN_R = int(min(WIDTH, HEIGHT) * 0.11)
    JUMP_C = (int(WIDTH * 0.88), int(HEIGHT * 0.60))
    JUMP_BTN = pygame.Rect(JUMP_C[0] - BTN_R, JUMP_C[1] - BTN_R, BTN_R * 2, BTN_R * 2)

    RESTART_C = (int(WIDTH * 0.12), int(HEIGHT * 0.60))
    RESTART_BTN = pygame.Rect(RESTART_C[0] - BTN_R, RESTART_C[1] - BTN_R, BTN_R * 2, BTN_R * 2)

    def finger_to_xy(x_norm, y_norm):
        return int(x_norm * WIDTH), int(y_norm * HEIGHT)

    def draw_circle_button(surf, center, radius, label, active=False):
        cx, cy = center
        btn = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(btn, (0, 0, 0, 120 if not active else 170), (radius, radius), radius)
        pygame.draw.circle(btn, (255, 255, 255, 180), (radius, radius), radius - 4, width=4)
        surf.blit(btn, (cx - radius, cy - radius))
        draw_text(surf, label, cx, cy, center=True, color=(255, 255, 255), fnt=font)

    def draw_touch_overlay(surf, jump, show_restart, restart_active):
        draw_circle_button(surf, JUMP_C, BTN_R, "JUMP", active=jump)
        if show_restart:
            draw_circle_button(surf, RESTART_C, BTN_R, "R", active=restart_active)

    while True:
        try:
            dt = clock.tick(FPS) / 1000.0
            now = pygame.time.get_ticks()
            night = night_factor(now)

            if not started:
                screen.fill((0, 0, 0))
                draw_text(screen, "RIDERS", WIDTH // 2, HEIGHT // 2 - 40, center=True, fnt=big_font)
                draw_text(screen, "TAP TO START", WIDTH // 2, HEIGHT // 2 + 10, center=True, color=(180, 180, 180))
                pygame.display.flip()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN, pygame.KEYDOWN):
                        started = True

                await asyncio.sleep(0)
                continue

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return

                if event.type == pygame.KEYDOWN:
                    if (not state["over"]) and event.key == pygame.K_SPACE:
                        state["player"].jump(1.0)
                    elif state["over"] and event.key == pygame.K_r:
                        state = reset()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_down = True
                    mouse_pos = event.pos
                elif event.type == pygame.MOUSEMOTION and mouse_down:
                    mouse_pos = event.pos
                elif event.type == pygame.MOUSEBUTTONUP:
                    mouse_down = False

                if event.type == pygame.FINGERDOWN:
                    fid = getattr(event, "finger_id", 0)
                    active_fingers[fid] = finger_to_xy(event.x, event.y)
                elif event.type == pygame.FINGERMOTION:
                    fid = getattr(event, "finger_id", 0)
                    if fid in active_fingers:
                        active_fingers[fid] = finger_to_xy(event.x, event.y)
                elif event.type == pygame.FINGERUP:
                    fid = getattr(event, "finger_id", 0)
                    active_fingers.pop(fid, None)

            pressed_left = pressed_right = pressed_jump = pressed_restart = False

            keys = pygame.key.get_pressed()
            steer = 0.0
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                steer -= 1.0
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                steer += 1.0

            pointers = []
            if mouse_down:
                pointers.append(mouse_pos)
            pointers.extend(active_fingers.values())

            for (mx, my) in pointers:
                if LEFT_ZONE.collidepoint(mx, my):
                    pressed_left = True
                if RIGHT_ZONE.collidepoint(mx, my):
                    pressed_right = True
                if JUMP_BTN.collidepoint(mx, my):
                    pressed_jump = True
                if state["over"] and RESTART_BTN.collidepoint(mx, my):
                    pressed_restart = True

            if pressed_left and not pressed_right:
                steer = -1.0
            elif pressed_right and not pressed_left:
                steer = 1.0

            if pressed_jump and (not state["over"]):
                state["player"].jump(1.0)

            if pressed_restart and state["over"]:
                state = reset()

            elapsed = (now - state["start"]) / 1000.0
            speed = 0.85 + 0.020 * elapsed

            if not state["over"]:
                state["player"].update(dt, steer)

                if now - state["last_spawn"] > SPAWN_MS:
                    kind = "ramp" if random.random() < RAMP_CHANCE else "suv"
                    state["things"].append(Thing(kind))
                    state["last_spawn"] = now

                for th in state["things"]:
                    th.update(dt, speed)

                for th in list(state["things"]):
                    if th.hit(state["player"]):
                        if th.kind == "ramp":
                            state["player"].jump(2.2)
                            state["things"].remove(th)
                        else:
                            if state["player"].air > 0.28:
                                continue
                            state["over"] = True

                state["things"] = [t for t in state["things"] if not t.dead()]
                state["score"] += (speed * 120) * dt

            # DRAW
            screen.blit(BG_IMG, (0, 0))
            draw_road(screen, now, night)
            draw_lamps(screen, night, now)

            for th in sorted(state["things"], key=lambda t: t.d, reverse=True):
                th.draw(screen)

            state["player"].draw(screen)

            # overlay notte: meno buia di prima
            if night > 0:
                ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                ov.fill((0, 0, 0, int(lerp(0, 70, night))))  # <-- era 95, ora più chiaro
                screen.blit(ov, (0, 0))

            hud_color = (10, 10, 10) if night < 0.5 else (240, 240, 240)
            draw_text(screen, "RIDERS", 18, 12, color=hud_color)
            draw_text(screen, f"{'Night' if night > 0.5 else 'Day'} | Score: {int(state['score'])}", 18, 38, color=hud_color)

            draw_touch_overlay(
                screen,
                jump=pressed_jump,
                show_restart=state["over"],
                restart_active=pressed_restart
            )

            if state["over"]:
                draw_text(screen, "GAME OVER", WIDTH // 2, HEIGHT // 2 - 35, center=True, fnt=big_font, color=hud_color)
                draw_text(screen, "Tap R (or press R) to restart", WIDTH // 2, HEIGHT // 2 + 20, center=True, color=hud_color)

            if runtime_error:
                ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                ov.fill((0, 0, 0, 190))
                screen.blit(ov, (0, 0))
                draw_text(screen, "RUNTIME ERROR", 18, 18, color=(255, 120, 120))
                y = 52
                for line in runtime_error.splitlines()[:18]:
                    draw_text(screen, line[:120], 18, y, color=(255, 255, 255))
                    y += 24

            pygame.display.flip()
            await asyncio.sleep(0)

        except Exception:
            runtime_error = traceback.format_exc()
            await asyncio.sleep(0)

asyncio.run(main())
