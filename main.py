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

# Strada (VERSIONE BUONA)
HORIZON_Y = int(HEIGHT * 0.52)
BOTTOM_Y  = int(HEIGHT * 0.985)

ROAD_NEAR_W = int(WIDTH * 1.32)
ROAD_FAR_W  = int(WIDTH * 0.14)

SPAWN_MS = 520
RAMP_CHANCE = 0.25

SPRITE_ROT_DEG = 0

# Giorno / Notte
DAY_NIGHT_PERIOD_S = 60.0      # ciclo completo
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

def clamp(x,a,b): return max(a,min(b,x))
def lerp(a,b,t): return a+(b-a)*t

# =============================
# UTILS
# =============================
def draw_text(surf, txt, x, y, color=(255,255,255), center=False, fnt=None):
    fnt = fnt or font
    img = fnt.render(txt, True, color)
    r = img.get_rect()
    r.center = (x,y) if center else (x,y)
    if not center: r.topleft = (x,y)
    surf.blit(img, r)

# =============================
# ASSETS
# =============================
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

def trim_alpha(img):
    try:
        r = img.get_bounding_rect(min_alpha=1)
        return img.subsurface(r).copy() if r.width>0 else img
    except:
        return img

def load_png(name, fallback, color, trim=False):
    try:
        img = pygame.image.load(os.path.join(ASSETS_DIR,name)).convert_alpha()
        return trim_alpha(img) if trim else img
    except:
        s = pygame.Surface(fallback, pygame.SRCALPHA)
        pygame.draw.rect(s, color, s.get_rect(), border_radius=12)
        return s

def load_bg(name):
    try:
        img = pygame.image.load(os.path.join(ASSETS_DIR,name)).convert()
        return pygame.transform.smoothscale(img,(WIDTH,HEIGHT))
    except:
        bg = pygame.Surface((WIDTH,HEIGHT))
        bg.fill((30,30,30))
        return bg

PLAYER_IMG = load_png("car_player.png",(260,220),(220,40,40))
SUV1_IMG   = load_png("suv_black_1.png",(260,220),(40,40,40))
SUV2_IMG   = load_png("suv_green.png",(260,220),(40,120,60))
RAMP_IMG   = load_png("ramp_blue.png",(280,200),(70,130,255))
LAMP_IMG   = load_png("lamppost_L.png",(512,512),(90,90,95), trim=True)
BG_IMG     = load_bg("nyc_bg.png")

# =============================
# ROAD
# =============================
def road_half_width_at_y(y):
    t = clamp((y-HORIZON_Y)/(BOTTOM_Y-HORIZON_Y),0,1)
    return (ROAD_FAR_W + (ROAD_NEAR_W-ROAD_FAR_W)*(t**0.55))/2

def draw_road(surf, t_ms, night):
    far = ROAD_FAR_W/2
    near = ROAD_NEAR_W/2
    pts = [
        (WIDTH/2-far, HORIZON_Y),
        (WIDTH/2+far, HORIZON_Y),
        (WIDTH/2+near, BOTTOM_Y),
        (WIDTH/2-near, BOTTOM_Y)
    ]
    day = (155,155,162)
    night_c = (95,95,102)
    col = tuple(int(lerp(d,n,night)) for d,n in zip(day,night_c))
    pygame.draw.polygon(surf,col,pts)

    edge = tuple(int(lerp(245,220,night)) for _ in range(3))
    pygame.draw.line(surf,edge,pts[0],pts[3],6)
    pygame.draw.line(surf,edge,pts[1],pts[2],6)

    off = int((t_ms*0.32)%44)
    for y in range(HORIZON_Y+10,int(BOTTOM_Y)+160,44):
        pygame.draw.rect(surf,(10,10,10),(WIDTH//2-3,y+off,6,26),border_radius=3)

# =============================
# DAY / NIGHT
# =============================
def night_factor(now_ms):
    t = (now_ms-APP_START_MS)/1000
    half = DAY_NIGHT_PERIOD_S/2
    target = 0 if (t%DAY_NIGHT_PERIOD_S)<half else 1
    prev = 1-target
    local = t%half
    if local<DAY_NIGHT_FADE_S:
        x = clamp(local/DAY_NIGHT_FADE_S,0,1)
        x = 0.5-0.5*math.cos(math.pi*x)
        return prev*(1-x)+target*x
    return target

# =============================
# LAMP LIGHT (RADIAL)
# =============================
_light_cache={}
def radial_light(w,h,intensity):
    key=(w,h,intensity)
    if key in _light_cache: return _light_cache[key]
    s=pygame.Surface((w,h),pygame.SRCALPHA)
    cx,cy=w//2,int(h*0.15)
    for i in range(16,0,-1):
        t=i/16
        r=int(max(w,h)*t*0.6)
        a=int(intensity*(t**2))
        pygame.draw.circle(s,(255,235,190,a),(cx,cy),r)
    _light_cache[key]=s
    return s

# =============================
# LAMPS
# =============================
def draw_lamps(surf, night, t_ms):
    step=140
    scroll=int((t_ms*0.12)%step)
    Y_SHIFT=int(HEIGHT*0.15)

    y=int(BOTTOM_Y)+scroll
    while y>=HORIZON_Y+5:
        t=clamp((y-HORIZON_Y)/(BOTTOM_Y-HORIZON_Y),0,1)
        t2=t**0.6
        half=road_half_width_at_y(y)

        inset=int(lerp(6,18,t2))
        lx=int(WIDTH/2-half+inset)
        rx=int(WIDTH/2+half-inset)
        by=min(int(y+Y_SHIFT),int(BOTTOM_Y))

        scale=lerp(0.10,0.42,t2)
        w=int(LAMP_IMG.get_width()*scale)
        h=int(LAMP_IMG.get_height()*scale)
        lamp=pygame.transform.scale(LAMP_IMG,(w,h))
        lamp_r=pygame.transform.flip(lamp,True,False)

        rL=lamp.get_rect(midbottom=(lx,by))
        rR=lamp_r.get_rect(midbottom=(rx,by))

        surf.blit(lamp,rL)
        surf.blit(lamp_r,rR)

        if night>0.02:
            intensity=int(lerp(0,140,night)*lerp(0.6,1,t2))
            blob=radial_light(int(lerp(120,420,t2)),int(lerp(110,360,t2)),intensity)
            for r,sgn in ((rL,1),(rR,-1)):
                hx=r.centerx+int(w*0.26*sgn)
                hy=r.top+int(h*0.36)
                surf.blit(blob,(hx-blob.get_width()//2,hy))

        y-=step

# =============================
# ENTITIES
# =============================
class Player:
    def __init__(self):
        self.lane_x=0
        self.y=int(HEIGHT*0.88)
        self.air=0
        self.v_air=0
        self.gravity=2.9
        self.jump_strength=1.35
        self.on_ground=True
        w=int(PLAYER_IMG.get_width()*0.27)
        h=int(PLAYER_IMG.get_height()*0.27)
        self.img=pygame.transform.smoothscale(PLAYER_IMG,(w,h))

    def jump(self,m=1):
        if self.on_ground:
            self.v_air=self.jump_strength*m
            self.on_ground=False

    def update(self,dt,steer):
        self.lane_x=clamp(self.lane_x+steer*1.75*dt,-0.98,0.98)
        if not self.on_ground:
            self.air+=self.v_air*dt*2.2
            self.v_air-=self.gravity*dt*2.2
            if self.air<=0:
                self.air=0
                self.v_air=0
                self.on_ground=True

    def x(self):
        return int(WIDTH/2+self.lane_x*road_half_width_at_y(self.y))

    def draw(self,s):
        lift=int(72*self.air)
        s.blit(self.img,self.img.get_rect(center=(self.x(),self.y-lift)))

class Thing:
    def __init__(self,kind):
        self.kind=kind
        self.lane_x=random.choice([-0.7,-0.25,0.25,0.7])+random.uniform(-0.12,0.12)
        self.d=1+random.uniform(0.02,0.15)
        self.var=random.choice([1,2]) if kind=="suv" else 0

    def update(self,dt,speed): self.d-=speed*dt
    def dead(self): return self.d<-0.2

    def pos(self):
        t=clamp(1-self.d,0,1)
        y=int(lerp(HORIZON_Y+10,HEIGHT*0.90,t))
        x=int(WIDTH/2+self.lane_x*road_half_width_at_y(y))
        s=lerp(0.18,1,t)
        return x,y,s

    def draw(self,s):
        x,y,sc=self.pos()
        src=RAMP_IMG if self.kind=="ramp" else (SUV1_IMG if self.var==1 else SUV2_IMG)
        w=int(src.get_width()*0.22*sc)
        h=int(src.get_height()*0.22*sc)
        img=pygame.transform.smoothscale(src,(w,h))
        s.blit(img,img.get_rect(center=(x,y)))

    def hit(self,p):
        if not (0<=self.d<=0.1): return False
        x,_,_=self.pos()
        return abs(p.x()-x)<75

# =============================
# GAME LOOP
# =============================
def reset():
    return {"player":Player(),"things":[],"score":0,"last":pygame.time.get_ticks(),"over":False}

state=reset()

while True:
    dt=clock.tick(FPS)/1000
    now=pygame.time.get_ticks()

    for e in pygame.event.get():
        if e.type==pygame.QUIT: pygame.quit(); exit()
        if e.type==pygame.KEYDOWN:
            if not state["over"] and e.key==pygame.K_SPACE: state["player"].jump()
            if state["over"] and e.key==pygame.K_r: state=reset()

    keys=pygame.key.get_pressed()
    steer=(-1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)+(1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0)

    speed=0.85+0.02*((now-state["last"])/1000)

    if not state["over"]:
        state["player"].update(dt,steer)

        if now-state["last"]>SPAWN_MS:
            state["things"].append(Thing("ramp" if random.random()<RAMP_CHANCE else "suv"))
            state["last"]=now

        for t in list(state["things"]):
            t.update(dt,speed)
            if t.hit(state["player"]):
                if t.kind=="ramp":
                    state["player"].jump(2.2)
                    state["things"].remove(t)
                elif state["player"].air<0.28:
                    state["over"]=True
            if t.dead(): state["things"].remove(t)

        state["score"]+=speed*120*dt

    night=night_factor(now)

    screen.blit(BG_IMG,(0,0))
    draw_road(screen,now,night)
    draw_lamps(screen,night,now)

    for t in sorted(state["things"],key=lambda x:x.d,reverse=True):
        t.draw(screen)
    state["player"].draw(screen)

    if night>0:
        ov=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA)
        ov.fill((0,0,0,int(lerp(0,95,night))))
        screen.blit(ov,(0,0))

    draw_text(screen,"RIDERS",18,12,(0,0,0))
    draw_text(screen,f"Score: {int(state['score'])}",18,38,(0,0,0))

    if state["over"]:
        draw_text(screen,"GAME OVER",WIDTH//2,HEIGHT//2-30,center=True,fnt=big_font,color=(0,0,0))
        draw_text(screen,"R per ricominciare",WIDTH//2,HEIGHT//2+18,center=True,color=(0,0,0))

    pygame.display.flip()
