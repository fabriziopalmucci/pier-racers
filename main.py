import os
import sys
import random
import pygame

# =============================
# CONFIG
# =============================
WIDTH, HEIGHT = 900, 600
FPS = 60

HORIZON_Y = int(HEIGHT * 0.50)
BOTTOM_Y  = int(HEIGHT * 0.98)

ROAD_NEAR_W = int(WIDTH * 0.82)
ROAD_FAR_W  = int(WIDTH * 0.18)

SPAWN_MS = 520
RAMP_CHANCE = 0.25

SPRITE_ROT_DEG = 0

PLAYER_SCALE_MULT = 0.60   # auto -40%
SUV_SIZE_MULT = 1.20       # SUV +20%

JUMP_MULT_ON_RAMP = 2.2
LIFT_MULT = 1.55

# --- Touch UI (smartphone) ---
# aree touch: sinistra/destra per sterzo, bottone salto in basso a destra
JUMP_BTN_W, JUMP_BTN_H = 165, 90
JUMP_BTN_MARGIN = 18

pygame.init()
pygame.display.set_caption("Riders - NYC Day (Web-ready)")
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

font = pygame.font.SysFont(None, 28)
big_font = pygame.font.SysFont(None, 64)

# =============================
# UTILS
# =============================
def clamp(x, a, b):
    return max(a, min(b, x))

def lerp(a, b, t):
    return a + (b - a) * t

def draw_text(surf, text, x, y, color=(10,10,10), center=False, fnt=None):
    fnt = fnt or font
    img = fnt.render(text, True, color)
    rect = img.get_rect()
    rect.center = (x, y) if center else rect.topleft
    surf.blit(img, rect)

# =============================
# ASSETS
# =============================
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

def load_png_alpha(filename, fallback_size, color):
    path = os.path.join(ASSETS_DIR, filename)
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception:
        surf = pygame.Surface(fallback_size, pygame.SRCALPHA)
        pygame.draw.rect(surf, color, (0,0,*fallback_size), border_radius=12)
        return surf

def load_bg(filename):
    path = os.path.join(ASSETS_DIR, filename)
    try:
        img = pygame.image.load(path).convert()
        return pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
    except Exception:
        bg = pygame.Surface((WIDTH, HEIGHT))
        bg.fill((170,220,255))
        return bg

def rotate(img, deg):
    return img if deg == 0 else pygame.transform.rotate(img, deg)

def force_opaque_keep_transparent(surface):
    """
    Rende OPACHI (alpha=255) tutti i pixel visibili.
    Mantiene alpha=0 solo dove è davvero trasparente.
    (Fix utile se un PNG ha semitrasparenze indesiderate.)
    """
    surf = surface.convert_alpha()
    try:
        import pygame.surfarray as surfarray
        a = surfarray.pixels_alpha(surf)
        a[a > 0] = 255
        del a
    except Exception:
        w, h = surf.get_size()
        for y in range(h):
            for x in range(w):
                r,g,b,a = surf.get_at((x,y))
                if a > 0:
                    surf.set_at((x,y),(r,g,b,255))
    return surf

# --- LOAD FILES ---
PLAYER_IMG = load_png_alpha("car_player.png",(260,220),(220,40,40))
RAMP_IMG   = load_png_alpha("ramp_blue.png",(280,200),(70,130,255))

SUV1_IMG  = load_png_alpha("suv_black_1.png",(260,220),(35,35,40))
SUV2_IMG  = load_png_alpha("suv_green.png",(260,220),(20,80,40))
# Se vuoi assicurarti che il verde NON sia mai trasparente:
SUV2_IMG  = force_opaque_keep_transparent(SUV2_IMG)

BG_IMG = load_bg("nyc_bg.png")

# =============================
# ROAD GEOMETRY
# =============================
def road_half_width_at_y(y):
    t = clamp((y - HORIZON_Y)/(BOTTOM_Y - HORIZON_Y), 0, 1)
    return lerp(ROAD_FAR_W, ROAD_NEAR_W, t) / 2

ROAD_TEXTURE = None

def build_road_texture():
    rnd = random.Random(1337)
    tex = pygame.Surface((512,512)).convert()
    tex.fill((95,95,100))  # asfalto chiaro
    for _ in range(12000):
        x,y = rnd.randrange(512), rnd.randrange(512)
        v = rnd.randrange(85,135)
        tex.set_at((x,y),(v,v,v))
    return tex

def draw_guard_rails(surf, y0, y1):
    layer = pygame.Surface((WIDTH,HEIGHT), pygame.SRCALPHA)
    for y in range(y0, y1, 4):
        t = clamp((y-y0)/(y1-y0), 0, 1)
        half = lerp(ROAD_FAR_W, ROAD_NEAR_W, t)/2
        off = lerp(14, 28, t)
        lx = int(WIDTH/2 - half - off)
        rx = int(WIDTH/2 + half + off)
        pygame.draw.line(layer, (160,160,160,220), (lx, y), (lx+8, y), 3)
        pygame.draw.line(layer, (160,160,160,220), (rx-8, y), (rx, y), 3)
    surf.blit(layer, (0,0))

def draw_road(surf, t_ms):
    global ROAD_TEXTURE
    if ROAD_TEXTURE is None:
        ROAD_TEXTURE = build_road_texture()

    y0, y1 = HORIZON_Y, int(BOTTOM_Y)
    tex = ROAD_TEXTURE

    scroll = int((-t_ms * 0.20) % 512)  # verso giusto

    for y in range(y0, y1):
        t = clamp((y-y0)/(y1-y0), 0, 1)
        half = lerp(ROAD_FAR_W, ROAD_NEAR_W, t)/2
        left = int(WIDTH/2 - half)
        w = int(half*2)

        ty = (int(t*512) + scroll) % 512
        row = pygame.transform.smoothscale(tex.subsurface((0,ty,512,1)), (w,1))
        surf.blit(row, (left, y))

    # bordi
    pygame.draw.line(surf, (245,245,245), (WIDTH/2-road_half_width_at_y(y0), y0),
                     (WIDTH/2-road_half_width_at_y(y1), y1), 6)
    pygame.draw.line(surf, (245,245,245), (WIDTH/2+road_half_width_at_y(y0), y0),
                     (WIDTH/2+road_half_width_at_y(y1), y1), 6)

    # linea centrale tratteggiata
    dash_len, gap = 28, 18
    offset = int((t_ms * 0.30) % (dash_len + gap))
    for y in range(y0 + 20, y1 + 140, dash_len + gap):
        yy = y + offset
        if y0 <= yy <= y1:
            pygame.draw.rect(surf, (235,235,90), (WIDTH//2 - 4, yy, 8, dash_len), border_radius=4)

    draw_guard_rails(surf, y0, y1)

# =============================
# TOUCH UI
# =============================
def get_jump_button_rect():
    return pygame.Rect(
        WIDTH - JUMP_BTN_W - JUMP_BTN_MARGIN,
        HEIGHT - JUMP_BTN_H - JUMP_BTN_MARGIN,
        JUMP_BTN_W,
        JUMP_BTN_H
    )

def draw_touch_ui(surf):
    # Semitrasparente (solo UI), per capire dove toccare
    jump_rect = get_jump_button_rect()
    ui = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    # bottone salto
    pygame.draw.rect(ui, (20, 20, 20, 120), jump_rect, border_radius=18)
    pygame.draw.rect(ui, (250, 250, 250, 160), jump_rect, width=2, border_radius=18)
    surf.blit(ui, (0,0))

    draw_text(surf, "SALTA", jump_rect.centerx, jump_rect.centery-8, color=(255,255,255), center=True)
    draw_text(surf, "TOUCH", jump_rect.centerx, jump_rect.centery+18, color=(235,235,235), center=True, fnt=font)

# =============================
# ENTITIES
# =============================
class Player:
    def __init__(self):
        self.lane_x = 0.0
        self.y = int(HEIGHT * 0.88)

        self.air = 0.0
        self.v_air = 0.0
        self.jump_strength = 1.35
        self.on_ground = True

        self.steer_speed = 2.0

    def jump(self, mult=1.0):
        if self.on_ground:
            self.v_air = self.jump_strength * mult
            self.on_ground = False

    def update(self, dt, steer_dir):
        # steer_dir: -1, 0, +1
        self.lane_x = clamp(self.lane_x + steer_dir * self.steer_speed * dt, -0.95, 0.95)

        if not self.on_ground:
            self.air += self.v_air * dt * 2.2
            self.v_air -= 2.9 * dt * 2.2
            if self.air <= 0:
                self.air = 0
                self.v_air = 0
                self.on_ground = True

    def screen_x(self):
        return int(WIDTH/2 + self.lane_x * road_half_width_at_y(self.y))

    def draw(self, surf):
        x = self.screen_x()

        # ombra pulita
        shadow_scale = 1.0 - self.air * 0.25
        sw, sh = int(110 * shadow_scale), int(30 * shadow_scale)
        shadow = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0,0,0,90), (0,0,sw,sh))
        surf.blit(shadow, shadow.get_rect(center=(x, self.y + 48)))

        w = int(PLAYER_IMG.get_width() * 0.45 * PLAYER_SCALE_MULT)
        h = int(PLAYER_IMG.get_height() * 0.45 * PLAYER_SCALE_MULT)
        img = pygame.transform.smoothscale(PLAYER_IMG, (w, h))
        img = rotate(img, SPRITE_ROT_DEG)

        lift = int(90 * self.air * LIFT_MULT)
        surf.blit(img, img.get_rect(center=(x, self.y - lift)))

class Thing:
    def __init__(self, kind):
        self.kind = kind
        self.lane_x = random.choice([-0.7, -0.25, 0.25, 0.7]) + random.uniform(-0.10, 0.10)
        self.lane_x = clamp(self.lane_x, -0.95, 0.95)

        self.d = 1.0 + random.uniform(0.02, 0.15)
        self.variant = random.choice([1, 2]) if kind == "suv" else 0

    def update(self, dt, speed):
        self.d -= speed * dt

    def is_dead(self):
        return self.d < -0.20

    def screen_pos_and_scale(self):
        t = clamp(1.0 - self.d, 0.0, 1.0)
        y = int(lerp(HORIZON_Y + 20, HEIGHT * 0.88, t))
        x = int(WIDTH/2 + self.lane_x * road_half_width_at_y(y))
        scale = lerp(0.20, 0.85, t)
        return x, y, scale

    def draw(self, surf):
        x, y, scale = self.screen_pos_and_scale()

        if self.kind == "suv":
            src = SUV1_IMG if self.variant == 1 else SUV2_IMG
            w = max(34, int(src.get_width() * 0.22 * scale * SUV_SIZE_MULT))
            h = max(34, int(src.get_height() * 0.22 * scale * SUV_SIZE_MULT))
            img = pygame.transform.smoothscale(src, (w, h))
        else:
            src = RAMP_IMG
            w = max(44, int(src.get_width() * 0.20 * scale))
            h = max(30, int(src.get_height() * 0.20 * scale))
            img = pygame.transform.smoothscale(src, (w, h))

        img = rotate(img, SPRITE_ROT_DEG)
        surf.blit(img, img.get_rect(center=(x, y)))

    def collides(self, player: Player):
        # finestra collisione quando l'oggetto arriva “vicino”
        if not (0.00 <= self.d <= 0.10):
            return False
        px = player.screen_x()
        x, _, _ = self.screen_pos_and_scale()
        return abs(px - x) < 75

# =============================
# MAIN LOOP
# =============================
def main():
    player = Player()
    things = []
    last_spawn = pygame.time.get_ticks()
    start = pygame.time.get_ticks()
    score = 0.0
    game_over = False

    # touch state
    touch_left = False
    touch_right = False

    while True:
        dt = clock.tick(FPS) / 1000.0
        now = pygame.time.get_ticks()

        # ---- input: keyboard base ----
        keys = pygame.key.get_pressed()
        steer_dir = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            steer_dir -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            steer_dir += 1

        # ---- input: touch (mouse + finger) ----
        jump_rect = get_jump_button_rect()

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # desktop jump
            if e.type == pygame.KEYDOWN:
                if not game_over and e.key == pygame.K_SPACE:
                    player.jump(1.0)
                if game_over and e.key == pygame.K_r:
                    player = Player()
                    things = []
                    last_spawn = now
                    start = now
                    score = 0.0
                    game_over = False

            # mouse/touch emulation
            if e.type == pygame.MOUSEBUTTONDOWN:
                mx, my = e.pos
                if jump_rect.collidepoint(mx, my):
                    if not game_over:
                        player.jump(1.0)
                else:
                    if mx < WIDTH * 0.5:
                        touch_left = True
                    else:
                        touch_right = True

            if e.type == pygame.MOUSEBUTTONUP:
                touch_left = False
                touch_right = False

            # real finger events (alcuni browser/pygbag li mandano)
            if e.type == pygame.FINGERDOWN:
                mx = int(e.x * WIDTH)
                my = int(e.y * HEIGHT)
                if jump_rect.collidepoint(mx, my):
                    if not game_over:
                        player.jump(1.0)
                else:
                    if mx < WIDTH * 0.5:
                        touch_left = True
                    else:
                        touch_right = True

            if e.type == pygame.FINGERUP:
                touch_left = False
                touch_right = False

        # apply touch steer (adds to keyboard)
        if touch_left and not touch_right:
            steer_dir -= 1
        if touch_right and not touch_left:
            steer_dir += 1
        steer_dir = clamp(steer_dir, -1, 1)

        # ---- game update ----
        elapsed = (now - start) / 1000.0
        speed = 0.85 + 0.020 * elapsed

        if not game_over:
            player.update(dt, steer_dir)

            if now - last_spawn > SPAWN_MS:
                kind = "ramp" if random.random() < RAMP_CHANCE else "suv"
                things.append(Thing(kind))
                last_spawn = now

            for t in things:
                t.update(dt, speed)

            for t in list(things):
                if t.collides(player):
                    if t.kind == "ramp":
                        player.jump(JUMP_MULT_ON_RAMP)
                        things.remove(t)
                    else:
                        if player.air < 0.28:
                            game_over = True

            things = [t for t in things if not t.is_dead()]
            score += speed * 120 * dt

        # ---- draw ----
        screen.blit(BG_IMG, (0, 0))
        draw_road(screen, now)

        for t in sorted(things, key=lambda x: x.d, reverse=True):
            t.draw(screen)

        player.draw(screen)

        # UI/HUD
        draw_text(screen, "RIDERS", 18, 12, color=(0,0,0))
        draw_text(screen, f"Score: {int(score)}", 18, 42, color=(0,0,0))
        draw_text(screen, "A/D sterzo | SPAZIO salto | R restart", 18, HEIGHT-28, color=(0,0,0))

        draw_touch_ui(screen)

        if game_over:
            draw_text(screen, "GAME OVER", WIDTH//2, HEIGHT//2 - 35, center=True, fnt=big_font, color=(0,0,0))
            draw_text(screen, f"Punteggio: {int(score)}", WIDTH//2, HEIGHT//2 + 20, center=True, color=(0,0,0))
            draw_text(screen, "Premi R per ricominciare", WIDTH//2, HEIGHT//2 + 52, center=True, color=(0,0,0))

        pygame.display.flip()

# run
if __name__ == "__main__":
    main()
