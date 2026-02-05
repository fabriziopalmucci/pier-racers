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

HORIZON_Y = int(HEIGHT * 0.28)
BOTTOM_Y  = int(HEIGHT * 0.98)
ROAD_NEAR_W = int(WIDTH * 0.80)
ROAD_FAR_W  = int(WIDTH * 0.18)

SPAWN_MS = 520
RAMP_CHANCE = 0.25
SPRITE_ROT_DEG = 0

pygame.init()
pygame.display.set_caption("Riders - NYC Day (Web)")
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
    rect.center = (x, y) if center else rect.center
    if not center:
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
    pygame.draw.polygon(surf, (70, 70, 75), pts)
    pygame.draw.line(surf, (245, 245, 245), pts[0], pts[3], 6)
    pygame.draw.line(surf, (245, 245, 245), pts[1], pts[2], 6)

    dash_len, gap = 26, 18
    offset = int((t_ms * 0.28) % (dash_len + gap))
    for y in range(HORIZON_Y + 15, int(BOTTOM_Y) + 120, dash_len + gap):
        yy = y + offset
        pygame.draw.rect(surf, (235, 235, 90), (WIDTH/2 - 4, yy, 8, dash_len), border_radius=4)

# -----------------------------
# Touch UI
# -----------------------------
LEFT_ZONE  = pygame.Rect(0, 0, int(WIDTH * 0.42), HEIGHT)
RIGHT_ZONE = pygame.Rect(int(WIDTH * 0.58), 0, int(WIDTH * 0.42), HEIGHT)

BTN_R = int(min(WIDTH, HEIGHT) * 0.055)

JUMP_C = (int(WIDTH * 0.88), int(HEIGHT * 0.82))
JUMP_BTN = pygame.Rect(JUMP_C[0] - BTN_R, JUMP_C[1] - BTN_R, BTN_R*2, BTN_R*2)

RESTART_C = (int(WIDTH * 0.12), int(HEIGHT * 0.82))
RESTART_BTN = pygame.Rect(RESTART_C[0] - BTN_R, RESTART_C[1] - BTN_R, BTN_R*2, BTN_R*2)

def pointer_xy(event):
    if hasattr(event, "pos"):
        return event.pos
    if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
        return int(event.x * WIDTH), int(event.y * HEIGHT)
    return None

def draw_circle_button(surf, center, radius, label, active=False):
    cx, cy = center
    btn = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
    pygame.draw.circle(btn, (0, 0, 0, 95 if not active else 140), (radius, radius), radius)
    pygame.draw.circle(btn, (255, 255, 255, 160), (radius, radius), radius-3, width=3)
    surf.blit(btn, (cx - radius, cy - radius))
    draw_text(surf, label, cx, cy-8, center=True, color=(255,255,255))

def draw_touch_overlay(surf, left, right, jump, show_restart, restart_active):
    # subtle zones
    z = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    if left:
        pygame.draw.rect(z, (255, 255, 255, 18), LEFT_ZONE)
    if right:
        pygame.draw.rect(z, (255, 255, 255, 18), RIGHT_ZONE)
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
        self.y = int(HEIGHT * 0.78)

        self.air = 0.0
        self.v_air = 0.0
        self.gravity = 2.9
        self.jump_strength = 1.35
        self.on_ground = True

        # riduci del 40% rispetto a ~0.45 -> 0.27
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

        shadow_scale = 1.0 - self.air * 0.35
        sw = int(110 * shadow_scale)
        sh = int(34 * shadow_scale)
        shadow = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 110), (0, 0, sw, sh))
        surf.blit(shadow, shadow.get_rect(center=(x, self.y + 62)))

        base_w = int(PLAYER_IMG.get_width() * self.visual_scale)
        base_h = int(PLAYER_IMG.get_height() * self.visual_scale)
        img = pygame.transform.smoothscale(PLAYER_IMG, (base_w, base_h))
        img = rotate(img, SPRITE_ROT_DEG)

        lift = int(95 * self.air)
        surf.blit(img, img.get_rect(center=(x, self.y - lift)))

class Thing:
    def __init__(self, kind):
        self.kind = kind

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
# Async game loop (web-safe)
# -----------------------------
async def main():
    state = reset()
    runtime_error = None

    # START GATE (fix iPhone “Ready to start” flakiness)
    started = False

    # touch states
    pressed_left = False
    pressed_right = False
    pressed_jump = False
    pressed_restart = False

    while True:
        try:
            dt = clock.tick(FPS) / 1000.0
            now = pygame.time.get_ticks()

            # --- start screen: wait for a real gesture ---
            if not started:
                screen.fill((0, 0, 0))
                draw_text(screen, "RIDERS", WIDTH//2, HEIGHT//2 - 40, center=True, fnt=big_font)
                draw_text(screen, "TAP TO START", WIDTH//2, HEIGHT//2 + 10, center=True, color=(180, 180, 180))
                draw_text(screen, "(iPhone: tap once)", WIDTH//2, HEIGHT//2 + 42, center=True, color=(130, 130, 130))
                pygame.display.flip()

                # eat events until a gesture comes
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN, pygame.KEYDOWN):
                        started = True

                await asyncio.sleep(0)
                continue

            # keyboard steer
            keys = pygame.key.get_pressed()
            steer_dir = 0.0
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                steer_dir -= 1.0
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                steer_dir += 1.0

            # reset touch flags each frame
            pressed_left = pressed_right = pressed_jump = pressed_restart = False

            # events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return

                # desktop keys
                if event.type == pygame.KEYDOWN:
                    if not state["game_over"] and event.key == pygame.K_SPACE:
                        state["player"].jump(mult=1.0)
                    elif state["game_over"] and event.key == pygame.K_r:
                        state = reset()

                # touch / mouse
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP,
                                  pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
                    xy = pointer_xy(event)
                    if xy is None:
                        continue
                    mx, my = xy

                    if event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP):
                        # release -> nothing pressed
                        pass
                    else:
                        # press/drag states
                        if LEFT_ZONE.collidepoint(mx, my):
                            pressed_left = True
                        if RIGHT_ZONE.collidepoint(mx, my):
                            pressed_right = True
                        if JUMP_BTN.collidepoint(mx, my):
                            pressed_jump = True
                        if state["game_over"] and RESTART_BTN.collidepoint(mx, my):
                            pressed_restart = True

            # touch overrides steer
            if pressed_left and not pressed_right:
                steer_dir = -1.0
            elif pressed_right and not pressed_left:
                steer_dir = 1.0

            # touch jump
            if pressed_jump and (not state["game_over"]):
                state["player"].jump(mult=1.0)

            # touch restart
            if pressed_restart and state["game_over"]:
                state = reset()

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
                            state["player"].jump(mult=2.2)  # jump higher
                            state["things"].remove(th)
                        else:
                            if state["player"].air > 0.28:
                                continue
                            state["game_over"] = True

                state["things"] = [t for t in state["things"] if not t.is_dead()]
                state["score"] += (speed * 120) * dt

            # draw
            screen.blit(BG_IMG, (0, 0))
            draw_road(screen, now)

            for th in sorted(state["things"], key=lambda t: t.d, reverse=True):
                th.draw(screen)

            state["player"].draw(screen)

            draw_text(screen, "RIDERS", 18, 12, color=(0, 0, 0))
            draw_text(screen, f"Score: {int(state['score'])}", 18, 40, color=(0, 0, 0))

            # touch overlay (restart only in game over)
            draw_touch_overlay(
                screen,
                pressed_left,
                pressed_right,
                pressed_jump,
                show_restart=state["game_over"],
                restart_active=pressed_restart
            )

            if state["game_over"]:
                draw_text(screen, "GAME OVER", WIDTH//2, HEIGHT//2 - 35, center=True, fnt=big_font, color=(0, 0, 0))
                draw_text(screen, "Tap R button (or press R) to restart", WIDTH//2, HEIGHT//2 + 20, center=True, color=(0, 0, 0))

            if runtime_error:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 190))
                screen.blit(overlay, (0, 0))
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

# Pygbag web entry
asyncio.run(main())
