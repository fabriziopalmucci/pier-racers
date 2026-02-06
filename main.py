import os
import random
import pygame
import asyncio
import traceback

# -----------------------------
# Config
# -----------------------------
WIDTH, HEIGHT = 900, 600
FPS = 60

# Strada: "fine" più bassa + prospettiva più urbana
HORIZON_Y = int(HEIGHT * 0.62)
BOTTOM_Y  = int(HEIGHT * 0.985)

# Strada larghissima in basso (copre quasi tutta la strada della foto)
ROAD_NEAR_W = int(WIDTH * 1.10)   # volutamente > WIDTH
ROAD_FAR_W  = int(WIDTH * 0.30)

SPAWN_MS = 520
RAMP_CHANCE = 0.25

# Sprite rotation (0 se già "dritti")
SPRITE_ROT_DEG = 0

# Giorno/notte
DAY_NIGHT_PERIOD_S = 60  # ogni 60 secondi cambia

# -----------------------------
# Init
# -----------------------------
pygame.init()

# iPhone/Safari: spesso "Ready to start" è legato ad audio/autoplay.
# Qui disabilitiamo il mixer: riduce problemi e "media user action required".
try:
    pygame.mixer.quit()
except Exception:
    pass

pygame.display.set_caption("Riders - NYC Day/Night")
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 24)
big_font = pygame.font.SysFont(None, 56)

def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t

def draw_text(surf, text, x, y, color=(255, 255, 255), center=False, fnt=None):
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
        pygame.draw.rect(surf, (20, 20, 20), (10, 12, fallback_size[0]-20, 22), border_radius=10)
        return surf

def load_bg(filename):
    path = os.path.join(ASSETS_DIR, filename)
    try:
        img = pygame.image.load(path).convert()
        return pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
    except Exception:
        bg = pygame.Surface((WIDTH, HEIGHT))
        bg.fill((30, 30, 30))
        return bg

def rotate(img, deg):
    return img if deg == 0 else pygame.transform.rotate(img, deg)

PLAYER_IMG = load_png("car_player.png", (260, 220), (220, 40, 40), colorkey=None)
RAMP_IMG   = load_png("ramp_blue.png",  (280, 200), (70, 130, 255), colorkey=None)
SUV1_IMG   = load_png("suv_black_1.png", (260, 220), (35, 35, 40), colorkey=None)
SUV2_IMG   = load_png("suv_green.png",   (260, 220), (20, 180, 80), colorkey=None)

BG_IMG     = load_bg("nyc_bg.png")

# -----------------------------
# Road geometry (prospettiva curva stile "foto urbana")
# -----------------------------
def road_half_width_at_y(y):
    # Prospettiva NON lineare: molto larga sotto, stringe presto e poi "schiaccia"
    t = clamp((y - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0.0, 1.0)
    t2 = t ** 0.55
    w = ROAD_FAR_W + (ROAD_NEAR_W - ROAD_FAR_W) * t2
    return w / 2

# -----------------------------
# Lampioni a L (alti, realistici, base sul piano strada)
# -----------------------------
def draw_lamps(surf, is_night, t_ms):
    # più radi: meno affollamento
    step = 140
    scroll = int((t_ms * 0.12) % step)

    for y in range(HORIZON_Y + 20, int(BOTTOM_Y) + step, step):
        yy = y + scroll
        if yy < HORIZON_Y + 20 or yy > BOTTOM_Y:
            continue

        half = road_half_width_at_y(yy)

        # Base palo = bordo strada (piano strada)
        left_base_x  = int(WIDTH/2 - half)
        right_base_x = int(WIDTH/2 + half)
        base_y = int(yy)

        # scala prospettica coerente con la strada
        t = clamp((yy - HORIZON_Y) / (BOTTOM_Y - HORIZON_Y), 0.0, 1.0)
        t2 = t ** 0.6

        # lampioni ALTI
        pole_h = int(lerp(90, 230, t2))
        pole_w = max(3, int(lerp(3, 6, t2)))

        # Braccio a L verso la strada (luce vicino alla carreggiata)
        arm_len  = int(lerp(30, 85, t2))
        arm_drop = int(lerp(18, 38, t2))

        for base_x, side in ((left_base_x, "L"), (right_base_x, "R")):
            # palo verticale
            pygame.draw.rect(
                surf, (60, 60, 66),
                (base_x - pole_w//2, base_y - pole_h, pole_w, pole_h),
                border_radius=2
            )

            # braccio orizzontale (L)
            arm_y = base_y - pole_h + int(pole_h * 0.20)
            arm_x = base_x + arm_len if side == "L" else base_x - arm_len
            pygame.draw.line(surf, (60, 60, 66), (base_x, arm_y), (arm_x, arm_y), pole_w)

            # luce (più verso il centro strada)
            lamp_x = arm_x
            lamp_y = arm_y + arm_drop

            head_r = max(4, int(lerp(4, 7, t2)))
            pygame.draw.circle(
                surf,
                (255, 245, 210) if is_night else (140, 140, 145),
                (lamp_x, lamp_y),
                head_r
            )

            if is_night:
                # cono di luce verso il basso
                cone_h = int(lerp(80, 210, t2))
                cone_w = int(lerp(60, 190, t2))
                cone = pygame.Surface((cone_w, cone_h), pygame.SRCALPHA)

                pygame.draw.polygon(
                    cone,
                    (255, 235, 170, 70),
                    [(cone_w//2, 0), (0, cone_h), (cone_w, cone_h)]
                )
                # layer interno più intenso
                pygame.draw.polygon(
                    cone,
                    (255, 235, 170, 40),
                    [(cone_w//2, 0), (int(cone_w*0.18), cone_h), (int(cone_w*0.82), cone_h)]
                )

                surf.blit(cone, (lamp_x - cone_w//2, lamp_y))

# -----------------------------
# Road drawing (asfalto più chiaro + linea centrale nera)
# -----------------------------
def draw_road(surf, t_ms, is_night):
    far_half = ROAD_FAR_W / 2
    near_half = ROAD_NEAR_W / 2

    # Trapezio base (la "curva" è in road_half_width_at_y per spawn/posizioni,
    # qui lo teniamo trapezoide per solidità visiva; copre quasi tutta la strada sotto)
    pts = [
        (WIDTH/2 - far_half, HORIZON_Y),
        (WIDTH/2 + far_half, HORIZON_Y),
        (WIDTH/2 + near_half, BOTTOM_Y),
        (WIDTH/2 - near_half, BOTTOM_Y),
    ]

    asphalt = (122, 122, 128) if not is_night else (62, 62, 66)
    pygame.draw.polygon(surf, asphalt, pts)

    # bordi strada
    edge = (245, 245, 245) if not is_night else (210, 210, 210)
    pygame.draw.line(surf, edge, pts[0], pts[3], 6)
    pygame.draw.line(surf, edge, pts[1], pts[2], 6)

    # linea centrale NERA
    dash_len, gap = 26, 18
    offset = int((t_ms * 0.32) % (dash_len + gap))
    for y in range(HORIZON_Y + 8, int(BOTTOM_Y) + 160, dash_len + gap):
        yy = y + offset
        pygame.draw.rect(surf, (10, 10, 10), (WIDTH/2 - 3, yy, 6, dash_len), border_radius=3)

# -----------------------------
# Touch UI
# -----------------------------
LEFT_ZONE  = pygame.Rect(0, 0, int(WIDTH * 0.42), HEIGHT)
RIGHT_ZONE = pygame.Rect(int(WIDTH * 0.58), 0, int(WIDTH * 0.42), HEIGHT)

# Pulsanti grandi ~2x rispetto a prima
BTN_R = int(min(WIDTH, HEIGHT) * 0.11)

JUMP_C = (int(WIDTH * 0.88), int(HEIGHT * 0.82))
JUMP_BTN = pygame.Rect(JUMP_C[0] - BTN_R, JUMP_C[1] - BTN_R, BTN_R*2, BTN_R*2)

RESTART_C = (int(WIDTH * 0.12), int(HEIGHT * 0.82))
RESTART_BTN = pygame.Rect(RESTART_C[0] - BTN_R, RESTART_C[1] - BTN_R, BTN_R*2, BTN_R*2)

def finger_to_xy(x_norm, y_norm):
    return int(x_norm * WIDTH), int(y_norm * HEIGHT)

def draw_circle_button(surf, center, radius, label, active=False):
    cx, cy = center
    btn = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
    pygame.draw.circle(btn, (0, 0, 0, 120 if not active else 170), (radius, radius), radius)
    pygame.draw.circle(btn, (255, 255, 255, 170), (radius, radius), radius-4, width=4)
    surf.blit(btn, (cx - radius, cy - radius))
    draw_text(surf, label, cx - int(radius*0.60), cy - 10, center=True, color=(255,255,255), fnt=font)

def draw_touch_overlay(surf, left, right, jump, show_restart, restart_active):
    # zone leggere (debug visivo)
    z = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    if left:
        pygame.draw.rect(z, (255, 255, 255, 12), LEFT_ZONE)
    if right:
        pygame.draw.rect(z, (255, 255, 255, 12), RIGHT_ZONE)
    surf.blit(z, (0, 0))

    draw_circle_button(surf, JUMP_C, BTN_R, "JUMP", active=jump)
    if show_restart:
        draw_circle_button(surf, RESTART_C, BTN_R, "R", active=restart_active)

# -----------------------------
# Entities
# -----------------------------
class Player:
    def __init__(self):
        self.lane_x = 0.0
        self.steer_speed = 1.75
        self.y = int(HEIGHT * 0.875)   # più giù per stare "sul piano" dei SUV

        self.air = 0.0
        self.v_air = 0.0
        self.gravity = 2.9
        self.jump_strength = 1.35
        self.on_ground = True

        # scala auto (tieni questo se ti piace; cambia qui se vuoi)
        self.visual_scale = 0.27

    def jump(self, mult=1.0):
        if self.on_ground:
            self.v_air = self.jump_strength * mult
            self.on_ground = False

    def update(self, dt, steer_dir):
        self.lane_x = clamp(self.lane_x + steer_dir * self.steer_speed * dt, -0.98, 0.98)

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

        base_w = int(PLAYER_IMG.get_width() * self.visual_scale)
        base_h = int(PLAYER_IMG.get_height() * self.visual_scale)
        img = pygame.transform.smoothscale(PLAYER_IMG, (base_w, base_h))
        img = rotate(img, SPRITE_ROT_DEG)

        # NIENTE OMBRA (richiesto)
        lift = int(80 * self.air)
        surf.blit(img, img.get_rect(center=(x, self.y - lift)))

class Thing:
    def __init__(self, kind):
        self.kind = kind

        # spawn in corsie + jitter
        lanes = [-0.70, -0.25, 0.25, 0.70]
        self.lane_x = random.choice(lanes) + random.uniform(-0.12, 0.12)
        self.lane_x = clamp(self.lane_x, -0.95, 0.95)

        self.d = 1.0 + random.uniform(0.02, 0.15)  # distanza (1 = lontano)
        self.variant = random.choice([1, 2]) if kind == "suv" else 0

    def update(self, dt, speed):
        self.d -= speed * dt

    def is_dead(self):
        return self.d < -0.20

    def screen_pos_and_scale(self):
        t = clamp(1.0 - self.d, 0.0, 1.0)
        y = lerp(HORIZON_Y + 10, int(HEIGHT * 0.875), t)

        half = road_half_width_at_y(y)
        x = WIDTH/2 + self.lane_x * half

        # più coerente con strada larghissima in basso
        scale = lerp(0.18, 0.98, t)
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
# Game state
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

# -----------------------------
# Async loop (web-safe)
# -----------------------------
async def main():
    state = reset()
    runtime_error = None
    started = False

    active_fingers = {}
    mouse_down = False
    mouse_pos = (0, 0)

    while True:
        try:
            dt = clock.tick(FPS) / 1000.0
            now = pygame.time.get_ticks()

            # giorno/notte toggle
            seconds = (now // 1000) % (DAY_NIGHT_PERIOD_S * 2)
            is_night = (seconds >= DAY_NIGHT_PERIOD_S)

            # schermata start "tap to start"
            if not started:
                screen.fill((0, 0, 0))
                draw_text(screen, "RIDERS", WIDTH//2, HEIGHT//2 - 40, center=True, fnt=big_font)
                draw_text(screen, "TAP TO START", WIDTH//2, HEIGHT//2 + 10, center=True, color=(180, 180, 180))
                pygame.display.flip()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN, pygame.KEYDOWN):
                        started = True

                await asyncio.sleep(0)
                continue

            # eventi
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return

                if event.type == pygame.KEYDOWN:
                    if not state["game_over"] and event.key == pygame.K_SPACE:
                        state["player"].jump(mult=1.0)
                    elif state["game_over"] and event.key == pygame.K_r:
                        state = reset()

                # mouse (desktop)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_down = True
                    mouse_pos = event.pos
                elif event.type == pygame.MOUSEMOTION and mouse_down:
                    mouse_pos = event.pos
                elif event.type == pygame.MOUSEBUTTONUP:
                    mouse_down = False

                # touch (mobile)
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

            # input hold
            pressed_left = pressed_right = pressed_jump = pressed_restart = False

            keys = pygame.key.get_pressed()
            steer_dir = 0.0
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                steer_dir -= 1.0
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                steer_dir += 1.0

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
                if state["game_over"] and RESTART_BTN.collidepoint(mx, my):
                    pressed_restart = True

            if pressed_left and not pressed_right:
                steer_dir = -1.0
            elif pressed_right and not pressed_left:
                steer_dir = 1.0

            if pressed_jump and (not state["game_over"]):
                state["player"].jump(mult=1.0)

            if pressed_restart and state["game_over"]:
                state = reset()

            # update
            elapsed = (now - state["start_ms"]) / 1000.0
            speed = 0.85 + 0.020 * elapsed

            if not state["game_over"]:
                state["player"].update(dt, steer_dir)

                if now - state["last_spawn"] > SPAWN_MS:
                    kind = "ramp" if random.random() < RAMP_CHANCE else "suv"
                    state["things"].append(Thing(kind))
                    state["last_spawn"] = now

                for th in state["things"]:
                    th.update(dt, speed)

                for th in list(state["things"]):
                    if th.collides_with_player(state["player"]):
                        if th.kind == "ramp":
                            # salto più forte sulla rampa
                            state["player"].jump(mult=2.2)
                            state["things"].remove(th)
                        else:
                            # se sei in aria abbastanza, lo "scavalchi"
                            if state["player"].air > 0.28:
                                continue
                            state["game_over"] = True

                state["things"] = [t for t in state["things"] if not t.is_dead()]
                state["score"] += (speed * 120) * dt

            # -----------------------------
            # DRAW (ordine corretto per notte/luci)
            # -----------------------------
            screen.blit(BG_IMG, (0, 0))

            # overlay notte PRIMA
            if is_night:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 140))
                screen.blit(overlay, (0, 0))

            # strada
            draw_road(screen, now, is_night)

            # lampioni DOPO overlay (così illuminano davvero)
            draw_lamps(screen, is_night, now)

            # oggetti
            for th in sorted(state["things"], key=lambda t: t.d, reverse=True):
                th.draw(screen)

            # player
            state["player"].draw(screen)

            # HUD
            hud_color = (0, 0, 0) if not is_night else (240, 240, 240)
            draw_text(screen, "RIDERS", 18, 12, color=hud_color)
            label = "Night" if is_night else "Day"
            draw_text(screen, f"{label} | Score: {int(state['score'])}", 18, 40, color=hud_color)

            # touch UI
            draw_touch_overlay(
                screen,
                pressed_left, pressed_right, pressed_jump,
                show_restart=state["game_over"],
                restart_active=pressed_restart
            )

            if state["game_over"]:
                draw_text(screen, "GAME OVER", WIDTH//2, HEIGHT//2 - 35, center=True,
                          fnt=big_font, color=hud_color)
                draw_text(screen, "Tap R (or press R) to restart", WIDTH//2, HEIGHT//2 + 20,
                          center=True, color=hud_color)

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
