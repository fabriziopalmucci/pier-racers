import os
import random
import pygame
import asyncio
import traceback
import math

# -----------------------------
# Config
# -----------------------------
WIDTH, HEIGHT = 900, 600
FPS = 60

# Strada (questa è quella che hai detto VA BENE)
HORIZON_Y = int(HEIGHT * 0.50)
BOTTOM_Y  = int(HEIGHT * 0.975)

ROAD_NEAR_W = int(WIDTH * 1.32)
ROAD_FAR_W  = int(WIDTH * 0.14)

SPAWN_MS = 520
RAMP_CHANCE = 0.25

SPRITE_ROT_DEG = 0

# Giorno / notte
DAY_NIGHT_PERIOD_S = 60       # ciclo totale
DAY_NIGHT_FADE_S   = 3.0      # transizione smooth

# -----------------------------
# Init
# -----------------------------
pygame.init()
try:
    pygame.mixer.quit()
except Exception:
    pass

pygame.display.set_caption("Riders - NYC Day/Night")
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 24)
big_font = pygame.font.SysFont(None, 56)

APP_START_MS = pygame.time.get_ticks()

def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t

def draw_text(surf, text, x, y, color=(255,255,255), center=False, fnt=None):
    fnt = fnt or font
    img = fnt.render(text, True, color)
    rect = img.get_rect()
    rect.center = (x,y) if center else rect.move(x,y).topleft
    if not center:
        rect.topleft = (x,y)
    surf.blit(img, rect)

# -----------------------------
# Assets
# -----------------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

def load_png(name, fallback_size, color):
    path = os.path.join(ASSETS_DIR, name)
    try:
        return pygame.image.load(path).convert_alpha()
    except:
        s = pygame.Surface(fallback_size, pygame.SRCALPHA)
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
SUV1_IMG   = load_png("suv_black_1.png",(260,220),(35,35,40))
SUV2_IMG   = load_png("suv_green.png",(260,220),(20,120,60))
RAMP_IMG   = load_png("ramp_blue.png",(280,200),(70,130,255))
LAMP_IMG   = load_png("lamp_post.png",(512,512),(90,90,95))
BG_IMG     = load_bg("nyc_bg.png")

# -----------------------------
# Road geometry
# -----------------------------
def road_half_width_at_y(y):
    t = clamp((y-HORIZON_Y)/(BOTTOM_Y-HORIZON_Y),0,1)
    t2 = t**0.55
    return (ROAD_FAR_W + (ROAD_NEAR_W-ROAD_FAR_W)*t2)/2

# -----------------------------
# Giorno / notte STABILE
# -----------------------------
def get_night_factor(now_ms):
    t = (now_ms-APP_START_MS)/1000.0
    half = DAY_NIGHT_PERIOD_S/2.0

    target = 0.0 if (t%DAY_NIGHT_PERIOD_S)<half else 1.0
    prev   = 1.0-target

    t_in_half = t%half
    if t_in_half < DAY_NIGHT_FADE_S:
        x = clamp(t_in_half/DAY_NIGHT_FADE_S,0,1)
        x = 0.5-0.5*math.cos(math.pi*x)
        return prev*(1-x)+target*x
    return target

# -----------------------------
# Lampioni (FIX DEFINITIVO)
# -----------------------------
def draw_lamps_and_lights(surf, night_factor, t_ms):
    step = 170
    scroll = int((t_ms*0.12)%step)

    rows = int((BOTTOM_Y-(HORIZON_Y+25))//step)+3

    for i in range(rows):
        yy = int(BOTTOM_Y - (i*step - scroll))
        if yy<HORIZON_Y+25 or yy>HEIGHT+80:
            continue

        t = clamp((yy-HORIZON_Y)/(BOTTOM_Y-HORIZON_Y),0,1)
        t2 = t**0.6
        half = road_half_width_at_y(yy)

        inset = int(lerp(4,12,t2))
        lx = int(WIDTH/2-half+inset)
        rx = int(WIDTH/2+half-inset)

        scale = lerp(0.20,0.55,t2)
        w = int(LAMP_IMG.get_width()*scale)
        h = int(LAMP_IMG.get_height()*scale)
        lamp = pygame.transform.smoothscale(LAMP_IMG,(w,h))
        lamp_r = pygame.transform.flip(lamp,True,False)

        rL = lamp.get_rect(midbottom=(lx,yy))
        rR = lamp_r.get_rect(midbottom=(rx,yy))

        surf.blit(lamp,rL)
        surf.blit(lamp_r,rR)

        if night_factor>0.05:
            a1 = int(120*night_factor)
            a2 = int(70*night_factor)
            for r,side in ((rL,1),(rR,-1)):
                hx = r.centerx + int(w*0.26*side)
                hy = r.top + int(h*0.36)
                cone_h = int(lerp(110,320,t2))
                cone_w = int(lerp(110,320,t2))
                cone = pygame.Surface((cone_w,cone_h),pygame.SRCALPHA)
                pygame.draw.polygon(cone,(255,235,170,a1),
                                    [(cone_w//2,0),(0,cone_h),(cone_w,cone_h)])
                pygame.draw.polygon(cone,(255,235,170,a2),
                                    [(cone_w//2,0),(int(cone_w*0.18),cone_h),(int(cone_w*0.82),cone_h)])
                surf.blit(cone,(hx-cone_w//2,hy))

# -----------------------------
# Road drawing
# -----------------------------
def draw_road(surf, t_ms, night_factor):
    far,near = ROAD_FAR_W/2, ROAD_NEAR_W/2
    pts=[(WIDTH/2-far,HORIZON_Y),(WIDTH/2+far,HORIZON_Y),
         (WIDTH/2+near,BOTTOM_Y),(WIDTH/2-near,BOTTOM_Y)]

    asphalt_day=(155,155,162)
    asphalt_night=(70,70,76)
    asphalt=tuple(int(lerp(d,n,night_factor)) for d,n in zip(asphalt_day,asphalt_night))
    pygame.draw.polygon(surf,asphalt,pts)

    edge_day=(245,245,245)
    edge_night=(210,210,210)
    edge=tuple(int(lerp(d,n,night_factor)) for d,n in zip(edge_day,edge_night))
    pygame.draw.line(surf,edge,pts[0],pts[3],6)
    pygame.draw.line(surf,edge,pts[1],pts[2],6)

    dash_len,gap=26,18
    off=int((t_ms*0.32)%(dash_len+gap))
    for y in range(HORIZON_Y+8,int(BOTTOM_Y)+160,dash_len+gap):
        pygame.draw.rect(surf,(10,10,10),(WIDTH//2-3,y+off,6,dash_len),border_radius=3)

# -----------------------------
# Entities
# -----------------------------
class Player:
    def __init__(self):
        self.lane_x=0
        self.y=int(HEIGHT*0.88)
        self.steer_speed=1.75
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
        self.lane_x=clamp(self.lane_x+steer*self.steer_speed*dt,-0.98,0.98)
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

    def update(self,dt,speed):
        self.d-=speed*dt

    def dead(self): return self.d<-0.2

    def pos(self):
        t=clamp(1-self.d,0,1)
        y=int(lerp(HORIZON_Y+10,HEIGHT*0.90,t))
        x=int(WIDTH/2+self.lane_x*road_half_width_at_y(y))
        s=lerp(0.18,1.0,t)
        return x,y,s

    def draw(self,surf):
        x,y,sc=self.pos()
        src=RAMP_IMG if self.kind=="ramp" else (SUV1_IMG if self.var==1 else SUV2_IMG)
        w=int(src.get_width()*0.22*sc)
        h=int(src.get_height()*0.22*sc)
        img=pygame.transform.smoothscale(src,(w,h))
        surf.blit(img,img.get_rect(center=(x,y)))

    def hit(self,p):
        if not (0<=self.d<=0.1): return False
        x,_,_=self.pos()
        return abs(p.x()-x)<75

# -----------------------------
# Game loop
# -----------------------------
def reset():
    return {"player":Player(),"things":[],"score":0,"last_spawn":pygame.time.get_ticks(),"over":False}

state=reset()

while True:
    dt=clock.tick(FPS)/1000
    now=pygame.time.get_ticks()

    for e in pygame.event.get():
        if e.type==pygame.QUIT: pygame.quit(); sys.exit()
        if e.type==pygame.KEYDOWN:
            if not state["over"] and e.key==pygame.K_SPACE: state["player"].jump()
            if state["over"] and e.key==pygame.K_r: state=reset()

    keys=pygame.key.get_pressed()
    steer=(-1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)+(1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0)

    elapsed=(now-state["last_spawn"])/1000
    speed=0.85+0.02*elapsed

    if not state["over"]:
        state["player"].update(dt,steer)

        if now-state["last_spawn"]>SPAWN_MS:
            k="ramp" if random.random()<RAMP_CHANCE else "suv"
            state["things"].append(Thing(k))
            state["last_spawn"]=now

        for t in list(state["things"]):
            t.update(dt,speed)
            if t.hit(state["player"]):
                if t.kind=="ramp":
                    state["player"].jump(2.2)
                    state["things"].remove(t)
                else:
                    if state["player"].air<0.28: state["over"]=True
            if t.dead(): state["things"].remove(t)

        state["score"]+=speed*120*dt

    night=get_night_factor(now)

    screen.blit(BG_IMG,(0,0))
    draw_road(screen,now,night)
    draw_lamps_and_lights(screen,night,now)

    for t in sorted(state["things"],key=lambda x:x.d,reverse=True):
        t.draw(screen)

    state["player"].draw(screen)

    if night>0:
        ov=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA)
        ov.fill((0,0,0,int(160*night)))
        screen.blit(ov,(0,0))

    draw_text(screen,"RIDERS",18,12,(0,0,0))
    draw_text(screen,f"Score: {int(state['score'])}",18,40,(0,0,0))

    if state["over"]:
        draw_text(screen,"GAME OVER",WIDTH//2,HEIGHT//2-30,center=True,fnt=big_font,color=(0,0,0))
        draw_text(screen,"R per ricominciare",WIDTH//2,HEIGHT//2+18,center=True,color=(0,0,0))

    pygame.display.flip()
