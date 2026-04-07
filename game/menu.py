import pygame
import math
import time
import os
import shutil
import random
import subprocess
import sys
import threading
import json
import re

_FONT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets", "images", "fonts", "tacobae-font", "Tacobae-pge2K.otf",
)


# ─── Audio duration helper ───────────────────────────────────────────────────

def _audio_duration(path: str) -> float | None:
    """Return duration in seconds, or None if it can't be determined."""
    try:
        import soundfile as sf
        return sf.info(path).duration
    except Exception:
        pass
    try:
        import librosa
        return librosa.get_duration(path=path)
    except Exception:
        pass
    return None


# ─── File picker (subprocess to avoid tkinter/pygame crash) ──────────────────

def pick_audio_file() -> str | None:
    script = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk()\n"
        "root.withdraw()\n"
        "root.attributes('-topmost', True)\n"
        "path = filedialog.askopenfilename(\n"
        "    title='Select an Audio File',\n"
        "    filetypes=[('Audio Files','*.mp3 *.wav'),"
        "               ('MP3 Files','*.mp3'),('WAV Files','*.wav')])\n"
        "root.destroy()\n"
        "if path:\n"
        "    print(path)\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path if path else None
    except Exception:
        return None


# ─── Lyrics / word bank ──────────────────────────────────────────────────────

# fmt: off
_STOP_WORDS = {
    "the","a","an","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","shall","may",
    "might","must","can","to","of","in","on","at","by","for","with","from",
    "up","about","into","through","during","before","after","above","below",
    "between","and","but","or","nor","so","yet","both","either","neither",
    "not","also","just","than","then","that","this","these","those","it",
    "its","itself","he","she","they","we","you","i","me","my","mine","us",
    "our","him","his","her","their","your","yours","what","which","who",
    "whom","when","where","why","how","all","each","every","few","more",
    "most","other","some","such","no","only","own","same","too","very",
    "s","t","ll","ve","d","m","re","oh","yeah","ooh","ahh","hey","la",
    "na","da","ba","uh","mm","hmm","gonna","wanna","gotta","cause","cos",
    "coz","ima","tryna","lemme","dont","doesnt","didnt","wont","wouldnt",
    "couldnt","shouldnt","cant","isnt","arent","wasnt","werent","ive",
    "youre","youve","youll","youd","hes","shes","weve","theyre","theyve",
    "theyll","thats","theres","lets","id","here","there","now","still",
    "even","back","down","over","out","off","away","around","again",
    "never","always","ever","like","get","got","give","go","come","know",
    "see","say","told","make","made","take","think","feel","want","need",
    "look","keep","hold","find","let","put","run","try","turn","move",
    "seems","said","came","went","left","right","way","time","day","night",
    "long","life","good","bad","old","new","big","own","little","world",
    "man","boy","girl","love","one","two","three","four","five","six",
    "seven","eight","nine","ten",
}
# fmt: on

DEFAULT_WORD_BANK: list[str] = [
    # animals / transport
    "dog","cat","fish","bird","cow","pig","mouse","horse","wing","animal",
    "train","plane","car","truck","bicycle","bus","boat","ship","tire","engine",
    "ticket","airport","bridge","hotel","farm","court","school","office",
    "room","town","club","bar","park","camp","store","shop","theater",
    "library","hospital","church","market","country","building","ground",
    "space","bank","location",
    # clothing
    "hat","dress","suit","skirt","shirt","pants","shoes","pocket","coat",
    "stain","clothing",
    # colors
    "red","green","blue","yellow","brown","pink","orange","black","white",
    "gray","color",
    # people / family
    "son","daughter","mother","father","parent","baby","woman","brother",
    "sister","family","husband","wife","king","queen","president","neighbor",
    "girl","child","adult","human","friend","victim","player","crowd",
    "person","teacher","student","lawyer","doctor","patient","waiter",
    "priest","police","army","soldier","artist","author","manager",
    "reporter","actor",
    # society / abstract
    "job","religion","heaven","hell","death","medicine","money","dollar",
    "bill","marriage","wedding","team","race","gender","murder","prison",
    "energy","peace","attack","election","magazine","newspaper","poison",
    "sport","exercise","ball","game","price","contract","drug","sign",
    "science","band","song","music","movie",
    # food / drink
    "coffee","tea","wine","beer","juice","water","milk","cheese","bread",
    "soup","cake","chicken","pork","beef","apple","banana","lemon","corn",
    "rice","oil","seed","knife","spoon","fork","plate","cup","breakfast",
    "lunch","dinner","sugar","salt","bottle","food",
    # home / objects
    "table","chair","bed","dream","window","door","bedroom","kitchen",
    "bathroom","pencil","pen","soap","book","page","key","paint","letter",
    "note","wall","paper","floor","ceiling","roof","pool","lock","phone",
    "garden","yard","needle","bag","box","gift","card","ring","tool",
    "clock","lamp","fan",
    # tech
    "network","computer","program","laptop","screen","camera","radio",
    # body
    "head","neck","face","beard","hair","eye","mouth","lip","nose","tooth",
    "ear","tear","tongue","back","toe","finger","foot","hand","leg","arm",
    "shoulder","heart","blood","brain","knee","sweat","disease","bone",
    "voice","skin","body",
    # nature
    "sea","ocean","river","mountain","rain","snow","tree","sun","moon",
    "world","earth","forest","sky","plant","wind","soil","flower","valley",
    "root","lake","star","grass","leaf","air","sand","beach","wave","fire",
    "ice","island","hill","heat","nature",
    # materials / measurement
    "glass","metal","plastic","wood","stone","diamond","clay","dust","gold",
    "copper","silver","material","meter","inch","pound","half","circle",
    "square","date","weight","edge","corner","map","vowel","light","sound",
    "piece","pain","injury","hole","image","pattern","noun","verb",
    "bottom","side","front","outside","inside","straight","north","south",
    "east","west","direction","summer","spring","winter","season",
    # verbs
    "work","play","walk","run","drive","fly","swim","stop","follow","think",
    "speak","eat","drink","smile","laugh","cry","buy","sell","shoot","learn",
    "jump","smell","hear","listen","taste","touch","watch","kiss","burn",
    "melt","explode","stand","love","cut","fight","dance","sleep","sing",
    "count","marry","pray","lose","stir","bend","wash","cook","open","close",
    "write","call","turn","build","teach","grow","draw","feed","catch",
    "throw","clean","find","push","pull","carry","break","wear","hang",
    "shake","beat","lift",
    # adjectives
    "long","short","tall","wide","narrow","large","small","little","slow",
    "fast","cold","warm","cool","young","weak","alive","heavy","dark","famous",
]


def _extract_notable_words(lyrics: str) -> list[str]:
    words = re.findall(r"[a-z]+", lyrics.lower())
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w not in seen and w not in _STOP_WORDS and 3 <= len(w) <= 9:
            seen.add(w)
            result.append(w)
    # sample evenly to target ~65 words
    if len(result) > 70:
        step = len(result) / 65
        result = [result[int(i * step)] for i in range(65)]
    return result


def _fetch_lyrics_words(artist: str, title: str) -> list[str]:
    """Fetch from lyrics.ovh and extract notable words. Returns [] on failure."""
    import urllib.parse, urllib.request
    try:
        url = (
            "https://api.lyrics.ovh/v1/"
            + urllib.parse.quote(artist.strip())
            + "/"
            + urllib.parse.quote(title.strip())
        )
        req = urllib.request.Request(url, headers={"User-Agent": "KeyDash/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        lyrics = data.get("lyrics", "")
        if not lyrics:
            return []
        words = _extract_notable_words(lyrics)
        # Require at least 15 distinct words — otherwise assume non-English / bad data
        return words if len(words) >= 15 else []
    except Exception:
        return []


# ─── Persistent song word-bank store ─────────────────────────────────────────

_WORD_BANK_FILE = os.path.join("assets", "song_words.json")


def _load_word_banks() -> dict[str, list[str]]:
    try:
        with open(_WORD_BANK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_word_banks(banks: dict[str, list[str]]) -> None:
    try:
        with open(_WORD_BANK_FILE, "w", encoding="utf-8") as f:
            json.dump(banks, f, indent=2)
    except Exception:
        pass


# ─── Per-song top-score persistence ─────────────────────────────────────────

_SCORES_FILE = os.path.join("assets", "scores.json")


def _load_scores() -> dict:
    try:
        with open(_SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_scores(scores: dict) -> None:
    try:
        os.makedirs("assets", exist_ok=True)
        with open(_SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, indent=2)
    except Exception:
        pass


# ─── Floating petal background particle ─────────────────────────────────────

class Petal:
    COLORS = [
        (160, 160, 160),
        (210, 210, 210),
        (80,  80,  80),
        (255, 20,  147),
        (140, 210, 255),
    ]

    def __init__(self, sw, sh, randomize_y=True):
        self.sw, self.sh = sw, sh
        self._init(randomize_y)

    def _init(self, randomize_y=True):
        self.x         = random.uniform(0, self.sw)
        self.y         = random.uniform(0, self.sh) if randomize_y else random.uniform(-60, -10)
        self.vx        = random.uniform(-0.35, 0.35)
        self.vy        = random.uniform(0.12, 0.5)
        self.rotation  = random.uniform(0, 360)
        self.rot_speed = random.uniform(-0.7, 0.7)
        self.color     = random.choice(self.COLORS)
        self.alpha     = random.randint(10, 65)
        self.w         = random.randint(5, 16)
        self.h         = random.randint(10, 26)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.rotation += self.rot_speed
        if self.y > self.sh + 50:
            self._init(False)
        if self.x < -50:
            self.x = self.sw + 50
        elif self.x > self.sw + 50:
            self.x = -50

    def draw(self, screen):
        surf = pygame.Surface((self.w * 2 + 2, self.h * 2 + 2), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (*self.color, self.alpha), (1, 1, self.w * 2, self.h * 2))
        rotated = pygame.transform.rotate(surf, self.rotation)
        screen.blit(rotated, rotated.get_rect(center=(int(self.x), int(self.y))))


# ─── Generic text button ─────────────────────────────────────────────────────

class Button:
    def __init__(self, rect, text, font,
                 base_color=(255, 255, 255), hover_color=(200, 220, 255)):
        self.rect          = pygame.Rect(rect)
        self.text          = text
        self.font          = font
        self.base_color    = base_color
        self.hover_color   = hover_color
        self.is_hovered    = False
        self._scale        = 1.0
        self._target_scale = 1.0

    def check_hover(self, mouse_pos):
        self.is_hovered    = self.rect.collidepoint(mouse_pos)
        self._target_scale = 1.08 if self.is_hovered else 1.0

    def check_click(self, mouse_pos, mouse_clicked):
        return mouse_clicked and self.rect.collidepoint(mouse_pos)

    def draw(self, screen, _current_time):
        self._scale += (self._target_scale - self._scale) * 0.18
        color = self.hover_color if self.is_hovered else self.base_color
        if self.is_hovered:
            pygame.draw.rect(screen, (80, 80, 100), self.rect.inflate(8, 8), 2, border_radius=8)
        surf = self.font.render(self.text, True, color)
        sw   = int(surf.get_width()  * self._scale)
        sh   = int(surf.get_height() * self._scale)
        if sw > 0 and sh > 0:
            surf = pygame.transform.smoothscale(surf, (sw, sh))
        screen.blit(surf, surf.get_rect(center=self.rect.center))


# ─── Single-line text input ───────────────────────────────────────────────────

class TextInput:
    def __init__(self, rect, font, placeholder="", max_length=80):
        self.rect        = pygame.Rect(rect)
        self.font        = font
        self.placeholder = placeholder
        self.max_length  = max_length
        self.text        = ""
        self.active      = False

    def handle_events(self, events):
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.active = self.rect.collidepoint(event.pos)
            if self.active and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_TAB):
                    self.active = False
                elif event.unicode.isprintable() and len(self.text) < self.max_length:
                    self.text += event.unicode

    def draw(self, screen, current_time):
        bg    = (40, 40, 55)  if self.active else (22, 22, 32)
        bord  = (140, 180, 255) if self.active else (70, 70, 95)
        pygame.draw.rect(screen, bg,   self.rect, border_radius=8)
        pygame.draw.rect(screen, bord, self.rect, 2, border_radius=8)

        display  = self.text if self.text else self.placeholder
        color    = (235, 235, 255) if self.text else (90, 90, 115)
        surf     = self.font.render(display, True, color)
        pad      = 10
        text_x   = self.rect.x + pad
        text_y   = self.rect.centery - surf.get_height() // 2

        # clip text to rect
        old_clip = screen.get_clip()
        screen.set_clip(self.rect.inflate(-4, -4))
        screen.blit(surf, (text_x, text_y))
        screen.set_clip(old_clip)

        # blinking cursor
        if self.active and int(current_time * 2) % 2 == 0:
            cx = text_x + min(self.font.size(self.text)[0], self.rect.w - pad * 2)
            pygame.draw.line(screen, (200, 200, 255),
                             (cx, text_y + 2), (cx, text_y + surf.get_height() - 2), 2)


# ─── Difficulty selector  ◀ Medium ▶ ────────────────────────────────────────

class DifficultySelector:
    LABELS = ["Easy",    "Fair",    "Hard"  ]
    KEYS   = ["journey", "classic", "master"]
    COLORS = [
        (90,  210, 90),
        (220, 200, 70),
        (220, 85,  85),
    ]

    def __init__(self, center_x, center_y, font):
        self.cx, self.cy = center_x, center_y
        self.font        = font
        self.selected    = 1

        self._slide_offset = 0.0
        self._left_rect:  pygame.Rect | None = None
        self._right_rect: pygame.Rect | None = None

        self._max_label_w = max(font.size(l)[0] for l in self.LABELS)

    @property
    def difficulty(self) -> str:
        return self.KEYS[self.selected]

    def check_hover(self, _pos):
        pass

    def check_click(self, mouse_pos, mouse_clicked) -> bool:
        if not mouse_clicked:
            return False
        if self._left_rect and self._left_rect.collidepoint(mouse_pos) and self.selected > 0:
            self.selected      -= 1
            self._slide_offset  = -self._max_label_w * 0.9
            return True
        if self._right_rect and self._right_rect.collidepoint(mouse_pos) and self.selected < 2:
            self.selected      += 1
            self._slide_offset  = self._max_label_w * 0.9
            return True
        return False

    @staticmethod
    def _draw_arrow(screen, color, cx, cy, direction, w=11, h=16):
        hw, hh = w // 2, h // 2
        if direction == 'left':
            pts = [(cx - hw, cy), (cx + hw, cy - hh), (cx + hw, cy + hh)]
        else:
            pts = [(cx + hw, cy), (cx - hw, cy - hh), (cx - hw, cy + hh)]
        pygame.draw.polygon(screen, color, pts)

    def draw(self, screen, _current_time, y_offset=0):
        self._slide_offset += (0.0 - self._slide_offset) * 0.20
        if abs(self._slide_offset) < 0.5:
            self._slide_offset = 0.0

        eff_cy = self.cy - y_offset
        label  = self.LABELS[self.selected]
        color  = self.COLORS[self.selected]
        text_surf = self.font.render(label, True, color)
        tw, th    = text_surf.get_size()

        arrow_color = (160, 160, 160)
        arrow_gap   = 12
        aw, ah      = 11, 16

        label_left  = self.cx - self._max_label_w // 2
        label_right = self.cx + self._max_label_w // 2

        if self.selected > 0:
            tip_cx = label_left - arrow_gap - aw // 2
            self._draw_arrow(screen, arrow_color, tip_cx, eff_cy, 'left', aw, ah)
            self._left_rect = pygame.Rect(tip_cx - aw - 4, eff_cy - ah // 2 - 4, aw * 2 + 8, ah + 8)
        else:
            self._left_rect = None

        if self.selected < 2:
            tip_cx = label_right + arrow_gap + aw // 2
            self._draw_arrow(screen, arrow_color, tip_cx, eff_cy, 'right', aw, ah)
            self._right_rect = pygame.Rect(tip_cx - aw - 4, eff_cy - ah // 2 - 4, aw * 2 + 8, ah + 8)
        else:
            self._right_rect = None

        clip_rect = pygame.Rect(
            int(self.cx - self._max_label_w // 2), int(eff_cy - th // 2 - 2),
            self._max_label_w, th + 4,
        )
        old_clip = screen.get_clip()
        screen.set_clip(clip_rect)
        screen.blit(text_surf, (int(self.cx + self._slide_offset - tw // 2), int(eff_cy - th // 2)))
        screen.set_clip(old_clip)


# ─── Image button (hover scale + click shrink→bounce) ────────────────────────

_EXIT_IMG = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets", "images", "exitbutton.png",
)

class ImageButton:
    """Clickable image that scales on hover and bounces on click."""
    _HOVER_SCALE  = 1.12
    _CLICK_SHRINK = 0.75
    _CLICK_BOUNCE = 1.18
    _LERP_NORMAL  = 0.12
    _LERP_FAST    = 0.25

    def __init__(self, cx: int, cy: int, size: int, image_path: str):
        raw         = pygame.image.load(image_path).convert_alpha()
        self._base  = raw
        self._size  = size
        self.cx     = cx
        self.cy     = cy
        self._scale       = 1.0
        self._click_phase = None   # None | "shrink" | "bounce"
        self.rect = pygame.Rect(cx - size // 2, cy - size // 2, size, size)

    def _hovered(self, mouse_pos) -> bool:
        half = max(1, int(self._size * self._scale)) // 2
        return pygame.Rect(self.cx - half, self.cy - half, half * 2, half * 2).collidepoint(mouse_pos)

    def update(self, mouse_pos, mouse_clicked) -> bool:
        """Returns True on the frame the click fires."""
        hovered = self._hovered(mouse_pos)
        if mouse_clicked and hovered and self._click_phase is None:
            self._click_phase = "shrink"

        if self._click_phase == "shrink":
            self._scale += (self._CLICK_SHRINK - self._scale) * self._LERP_FAST
            if abs(self._scale - self._CLICK_SHRINK) < 0.025:
                self._click_phase = "bounce"
        elif self._click_phase == "bounce":
            self._scale += (self._CLICK_BOUNCE - self._scale) * self._LERP_FAST
            if abs(self._scale - self._CLICK_BOUNCE) < 0.025:
                self._click_phase = None
                self._scale = self._HOVER_SCALE if hovered else 1.0
                return True
        else:
            target = self._HOVER_SCALE if hovered else 1.0
            self._scale += (target - self._scale) * self._LERP_NORMAL
        return False

    def draw(self, screen, _current_time=None):
        disp = max(1, int(self._size * self._scale))
        surf = pygame.transform.smoothscale(self._base, (disp, disp))
        screen.blit(surf, surf.get_rect(center=(self.cx, self.cy)))


# ─── PNG sequence sprite ─────────────────────────────────────────────────────

class PNGSequenceSprite:
    """Plays a sorted sequence of transparent PNGs at a fixed FPS.

    All frames are pre-loaded and optionally scaled at construction time so
    playback is allocation-free.  Call ``advance(dt)`` each game tick and read
    ``current`` to get the surface to blit.
    """

    def __init__(self, folder: str, fps: float = 30.0,
                 scale: tuple[int, int] | None = None) -> None:
        self.fps = fps
        self._acc: float = 0.0
        self._idx: int = 0
        self._frames: list[pygame.Surface] = []

        if not os.path.isdir(folder):
            return

        paths = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".png")
        )
        for path in paths:
            surf = pygame.image.load(path).convert_alpha()
            if scale is not None:
                surf = pygame.transform.smoothscale(surf, scale)
            self._frames.append(surf)

    @property
    def ready(self) -> bool:
        return len(self._frames) > 0

    @property
    def current(self) -> pygame.Surface | None:
        if not self._frames:
            return None
        return self._frames[self._idx]

    def advance(self, dt: float = 1.0 / 60.0) -> None:
        """Advance the animation by *dt* seconds.  Call once per game tick."""
        if not self._frames:
            return
        self._acc += dt
        frame_dur = 1.0 / self.fps
        while self._acc >= frame_dur:
            self._acc -= frame_dur
            self._idx = (self._idx + 1) % len(self._frames)




# ─── Title screen ────────────────────────────────────────────────────────────

class TitleScreen:
    _ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "images")

    # play-button animation constants
    _HOVER_SCALE   = 1.18
    _CLICK_SHRINK  = 0.72
    _CLICK_BOUNCE  = 1.22
    _LERP_NORMAL   = 0.10
    _LERP_FAST     = 0.22

    # beat-pulse constants
    _BPM_INTRO     = 72.0   # first-time intro (synced to title2.wav)
    _BPM_RETURN    = 125.0  # after coming back from level select
    _BEAT_PEAK     = 1.14   # title scale on the beat
    _BTN_BEAT_PEAK = 1.20   # button scale boost on the beat
    _BEAT_LERP     = 0.18   # how fast the scale chases the target each frame

    def __init__(self, screen):
        self.screen = screen
        sw, sh = screen.get_size()

        # ── Title image ──────────────────────────────────────────────────
        raw_title = pygame.image.load(
            os.path.join(self._ASSETS, "noki_maintitle.png")
        ).convert_alpha()
        target_w      = int(sw * 0.325)
        target_h      = int(raw_title.get_height() * target_w / raw_title.get_width())
        self.title_img     = raw_title          # keep original full-res for scaling
        self._title_base_w = target_w
        self._title_base_h = target_h
        self.title_cx      = sw // 2 + int(sw * 0.15)
        self.title_cy      = sh // 2 - target_h // 2 + 20

        # beat-pulse scale for title
        self._title_scale        = 1.0
        self._title_scale_target = 1.0

        # ── Play button image ─────────────────────────────────────────────
        raw_btn = pygame.image.load(
            os.path.join(self._ASSETS, "playbutton.png")
        ).convert_alpha()
        btn_size = int(sh * 0.10 * 1.20)       # 20 % larger than before
        self._btn_base = raw_btn                # keep original for smooth scaling
        self._btn_size = btn_size
        self.btn_cx = sw // 2 + int(sw * 0.15)
        self.btn_cy = sh // 2 + target_h // 2 + 60

        # click animation state
        self._scale       = 1.0
        self._click_phase = None   # None | "shrink" | "bounce"

        # rect used by MenuManager as the transition origin
        self.play_button_rect = pygame.Rect(
            self.btn_cx - btn_size // 2,
            self.btn_cy - btn_size // 2,
            btn_size, btn_size,
        )

        # beat tracking — starts at intro BPM, switches to 125 on return
        self._beat_period  = 60.0 / self._BPM_INTRO
        self._last_beat    = -1

        # ── noki_bop looping video ────────────────────────────────────────
        # Positioned centered vertically, 1/4 of screen width from left edge
        _BOP_PATH = os.path.join(self._ASSETS, "noki_bop.mov")
        self._bop_cap       = None
        self._bop_fps       = 30.0
        self._bop_acc       = 0.0
        self._bop_surf      = None
        # noki_bop is 100 BPM — loop duration = 1.2s
        # Scale height to ~1/5 of screen height
        self._bop_h         = int(sh * 0.40)
        self._bop_cx        = sw // 4 + int(sw * 0.06)
        # bottom of bop aligns with bottom of play button
        _btn_bottom         = self.btn_cy + btn_size // 2
        self._bop_cy        = _btn_bottom - self._bop_h // 2
        self._spotlight_surf = None
        try:
            import cv2 as _cv2
            _cap = _cv2.VideoCapture(_BOP_PATH)
            if _cap.isOpened():
                _fps = _cap.get(_cv2.CAP_PROP_FPS)
                if _fps > 0:
                    self._bop_fps = _fps
                _fw = _cap.get(_cv2.CAP_PROP_FRAME_WIDTH)
                _fh = _cap.get(_cv2.CAP_PROP_FRAME_HEIGHT)
                self._bop_cap = _cap

                # Load spotlight.png: 30% wider than bop, extends 10% screen below bop bottom
                _bop_w  = int(_fw * self._bop_h / _fh) if _fh > 0 else self._bop_h
                _spot_w = int(_bop_w * 0.78)
                _spot_h = int((_btn_bottom + int(sh * 0.10)) * 1.15)   # +15% vertical stretch
                _raw    = pygame.image.load(
                    os.path.join(self._ASSETS, "spotlight.png")
                ).convert_alpha()
                _spot   = pygame.transform.smoothscale(_raw, (_spot_w, _spot_h))
                _spot.set_alpha(int(255 * 0.19))
                self._spotlight_surf = _spot
        except ImportError:
            pass

    def _btn_hovered(self, mouse_pos) -> bool:
        half = int(self._btn_size * self._scale) // 2
        r = pygame.Rect(self.btn_cx - half, self.btn_cy - half, half * 2, half * 2)
        return r.collidepoint(mouse_pos)

    def reset(self):
        """Call whenever the title screen becomes active to clear stale animation state.
        Switches to 125 BPM (return visits after the play button has been pressed)."""
        self._beat_period        = 60.0 / self._BPM_RETURN
        self._last_beat          = -1
        self._bop_acc            = 0.0
        self._title_scale        = 1.0
        self._title_scale_target = 1.0
        self._scale              = 1.0
        self._click_phase        = None
        if self._bop_cap is not None:
            try:
                import cv2 as _cv2
                self._bop_cap.set(_cv2.CAP_PROP_POS_FRAMES, 0)
            except Exception:
                pass

    def update(self, mouse_pos, mouse_clicked, current_time):
        hovered = self._btn_hovered(mouse_pos)

        if mouse_clicked and hovered and self._click_phase is None:
            self._click_phase = "shrink"

        # ── click animation ──────────────────────────────────────────────
        if self._click_phase == "shrink":
            target = self._CLICK_SHRINK
            self._scale += (target - self._scale) * self._LERP_FAST
            if abs(self._scale - target) < 0.025:
                self._click_phase = "bounce"

        elif self._click_phase == "bounce":
            target = self._CLICK_BOUNCE
            self._scale += (target - self._scale) * self._LERP_FAST
            if abs(self._scale - target) < 0.025:
                self._click_phase = None
                self._scale = self._HOVER_SCALE if hovered else 1.0
                return "play"

        else:
            # ── noki_bop video advance ────────────────────────────────────
            if self._bop_cap is not None:
                import cv2 as _cv2
                self._bop_acc += 1.44 / 60.0
                frame_dur = 1.0 / self._bop_fps
                while self._bop_acc >= frame_dur:
                    self._bop_acc -= frame_dur
                    ret, frame = self._bop_cap.read()
                    if not ret:
                        self._bop_cap.set(_cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self._bop_cap.read()
                    if ret:
                        frame_rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
                        fh, fw = frame_rgb.shape[:2]
                        sw_f = int(fw * self._bop_h / fh)
                        surf = pygame.surfarray.make_surface(frame_rgb.transpose(1, 0, 2))
                        self._bop_surf = pygame.transform.smoothscale(surf, (sw_f, self._bop_h))

            # ── beat pulse ────────────────────────────────────────────────
            beat_idx = int(current_time / self._beat_period)
            if beat_idx != self._last_beat:
                self._last_beat          = beat_idx
                self._title_scale_target = self._BEAT_PEAK
                # only kick button beat when not in hover/click animation
                if not hovered:
                    self._scale = 1.0 + (self._BTN_BEAT_PEAK - 1.0)

            # title scale lerps back to 1.0
            self._title_scale_target += (1.0 - self._title_scale_target) * self._BEAT_LERP
            self._title_scale        += (self._title_scale_target - self._title_scale) * self._BEAT_LERP

            # button scale lerps toward hover/rest
            base_target = self._HOVER_SCALE if hovered else 1.0
            self._scale += (base_target - self._scale) * self._LERP_NORMAL

        return None

    def draw(self, _current_time):
        # ── noki_bop looping video ────────────────────────────────────────
        if self._bop_surf is not None:
            self.screen.blit(self._bop_surf,
                             self._bop_surf.get_rect(center=(self._bop_cx, self._bop_cy)))

        # ── spotlight on top of bop ───────────────────────────────────────
        if self._spotlight_surf is not None:
            _sh = self.screen.get_height()
            self.screen.blit(self._spotlight_surf,
                             self._spotlight_surf.get_rect(midbottom=(self._bop_cx, self._bop_cy + self._bop_h // 2 + int(_sh * 0.05))))

        # ── beat-scaled title ────────────────────────────────────────────
        tw = max(1, int(self._title_base_w * self._title_scale))
        th = max(1, int(self._title_base_h * self._title_scale))
        title_surf = pygame.transform.smoothscale(self.title_img, (tw, th))
        self.screen.blit(title_surf, title_surf.get_rect(center=(self.title_cx, self.title_cy)))

        # scaled play button
        disp_size = max(1, int(self._btn_size * self._scale))
        btn_surf  = pygame.transform.smoothscale(self._btn_base, (disp_size, disp_size))
        self.screen.blit(btn_surf, btn_surf.get_rect(center=(self.btn_cx, self.btn_cy)))


# ─── Level select screen ─────────────────────────────────────────────────────

class LevelSelect:
    _LEFT_FRAC  = 0.35
    _RIGHT_FRAC = 0.65

    # rank thresholds (best score across all difficulties)
    _RANKS = [
        (80_000, "S", (255, 215,   0)),   # gold
        (50_000, "A", (100, 210, 255)),   # cyan
        (25_000, "B", ( 90, 220,  90)),   # green
        (10_000, "C", (220, 200,  70)),   # yellow
        (     1, "D", (210,  90,  90)),   # red
    ]

    def __init__(self, screen, song_names, scores=None):
        self.screen     = screen
        self.song_names = song_names
        self._scores    = scores or {}
        sw, sh = screen.get_size()

        self.header_font  = pygame.font.Font(_FONT, 60)
        self.button_font  = pygame.font.Font(_FONT, 42)
        self.diff_font    = pygame.font.Font(_FONT, 36)
        self.upload_font1 = pygame.font.Font(_FONT, 96)
        self.upload_font2 = pygame.font.Font(_FONT, 78)

        self.scroll_offset  = 0
        self.button_height  = 56
        self.button_spacing = 22      # more breathing room between rows
        self.list_top       = 120

        # ── Scrollbar geometry (right edge of right panel) ───────────────
        self._sb_w      = 6
        self._sb_margin = 12
        self._sb_x      = sw - self._sb_margin - self._sb_w
        self._sb_y      = self.list_top
        self._sb_h      = sh - self.list_top - 20
        self._sb_drag   = False
        self._sb_drag_start_y      = 0
        self._sb_drag_start_offset = 0

        # ── Upload zone (left 35%) ───────────────────────────────────────
        div_x = int(sw * self._LEFT_FRAC)
        self.upload_cx = div_x // 2
        self.upload_cy = sh // 2 + int(sh * 0.24)

        tw1, tw2 = self.upload_font1.size("Upload")[0], self.upload_font2.size("A File!")[0]
        th1, th2 = self.upload_font1.get_height(), self.upload_font2.get_height()
        gap = 8
        pad_x, pad_y = 28, 20
        btn_w = max(tw1, tw2) + pad_x * 2
        btn_h = th1 + gap + th2 + pad_y * 2
        self.upload_rect = pygame.Rect(
            self.upload_cx - btn_w // 2, self.upload_cy - btn_h // 2, btn_w, btn_h
        )
        self._upload_hovered = False
        self._upload_scale   = 1.0
        self._upload_line1_y_off = -(th1 + gap + th2) // 2 + th1 // 2
        self._upload_line2_y_off = self._upload_line1_y_off + th1 // 2 + gap + th2 // 2

        # ── noki_base_loop + eye overlays (all PNG sequences) ───────────────
        _assets = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "images")
        _loop_bottom = self.upload_rect.top + 6
        self._noki_loop_cx     = self.upload_cx
        self._noki_loop_bottom = _loop_bottom
        self._mouse_pos        = (sw // 2, sh // 2)
        self._eye_ox           = 0
        self._eye_oy           = 0
        self._eye_track_acc    = 0.0
        self._noki_loop_w      = 0
        self._noki_loop_h      = 0

        # Derive scale from first frame of noki_base_loop
        _base_dir = os.path.join(_assets, "noki_base_loop")
        _avail_h  = _loop_bottom - 20
        _body_scale: tuple[int, int] | None = None
        if os.path.isdir(_base_dir):
            _first = next(
                (os.path.join(_base_dir, f)
                 for f in sorted(os.listdir(_base_dir))
                 if f.lower().endswith(".png")),
                None,
            )
            if _first:
                _tmp = pygame.image.load(_first)
                _pw, _ph = _tmp.get_size()
                _bh = min(_avail_h, _ph)
                _bw = int(_pw * _bh / _ph) if _ph > 0 else _pw
                _body_scale = (_bw, _bh)
                self._noki_loop_w = _bw
                self._noki_loop_h = _bh

        self._noki_loop_seq = PNGSequenceSprite(
            _base_dir, fps=30.0, scale=_body_scale
        )

        # Shift noki + eyes down by 25% of the body image height
        self._noki_loop_bottom = _loop_bottom + int(sh * 0.13)

        # Eye PNG sequences — same scale as body, untouched
        _eye_scale: tuple[int, int] | None = _body_scale
        self._leye_seq = PNGSequenceSprite(
            os.path.join(_assets, "left"), fps=30.0, scale=_eye_scale
        )
        self._reye_seq = PNGSequenceSprite(
            os.path.join(_assets, "right"), fps=30.0, scale=_eye_scale
        )

        # ── Song list (right 65%) ────────────────────────────────────────
        # btn_x anchored close to the divider so names get maximum width.
        # diff_cx pinned near the scrollbar so there's always a fixed right margin.
        # Rank badge on the right — reserve space for one character + padding
        self._rank_font = pygame.font.Font(_FONT, 44)
        _rank_char_w    = self._rank_font.size("S")[0]
        _rank_col_w     = _rank_char_w + 24          # badge column width
        self._rank_cx   = self._sb_x - self._sb_margin - _rank_col_w // 2 - 4

        self.btn_x = div_x + 20
        self.btn_w = self._rank_cx - _rank_col_w // 2 - 24 - self.btn_x

        # Keep difficulty_selectors alive (used by MenuManager for initial LevelMenu state)
        self.diff_cx = self._rank_cx   # unused for drawing; satisfies old references

        # store full (un-truncated) display names for marquee rendering
        self._full_names: list[str] = []

        self.level_buttons:        list[Button]             = []
        self.difficulty_selectors: list[DifficultySelector] = []

        for i, name in enumerate(song_names):
            display = os.path.splitext(name)[0]
            self._full_names.append(display)
            btn_y = self.list_top + i * (self.button_height + self.button_spacing)
            self.level_buttons.append(Button(
                (self.btn_x, btn_y, self.btn_w, self.button_height),
                display, self.button_font,
            ))
            self.difficulty_selectors.append(
                DifficultySelector(self._rank_cx, btn_y + self.button_height // 2, self.diff_font)
            )

        # inline rename state (set by begin_rename after upload)
        self._rename_idx: int | None = None
        self._rename_input: TextInput | None = None
        self._rename_result: tuple[int, str] = (0, "")
        self._rename_font = pygame.font.Font(_FONT, 42)   # matches button_font

        _btn_sz = 52
        self.back_button = ImageButton(30 + _btn_sz // 2, 30 + _btn_sz // 2, _btn_sz, _EXIT_IMG)
        total = len(song_names) * (self.button_height + self.button_spacing)
        self.max_scroll = max(0, total - (sh - self.list_top - 40))

    def begin_rename(self, idx: int):
        """Start an inline rename for the slot at idx (scroll it into view first)."""
        self._rename_idx = idx
        btn = self.level_buttons[idx]
        # build a TextInput that fills the button's text area
        rect = pygame.Rect(btn.rect.x + 8, btn.rect.y + 8,
                           btn.rect.w - 16, btn.rect.h - 16)
        self._rename_input = TextInput(rect, self._rename_font, placeholder="Enter song name…")
        self._rename_input.active = True
        # scroll so the new slot is visible
        target_y = btn.rect.y - self.list_top
        self.scroll_offset = max(0, min(target_y, self.max_scroll))

    def _finish_rename(self) -> tuple[int, str] | None:
        """Commit rename; returns (idx, new_display) or None if blank (keep original)."""
        idx   = self._rename_idx
        inp   = self._rename_input
        self._rename_idx   = None
        self._rename_input = None
        if idx is None or inp is None:
            return None
        name = inp.text.strip()
        return (idx, name) if name else None

    def _best_rank(self, song_name: str) -> tuple[str, tuple] | None:
        """Return (letter, color) for the best score across all difficulties, or None."""
        song_scores = self._scores.get(song_name, {})
        if not song_scores:
            return None
        best = max(song_scores.values())
        for threshold, letter, color in self._RANKS:
            if best >= threshold:
                return letter, color
        return None

    def handle_scroll(self, event):
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_offset -= event.y * 30
            self.scroll_offset  = max(0, min(self.scroll_offset, self.max_scroll))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._sb_drag = False
        elif event.type == pygame.MOUSEMOTION and self._sb_drag:
            dy = event.pos[1] - self._sb_drag_start_y
            if self._sb_h > 0 and self.max_scroll > 0:
                self.scroll_offset = self._sb_drag_start_offset + int(
                    dy * 0.9 * self.max_scroll / self._sb_h
                )
            self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))

    def _sb_thumb_rect(self) -> pygame.Rect | None:
        """Return the scrollbar thumb rect, or None if scrollbar isn't needed."""
        if self.max_scroll <= 0:
            return None
        total_rows = len(self.level_buttons)
        if total_rows == 0:
            return None
        viewport_h = self._sb_h
        total_h    = total_rows * (self.button_height + self.button_spacing)
        thumb_h    = max(24, int(viewport_h * viewport_h / total_h))
        thumb_y    = self._sb_y + int(
            (viewport_h - thumb_h) * self.scroll_offset / self.max_scroll
        )
        return pygame.Rect(self._sb_x, thumb_y, self._sb_w, thumb_h)

    def update(self, mouse_pos, mouse_clicked, _current_time, events=None):
        self._mouse_pos = mouse_pos

        # ── inline rename mode ───────────────────────────────────────────
        if self._rename_input is not None and events is not None:
            for ev in events:
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_RETURN:
                        result = self._finish_rename()
                        if result is not None:
                            self._rename_result = result
                            return "rename", result[0]
                        return None, -1
                    elif ev.key == pygame.K_ESCAPE:
                        cancel_idx = self._rename_idx if self._rename_idx is not None else -1
                        self._rename_idx   = None
                        self._rename_input = None
                        return "cancel_upload", cancel_idx
                    elif ev.key == pygame.K_BACKSPACE:
                        self._rename_input.text = self._rename_input.text[:-1]
                    elif ev.unicode.isprintable():
                        if len(self._rename_input.text) < 80:
                            self._rename_input.text += ev.unicode
            return None, -1  # swallow all other actions while renaming

        if self.back_button.update(mouse_pos, mouse_clicked):
            return "back", -1

        self._upload_hovered = self.upload_rect.collidepoint(mouse_pos)
        if mouse_clicked and self._upload_hovered:
            return "upload", -1

        # Scrollbar click / drag start
        if mouse_clicked and self.max_scroll > 0:
            thumb = self._sb_thumb_rect()
            if thumb and thumb.collidepoint(mouse_pos):
                self._sb_drag = True
                self._sb_drag_start_y      = mouse_pos[1]
                self._sb_drag_start_offset = self.scroll_offset
            else:
                track = pygame.Rect(self._sb_x, self._sb_y, self._sb_w, self._sb_h)
                if track.collidepoint(mouse_pos):
                    # Click on track: jump
                    t = (mouse_pos[1] - self._sb_y) / self._sb_h
                    self.scroll_offset = int(t * self.max_scroll)
                    self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))

        adj = (mouse_pos[0], mouse_pos[1] + self.scroll_offset)
        for i, btn in enumerate(self.level_buttons):
            btn.check_hover(adj)
            if btn.check_click(adj, mouse_clicked):
                return "select", i

        # ── advance all PNG sequences ────────────────────────────────────
        self._noki_loop_seq.advance(1.0 / 60.0)
        self._leye_seq.advance(1.0 / 60.0)
        self._reye_seq.advance(1.0 / 60.0)

        # ── update eye tracking at 12 fps ────────────────────────────────
        self._eye_track_acc += 1.0 / 60.0
        if self._eye_track_acc >= 1.0 / 10.0:
            self._eye_track_acc = 0.0
            if self._noki_loop_h > 0:
                _sh = self.screen.get_height()
                _eye_radius = _sh * 0.01
                _img_top = self._noki_loop_bottom - self._noki_loop_h
                _eye_cx  = float(self._noki_loop_cx)
                _eye_cy  = _img_top + self._noki_loop_h * (1.0 - 0.66)
                _dx = self._mouse_pos[0] - _eye_cx
                _dy = self._mouse_pos[1] - _eye_cy
                _dist = (_dx * _dx + _dy * _dy) ** 0.5
                if _dist > 0:
                    _sf = min(1.0, _eye_radius / _dist)
                    self._eye_ox = int(_dx * _sf)
                    self._eye_oy = int(_dy * _sf)
                else:
                    self._eye_ox, self._eye_oy = 0, 0

        return None, -1

    def draw(self, current_time):
        sw, sh = self.screen.get_size()
        div_x  = int(sw * self._LEFT_FRAC)

        self.back_button.draw(self.screen, current_time)

        # divider
        div_surf = pygame.Surface((2, sh), pygame.SRCALPHA)
        div_surf.fill((255, 255, 255, 18))
        self.screen.blit(div_surf, (div_x, 0))

        # Upload button
        ts = 1.05 if self._upload_hovered else 1.0
        self._upload_scale += (ts - self._upload_scale) * 0.18
        sc = self._upload_scale

        bw    = int(self.upload_rect.w * sc)
        bh    = int(self.upload_rect.h * sc)
        brect = pygame.Rect(self.upload_cx - bw // 2, self.upload_cy - bh // 2, bw, bh)

        if self._upload_hovered:
            pygame.draw.rect(self.screen, (180, 0, 90), brect.inflate(10, 10), 4, border_radius=24)

        pink = (255, 75, 160)
        pygame.draw.rect(self.screen, pink, brect, 3, border_radius=20)

        for font, text, y_off in (
            (self.upload_font1, "Upload",  self._upload_line1_y_off),
            (self.upload_font2, "A File!", self._upload_line2_y_off),
        ):
            s = font.render(text, True, pink)
            if sc != 1.0:
                s = pygame.transform.smoothscale(
                    s, (max(1, int(s.get_width() * sc)), max(1, int(s.get_height() * sc))))
            cy = self.upload_cy + int(y_off * sc)
            self.screen.blit(s, s.get_rect(center=(self.upload_cx, cy)))

        # noki_base_loop body + eyes (drawn over the upload button)
        # Button top rises by (bh - base_h) / 2 when hovered — noki lifts with it
        _btn_lift = (bh - self.upload_rect.h) // 2
        _noki_y   = self._noki_loop_bottom - _btn_lift

        _body = self._noki_loop_seq.current
        if _body is not None:
            self.screen.blit(_body, _body.get_rect(
                midbottom=(self._noki_loop_cx, _noki_y)
            ))

        # Eye PNG overlays — follow the mouse (offset updated at 10 fps)
        for _eye_surf in (self._leye_seq.current, self._reye_seq.current):
            if _eye_surf is not None:
                self.screen.blit(_eye_surf, _eye_surf.get_rect(
                    midbottom=(self._noki_loop_cx + self._eye_ox,
                               _noki_y + self._eye_oy)
                ))

        # Right panel header
        right_cx = div_x + (sw - div_x) // 2
        hdr = self.header_font.render("SONGS", True, (255, 255, 255))
        self.screen.blit(hdr, hdr.get_rect(center=(right_cx, 68)))

        # Scrollable list
        scroll_clip = pygame.Rect(div_x + 1, self.list_top - 10, sw, sh - self.list_top)
        self.screen.set_clip(scroll_clip)

        _SCROLL_SPEED = 48   # px / sec  — how fast the marquee moves
        _PAUSE        = 2.0  # sec pause at left edge before scrolling

        for i, btn in enumerate(self.level_buttons):
            vis_y = btn.rect.y - self.scroll_offset

            # ── hover glow ──────────────────────────────────────────────
            btn._scale += (btn._target_scale - btn._scale) * 0.18
            if btn.is_hovered:
                glow = pygame.Rect(btn.rect.x, vis_y, btn.rect.w, btn.rect.h).inflate(8, 8)
                pygame.draw.rect(self.screen, (80, 80, 100), glow, 2, border_radius=8)

            # ── marquee text ─────────────────────────────────────────────
            color     = btn.hover_color if btn.is_hovered else btn.base_color
            text_surf = btn.font.render(self._full_names[i], True, color)
            tw        = text_surf.get_width()
            pad       = 10
            clip_w    = btn.rect.w - pad        # available width for text
            text_y    = vis_y + (btn.rect.h - text_surf.get_height()) // 2

            if tw > clip_w:
                max_off   = tw - clip_w
                scroll_t  = max_off / _SCROLL_SPEED
                cycle     = _PAUSE + scroll_t + _PAUSE + scroll_t
                t         = (current_time + i * 0.4) % cycle
                if t < _PAUSE:
                    # pause at start
                    x_off = 0
                elif t < _PAUSE + scroll_t:
                    # scroll forward
                    x_off = int((t - _PAUSE) * _SCROLL_SPEED)
                elif t < _PAUSE + scroll_t + _PAUSE:
                    # pause at end
                    x_off = max_off
                else:
                    # scroll back
                    x_off = int(max_off - (t - _PAUSE - scroll_t - _PAUSE) * _SCROLL_SPEED)
                draw_x = btn.rect.x + pad - x_off
            else:
                draw_x = btn.rect.x + (btn.rect.w - tw) // 2

            # clip text to its own column (inside scroll_clip)
            text_clip = pygame.Rect(btn.rect.x + pad, vis_y, clip_w, btn.rect.h)
            old_clip  = self.screen.get_clip()
            self.screen.set_clip(text_clip.clip(old_clip))
            self.screen.blit(text_surf, (draw_x, text_y))
            self.screen.set_clip(old_clip)

            # ── inline rename textbox (replaces text for the renaming slot) ──
            if self._rename_input is not None and self._rename_idx == i:
                inp   = self._rename_input
                cx    = btn.rect.x + btn.rect.w // 2   # horizontal center of slot
                cy    = vis_y + btn.rect.h // 2

                display = inp.text if inp.text else inp.placeholder
                color   = (255, 255, 255) if inp.text else (90, 90, 115)
                tsurf   = self._rename_font.render(display, True, color)
                th      = tsurf.get_height()

                # clip to the slot width so text doesn't overflow into rank column
                old_clip = self.screen.get_clip()
                slot_clip = pygame.Rect(btn.rect.x, vis_y, btn.rect.w, btn.rect.h)
                self.screen.set_clip(slot_clip.clip(old_clip))
                self.screen.blit(tsurf, tsurf.get_rect(center=(cx, cy)))
                self.screen.set_clip(old_clip)

                # blinking cursor at right edge of text, centered vertically
                if int(current_time * 2) % 2 == 0:
                    tw = tsurf.get_width()
                    cur_x = cx + tw // 2 + 3
                    cur_x = min(cur_x, btn.rect.x + btn.rect.w - 4)
                    pygame.draw.line(self.screen, (200, 200, 255),
                                     (cur_x, cy - th // 2 + 2),
                                     (cur_x, cy + th // 2 - 2), 2)
            else:
                rank = self._best_rank(self.song_names[i])
                if rank is not None:
                    r_letter, r_color = rank
                    r_surf = self._rank_font.render(r_letter, True, r_color)
                    self.screen.blit(r_surf, r_surf.get_rect(
                        center=(self._rank_cx, vis_y + self.button_height // 2)
                    ))

        self.screen.set_clip(None)

        # ── Scrollbar ────────────────────────────────────────────────────
        if self.max_scroll > 0:
            # track
            pygame.draw.rect(
                self.screen, (45, 45, 55),
                (self._sb_x, self._sb_y, self._sb_w, self._sb_h),
                border_radius=3,
            )
            # thumb
            thumb = self._sb_thumb_rect()
            if thumb:
                thumb_color = (160, 160, 185) if self._sb_drag else (110, 110, 135)
                pygame.draw.rect(self.screen, thumb_color, thumb, border_radius=3)


# ─── Level detail popup ───────────────────────────────────────────────────────

class LevelMenu:
    """Popup shown when a level row is clicked.
    Left half: huge difficulty label + ◀ ▶ arrows.
    Right half: huge best-score number.
    Black bg, white border.
    Lerps in from the source button rect and back out on close.
    """
    _BORD     = 2
    _ANIM_DUR = 0.13   # seconds for enter / exit

    def __init__(self, screen, song_idx, song_name, initial_diff_idx, scores,
                 origin_rect=None):
        self.screen    = screen
        self.song_idx  = song_idx
        self.song_name = song_name
        self._scores   = scores

        sw, sh = screen.get_size()

        # Popup geometry: 78% wide, 56% tall
        pw = int(sw * 0.78)
        ph = int(sh * 0.56)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        self.rect = pygame.Rect(px, py, pw, ph)

        # Layout constants (relative to final rect)
        self._px, self._py, self._pw, self._ph = px, py, pw, ph
        _pad              = max(24, pw // 30)
        self._pad         = _pad
        self._mid_x       = px + pw // 2
        self._top_h       = int(ph * 0.20)
        self._bot_h       = int(ph * 0.28)
        self._body_top    = py + self._top_h
        self._body_bottom = py + ph - self._bot_h
        self._body_cy     = (self._body_top + self._body_bottom) // 2

        # Fonts
        _title_sz = max(28, ph // 10)
        _big_sz   = max(64, ph // 4)
        _sub_sz   = max(20, ph // 18)
        _btn_sz   = max(30, ph // 8)
        self._title_font = pygame.font.Font(_FONT, _title_sz)
        self._big_font   = pygame.font.Font(_FONT, _big_sz)
        self._sub_font   = pygame.font.Font(_FONT, _sub_sz)
        self._btn_font   = pygame.font.Font(_FONT, _btn_sz)

        _dummy_font = pygame.font.Font(_FONT, _sub_sz)
        self._diff = DifficultySelector(0, 0, _dummy_font)
        self._diff.selected = max(0, min(2, initial_diff_idx))

        self._left_arrow_rect:  pygame.Rect | None = None
        self._right_arrow_rect: pygame.Rect | None = None

        btn_w = int(pw * 0.52)
        btn_h = int(self._bot_h * 0.62)
        self._play_rect = pygame.Rect(
            px + (pw - btn_w) // 2,
            py + ph - self._bot_h + (self._bot_h - btn_h) // 2,
            btn_w, btn_h,
        )
        self._play_hovered = False
        self._play_scale   = 1.0

        close_sz = 30
        self._close_rect = pygame.Rect(
            px + pw - _pad - close_sz,
            py + _pad // 2,
            close_sz, close_sz,
        )
        self._close_hovered = False

        # Dim overlay surface (alpha set dynamically)
        self._overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)

        # ── animation state ──────────────────────────────────────────────────
        # Origin: the button rect on screen the popup expands from/collapses to
        self._origin = origin_rect.copy() if origin_rect else pygame.Rect(
            px + pw // 2, py + ph // 2, 0, 0
        )
        self._anim_start  = time.time()
        self._closing     = False
        self._close_start = 0.0

    # ── helpers ─────────────────────────────────────────────────────────────

    def _top_score(self) -> int | None:
        return self._scores.get(self.song_name, {}).get(self._diff.difficulty)

    @staticmethod
    def _lerp_rect(r1: pygame.Rect, r2: pygame.Rect, t: float) -> pygame.Rect:
        return pygame.Rect(
            int(r1.x + (r2.x - r1.x) * t),
            int(r1.y + (r2.y - r1.y) * t),
            max(1, int(r1.w + (r2.w - r1.w) * t)),
            max(1, int(r1.h + (r2.h - r1.h) * t)),
        )

    def _anim_t(self, current_time: float) -> float:
        """0 → 1 while opening; 1 → 0 while closing. Uses ease-out both ways."""
        if self._closing:
            raw = (current_time - self._close_start) / self._ANIM_DUR
            t   = min(1.0, raw)
            return 1.0 - t * t      # ease-in collapse
        else:
            raw = (current_time - self._anim_start) / self._ANIM_DUR
            t   = min(1.0, raw)
            return 1.0 - (1.0 - t) ** 3   # ease-out expand

    # ── public API ──────────────────────────────────────────────────────────

    def update(self, mouse_pos, mouse_clicked, current_time):
        """Returns 'play', 'close', or None."""
        # Finish close animation then signal done
        if self._closing:
            if (current_time - self._close_start) >= self._ANIM_DUR:
                return "close"
            return None

        self._play_hovered  = self._play_rect.collidepoint(mouse_pos)
        self._close_hovered = self._close_rect.collidepoint(mouse_pos)

        if mouse_clicked:
            if self._play_hovered:
                return "play"
            if self._close_hovered or not self.rect.collidepoint(mouse_pos):
                # Begin close animation
                self._closing     = True
                self._close_start = current_time
                return None
            if self._left_arrow_rect and self._left_arrow_rect.collidepoint(mouse_pos):
                if self._diff.selected > 0:
                    self._diff.selected -= 1
            elif self._right_arrow_rect and self._right_arrow_rect.collidepoint(mouse_pos):
                if self._diff.selected < 2:
                    self._diff.selected += 1

        target = 1.05 if self._play_hovered else 1.0
        self._play_scale += (target - self._play_scale) * 0.18
        return None

    @staticmethod
    def _draw_tri(screen, color, cx, cy, direction, w=14, h=22):
        hw, hh = w // 2, h // 2
        if direction == "left":
            pts = [(cx - hw, cy), (cx + hw, cy - hh), (cx + hw, cy + hh)]
        else:
            pts = [(cx + hw, cy), (cx - hw, cy - hh), (cx - hw, cy + hh)]
        pygame.draw.polygon(screen, color, pts)

    def draw(self, current_time):
        at = self._anim_t(current_time)          # 0 → 1 (open) or 1 → 0 (close)
        cur = self._lerp_rect(self._origin, self.rect, at)
        pad = self._pad

        # overlay fades with animation
        self._overlay.fill((0, 0, 0, int(155 * at)))
        self.screen.blit(self._overlay, (0, 0))

        # panel shell (always drawn, even mid-animation)
        pygame.draw.rect(self.screen, (8, 8, 14),     cur, border_radius=14)
        pygame.draw.rect(self.screen, (255, 255, 255), cur, self._BORD, border_radius=14)

        # content only appears once the box is mostly open
        if at < 0.55:
            return

        content_a = min(255, int(255 * (at - 0.55) / 0.45))

        def _blit_a(surf, rect):
            surf = surf.copy()
            surf.set_alpha(content_a)
            self.screen.blit(surf, rect)

        # fixed geometry drawn relative to the FINAL rect (self._px etc.)
        fpx, fpy, fpw = self._px, self._py, self._pw
        diff_col = DifficultySelector.COLORS[self._diff.selected]

        # ── song title ───────────────────────────────────────────────────────
        display_name = os.path.splitext(self.song_name)[0]
        name_surf = self._title_font.render(display_name, True, (220, 220, 220))
        max_title_w = fpw - pad * 2 - 44
        if name_surf.get_width() > max_title_w:
            clipped = pygame.Surface((max_title_w, name_surf.get_height()), pygame.SRCALPHA)
            clipped.blit(name_surf, (0, 0))
            name_surf = clipped
        _blit_a(name_surf, name_surf.get_rect(center=(fpx + fpw // 2, fpy + self._top_h // 2)))

        rule_y = fpy + self._top_h - 1
        pygame.draw.line(self.screen, (int(50 * at), int(50 * at), int(60 * at)),
                         (fpx + pad, rule_y), (fpx + fpw - pad, rule_y), 1)

        # ── close × ──────────────────────────────────────────────────────────
        xc = (255, 80, 80) if self._close_hovered else (120, 120, 130)
        xc = tuple(int(c * at) for c in xc)
        ccx, ccy = self._close_rect.center
        sz = 10
        pygame.draw.line(self.screen, xc, (ccx - sz, ccy - sz), (ccx + sz, ccy + sz), 2)
        pygame.draw.line(self.screen, xc, (ccx + sz, ccy - sz), (ccx - sz, ccy + sz), 2)

        # ── vertical divider ─────────────────────────────────────────────────
        pygame.draw.line(self.screen, (int(45 * at), int(45 * at), int(55 * at)),
                         (self._mid_x, self._body_top + pad // 2),
                         (self._mid_x, self._body_bottom - pad // 2), 1)

        # ── LEFT HALF: difficulty + arrows ───────────────────────────────────
        left_cx = fpx + fpw // 4
        label     = DifficultySelector.LABELS[self._diff.selected].upper()
        diff_surf = self._big_font.render(label, True, diff_col)
        diff_y    = self._body_cy - int(self._ph * 0.06)
        _blit_a(diff_surf, diff_surf.get_rect(center=(left_cx, diff_y)))

        arrow_y   = diff_y + diff_surf.get_height() // 2 + 28
        arrow_gap = 44
        a_col     = tuple(int(180 * at) for _ in range(3))

        if self._diff.selected > 0:
            self._draw_tri(self.screen, a_col, left_cx - arrow_gap, arrow_y, "left")
            self._left_arrow_rect = pygame.Rect(left_cx - arrow_gap - 22, arrow_y - 18, 44, 36)
        else:
            self._left_arrow_rect = None

        if self._diff.selected < 2:
            self._draw_tri(self.screen, a_col, left_cx + arrow_gap, arrow_y, "right")
            self._right_arrow_rect = pygame.Rect(left_cx + arrow_gap - 22, arrow_y - 18, 44, 36)
        else:
            self._right_arrow_rect = None

        # ── RIGHT HALF: Best + score ──────────────────────────────────────────
        right_cx = fpx + fpw * 3 // 4
        sub_surf = self._sub_font.render("Best", True, (110, 170, 230))
        _blit_a(sub_surf, sub_surf.get_rect(center=(right_cx, self._body_cy - int(self._ph * 0.10))))

        top    = self._top_score()
        s_surf = self._big_font.render(f"{top:,}" if top is not None else "- -", True, (255, 255, 255))
        _blit_a(s_surf, s_surf.get_rect(center=(right_cx, self._body_cy + int(self._ph * 0.06))))

        # ── rule above play button ────────────────────────────────────────────
        pygame.draw.line(self.screen, (int(50 * at), int(50 * at), int(60 * at)),
                         (fpx + pad, self._body_bottom), (fpx + fpw - pad, self._body_bottom), 1)

        # ── PLAY button ───────────────────────────────────────────────────────
        bw = max(1, int(self._play_rect.w * self._play_scale))
        bh = max(1, int(self._play_rect.h * self._play_scale))
        br = pygame.Rect(
            self._play_rect.centerx - bw // 2,
            self._play_rect.centery - bh // 2,
            bw, bh,
        )
        btn_col = (255, 255, 255) if self._play_hovered else (190, 190, 210)
        btn_col_a = tuple(int(c * at) for c in btn_col)
        pygame.draw.rect(self.screen, (0, 0, 0), br, border_radius=8)
        pygame.draw.rect(self.screen, btn_col_a,  br, 2, border_radius=8)
        p_surf = self._btn_font.render("PLAY", True, btn_col)
        _blit_a(p_surf, p_surf.get_rect(center=br.center))


# ─── File upload screen ───────────────────────────────────────────────────────

class FileUploadScreen:
    """
    Upload flow:
      1. Browse for file  (30s minimum guard)
      2. Enter Song Name + Artist  (optional — leave blank for default word bank)
      3. Click "Add to Game!"
      4. Lyrics are fetched in background; spinner shown
      5. Returns ("upload", file_path, word_bank)
    """

    _SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, screen):
        self.screen = screen
        sw, sh = screen.get_size()
        cy = sh // 2

        title_font  = pygame.font.Font(_FONT, 72)
        label_font  = pygame.font.Font(_FONT, 32)
        input_font  = pygame.font.Font(_FONT, 36)
        btn_font    = pygame.font.Font(_FONT, 48)
        status_font = pygame.font.Font(_FONT, 30)

        self.title_font  = title_font
        self.label_font  = label_font
        self.status_font = status_font

        self.selected_path  = None
        self.status_msg     = "Choose a .mp3 or .wav file."
        self.status_color   = (160, 160, 160)

        # buttons
        _btn_sz = 52
        self.back_button = ImageButton(30 + _btn_sz // 2, 30 + _btn_sz // 2, _btn_sz, _EXIT_IMG)
        self.browse_button = Button(
            (sw // 2 - 160, cy - 160, 320, 54), "Browse Files…", btn_font,
            base_color=(140, 180, 255), hover_color=(200, 225, 255),
        )
        self.add_button = Button(
            (sw // 2 - 160, cy + 120, 320, 54), "Add to Game!", btn_font,
            base_color=(80, 200, 120), hover_color=(120, 240, 160),
        )

        # text inputs
        field_w = 360
        self.input_title = TextInput(
            (sw // 2 - field_w // 2, cy - 60, field_w, 44),
            input_font, placeholder="Song Name  (optional)",
        )
        self.input_artist = TextInput(
            (sw // 2 - field_w // 2, cy + 12, field_w, 44),
            input_font, placeholder="Artist  (optional)",
        )

        # lyrics-fetch thread state
        self._fetching    = False
        self._fetch_done  = False
        self._fetch_words: list[str] = []
        self._fetch_thread: threading.Thread | None = None
        self._spinner_idx = 0
        self._spinner_t   = 0.0

    # ── helpers ─────────────────────────────────────────────────────────────

    def show_error(self, message):
        self.status_msg   = message
        self.status_color = (255, 120, 120)

    def _start_fetch(self):
        title  = self.input_title.text.strip()
        artist = self.input_artist.text.strip()
        result_box: list[list[str]] = [[]]  # mutable container

        def worker():
            if title and artist:
                words = _fetch_lyrics_words(artist, title)
                result_box[0] = words if words else DEFAULT_WORD_BANK[:]
            else:
                result_box[0] = DEFAULT_WORD_BANK[:]

        self._result_box   = result_box
        self._fetching     = True
        self._fetch_done   = False
        self._fetch_thread = threading.Thread(target=worker, daemon=True)
        self._fetch_thread.start()

    # ── update / draw ────────────────────────────────────────────────────────

    def update(self, mouse_pos, mouse_clicked, current_time, events):
        # always handle text input events
        self.input_title.handle_events(events)
        self.input_artist.handle_events(events)

        # back
        if self.back_button.update(mouse_pos, mouse_clicked):
            return "back", None, None

        # ── while fetching ───────────────────────────────────────────────
        if self._fetching:
            if self._fetch_thread and not self._fetch_thread.is_alive():
                self._fetching   = False
                self._fetch_done = True
                self._fetch_words = self._result_box[0]
            return None, None, None

        if self._fetch_done:
            self._fetch_done = False
            return "upload", self.selected_path, self._fetch_words

        # ── browse ──────────────────────────────────────────────────────
        self.browse_button.check_hover(mouse_pos)
        if self.browse_button.check_click(mouse_pos, mouse_clicked):
            path = pick_audio_file()
            if path:
                ext = os.path.splitext(path)[1].lower()
                if ext not in ('.mp3', '.wav'):
                    self.show_error("Please select a .mp3 or .wav file.")
                    self.selected_path = None
                else:
                    dur = _audio_duration(path)
                    if dur is not None and dur < 30:
                        self.show_error(f"Too short ({dur:.0f}s). Need at least 30 seconds.")
                        self.selected_path = None
                    else:
                        self.selected_path = path
                        self.status_msg    = f'"{os.path.basename(path)}" selected.'
                        self.status_color  = (120, 220, 140)

        # ── add ─────────────────────────────────────────────────────────
        if self.selected_path:
            self.add_button.check_hover(mouse_pos)
            if self.add_button.check_click(mouse_pos, mouse_clicked):
                self._start_fetch()

        return None, None, None

    def draw(self, current_time):
        sw, sh = self.screen.get_size()
        cy = sh // 2

        title = self.title_font.render("Upload a Song", True, (255, 255, 255))
        self.screen.blit(title, title.get_rect(center=(sw // 2, cy - 230)))

        self.browse_button.draw(self.screen, current_time)

        # status
        status = self.status_font.render(self.status_msg, True, self.status_color)
        self.screen.blit(status, status.get_rect(center=(sw // 2, cy - 96)))

        # fetching spinner
        if self._fetching:
            self._spinner_t += 1 / 60
            if self._spinner_t >= 0.08:
                self._spinner_t = 0
                self._spinner_idx = (self._spinner_idx + 1) % len(self._SPINNER)
            spin_font = pygame.font.Font(_FONT, 52)
            spin_surf = spin_font.render(
                f"Fetching lyrics…  {self._SPINNER[self._spinner_idx]}", True, (180, 180, 220)
            )
            self.screen.blit(spin_surf, spin_surf.get_rect(center=(sw // 2, cy + 60)))
            self.back_button.draw(self.screen, current_time)
            return

        # labels and inputs
        lbl_color = (130, 130, 160)
        lbl1 = self.label_font.render("Song Name", True, lbl_color)
        lbl2 = self.label_font.render("Artist", True, lbl_color)
        self.screen.blit(lbl1, lbl1.get_rect(bottomleft=(self.input_title.rect.x,
                                                          self.input_title.rect.y - 4)))
        self.screen.blit(lbl2, lbl2.get_rect(bottomleft=(self.input_artist.rect.x,
                                                          self.input_artist.rect.y - 4)))
        self.input_title.draw(self.screen, current_time)
        self.input_artist.draw(self.screen, current_time)

        # hint
        if not (self.input_title.text or self.input_artist.text):
            hint_font = pygame.font.Font(_FONT, 26)
            hint = hint_font.render(
                "Leave blank to use a built-in word set.", True, (70, 70, 90)
            )
            self.screen.blit(hint, hint.get_rect(center=(sw // 2, cy + 68)))

        if self.selected_path:
            self.add_button.draw(self.screen, current_time)

        self.back_button.draw(self.screen, current_time)


# ─── Menu manager ─────────────────────────────────────────────────────────────

class MenuManager:
    _PETAL_COUNT = 55

    def __init__(self, screen, clock, song_names, start_state="title", music=None):
        self.screen     = screen
        self.clock      = clock
        self.song_names = song_names
        self.state      = start_state
        self._music     = music   # MusicManager | None

        # load scores first — needed by LevelSelect
        self._scores              = _load_scores()
        self._level_menu: LevelMenu | None = None
        self._pending_difficulty: str | None = None

        self.title_screen       = TitleScreen(screen)
        self.level_select       = LevelSelect(screen, song_names, self._scores)
        self.file_upload_screen = FileUploadScreen(screen)
        if start_state != "title":
            self.title_screen.reset()

        self.transition_start        = 0.0
        self.transition_duration     = 0.5
        self.transition_origin       = (screen.get_width() // 2, screen.get_height() // 2)
        self.transition_target_state = ""
        self.transition_selected     = -1
        self._pre_transition_state   = ""

        sw, sh = screen.get_size()
        self._petals = [Petal(sw, sh, randomize_y=True) for _ in range(self._PETAL_COUNT)]

        # ── Intro video ──────────────────────────────────────────────────────
        _VIDEO_PATH = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets", "images", "noki_intro.mov",
        )
        self._video_cap       = None
        self._video_done      = (music is not None and music.title_ready)
        self._video_last_surf = None
        self._video_acc       = 0.0
        self._video_frame_dur = 1.0 / 30.0

        # ── Waiting ("...") screen ────────────────────────────────────────────
        # Auto-advances after 2 seconds.
        self._show_waiting  = (music is not None and music.needs_start)
        self._dots_timer    = 0.0
        self._dots_count    = 1        # start with one dot visible
        self._waiting_elapsed = 0.0    # total time on waiting screen
        _dots_font_size     = max(48, screen.get_height() // 12)
        self._dots_font     = pygame.font.Font(_FONT, _dots_font_size)

        if not self._video_done:
            try:
                import cv2  # type: ignore
                if os.path.exists(_VIDEO_PATH):
                    cap = cv2.VideoCapture(_VIDEO_PATH)
                    if cap.isOpened():
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        if fps > 0:
                            self._video_frame_dur = 1.0 / fps
                        self._video_cap = cap
                    else:
                        self._video_done = True
                else:
                    self._video_done = True
            except ImportError:
                self._video_done = True

        # per-song word banks (filename → word list)
        self.song_word_banks: dict[str, list[str]] = _load_word_banks()

        self._pending_difficulty: str | None = None

    def _word_bank_for(self, idx: int) -> list[str]:
        name = self.song_names[idx]
        return self.song_word_banks.get(name, DEFAULT_WORD_BANK[:])

    def run(self):
        """Returns (song_index, difficulty_str, word_bank) or None if quit."""
        while True:
            current_time  = time.time()
            mouse_pos     = pygame.mouse.get_pos()
            mouse_clicked = False
            events        = []

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_clicked = True
                if self.state == "level_select":
                    self.level_select.handle_scroll(event)
                events.append(event)

            dt = self.clock.tick(60) / 1000.0

            # ── Waiting ("...") screen — auto-dismisses after 2 seconds ─────
            if self._show_waiting:
                self._waiting_elapsed += dt
                if self._waiting_elapsed >= 2.0:
                    self._show_waiting = False
                    if self._music:
                        self._music.start_intro()
                else:
                    self.screen.fill((0, 0, 0))
                    self._dots_timer += dt
                    if self._dots_timer >= 0.22:
                        self._dots_timer = 0.0
                        self._dots_count = (self._dots_count % 3) + 1
                    dots_str = "." * self._dots_count
                    sw2, sh2 = self.screen.get_size()
                    dot_surf = self._dots_font.render(dots_str, True, (220, 220, 220))
                    self.screen.blit(dot_surf, dot_surf.get_rect(center=(sw2 // 2, sh2 // 2)))
                    pygame.display.flip()
                    continue

            if self._music:
                self._music.update(dt)

            self.screen.fill((0, 0, 0))

            _title_ready = (self._music is None) or self._music.title_ready

            if _title_ready:
                for petal in self._petals:
                    petal.update()
                    petal.draw(self.screen)
            else:
                # ── Intro video on black background ──────────────────────────
                if not self._video_done and self._video_cap is not None:
                    import cv2  # type: ignore
                    self._video_acc += dt
                    # advance frames to stay in sync with elapsed time
                    while self._video_acc >= self._video_frame_dur:
                        self._video_acc -= self._video_frame_dur
                        ret, frame = self._video_cap.read()
                        if not ret:
                            # video finished
                            self._video_cap.release()
                            self._video_cap   = None
                            self._video_done  = True
                            if self._music:
                                self._music.on_intro_video_done()
                            break
                        # convert BGR→RGB and blit
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        fh, fw = frame_rgb.shape[:2]
                        surf = pygame.surfarray.make_surface(
                            frame_rgb.transpose(1, 0, 2)
                        )
                        sw2, sh2 = self.screen.get_size()
                        # scale to screen height, maintain aspect ratio
                        scaled_w = int(fw * sh2 / fh)
                        surf = pygame.transform.smoothscale(surf, (scaled_w, sh2))
                        self._video_last_surf = surf

                    if self._video_last_surf is not None and not self._video_done:
                        sw2, sh2 = self.screen.get_size()
                        x = (sw2 - self._video_last_surf.get_width()) // 2
                        self.screen.blit(self._video_last_surf, (x, 0))

            if self.state == "title":
                if _title_ready:
                    action = self.title_screen.update(mouse_pos, mouse_clicked, current_time)
                    self.title_screen.draw(current_time)
                    if action == "play":
                        if self._music:
                            self._music.on_play_pressed()
                        self._start_transition("level_select",
                                               self.title_screen.play_button_rect.center)
                # else: black screen already filled above — do nothing

            elif self.state == "level_select":
                # while popup is open: suppress clicks AND hover in the background
                ls_click  = mouse_clicked and self._level_menu is None
                ls_mouse  = mouse_pos if self._level_menu is None else (-9999, -9999)
                ls_events = events if self._level_menu is None else []
                action, idx = self.level_select.update(ls_mouse, ls_click, current_time, ls_events)
                self.level_select.draw(current_time)

                # ── level detail popup ────────────────────────────────────────
                if self._level_menu is not None:
                    lm_action = self._level_menu.update(mouse_pos, mouse_clicked, current_time)
                    self._level_menu.draw(current_time)
                    if lm_action == "play":
                        self._pending_difficulty = self._level_menu._diff.difficulty
                        li = self._level_menu.song_idx
                        btn = self.level_select.level_buttons[li]
                        origin = (btn.rect.centerx,
                                  btn.rect.centery - self.level_select.scroll_offset)
                        self._level_menu = None
                        self._start_transition("launch", origin, li)
                    elif lm_action == "close":
                        self._level_menu = None

                if action == "back":
                    self._start_transition("title", self.level_select.back_button.rect.center)
                elif action == "upload":
                    # Pick file immediately — no separate upload screen
                    fpath = pick_audio_file()
                    if fpath:
                        ok, msg = self._handle_upload(fpath, None)
                        if ok:
                            self.level_select = LevelSelect(self.screen, self.song_names, self._scores)
                            self.level_select.begin_rename(0)  # index 0 = newly inserted slot
                elif action == "cancel_upload":
                    # Escape during rename — remove the just-added song slot
                    cancel_idx = idx  # idx holds the rename slot index
                    if 0 <= cancel_idx < len(self.song_names):
                        removed = self.song_names.pop(cancel_idx)
                        self.song_word_banks.pop(removed, None)
                    self.level_select = LevelSelect(self.screen, self.song_names, self._scores)
                elif action == "rename":
                    rename_idx, new_name = self.level_select._rename_result
                    # Update display name in level_select lists
                    self.level_select._full_names[rename_idx] = new_name
                    self.level_select.level_buttons[rename_idx].text = new_name
                elif action == "select":
                    diff_idx = self.level_select.difficulty_selectors[idx].selected
                    _btn     = self.level_select.level_buttons[idx]
                    _vis_y   = _btn.rect.y - self.level_select.scroll_offset
                    _origin  = pygame.Rect(_btn.rect.x, _vis_y, _btn.rect.w, _btn.rect.h)
                    self._level_menu = LevelMenu(
                        self.screen, idx, self.song_names[idx],
                        diff_idx, self._scores, _origin,
                    )

            elif self.state == "upload":
                action, fpath, words = self.file_upload_screen.update(
                    mouse_pos, mouse_clicked, current_time, events
                )
                self.file_upload_screen.draw(current_time)
                if action == "back":
                    self.state = "level_select"
                elif action == "upload":
                    ok, msg = self._handle_upload(fpath, words)
                    if ok:
                        self.level_select = LevelSelect(self.screen, self.song_names, self._scores)
                        self.state = "level_select"
                    else:
                        self.file_upload_screen.show_error(msg)

            elif self.state == "transition":
                self._draw_transition(current_time)
                progress = (current_time - self.transition_start) / self.transition_duration
                if progress >= 1.0:
                    if self.transition_target_state == "launch":
                        idx        = self.transition_selected
                        difficulty = (self._pending_difficulty
                                      or self.level_select.difficulty_selectors[idx].difficulty)
                        self._pending_difficulty = None
                        word_bank  = self._word_bank_for(idx)
                        return (idx, difficulty, word_bank)
                    self.state = self.transition_target_state
                    if self.state == "title":
                        self.title_screen.reset()

            pygame.display.flip()

    def _handle_upload(self, file_path, word_bank: list[str] | None):
        try:
            dest_dir  = os.path.join("assets", "audios")
            filename  = os.path.basename(file_path)
            dest_path = os.path.join(dest_dir, filename)
            if not os.path.exists(dest_path):
                shutil.copy2(file_path, dest_path)
            if filename not in self.song_names:
                self.song_names.insert(0, filename)
            # persist word bank
            self.song_word_banks[filename] = word_bank if word_bank is not None else DEFAULT_WORD_BANK[:]
            _save_word_banks(self.song_word_banks)
            return True, filename
        except Exception as e:
            return False, f"Upload failed: {e}"

    def _draw_transition(self, current_time):
        progress = min(1.0, (current_time - self.transition_start) / self.transition_duration)
        ease     = 1 - (1 - progress) ** 3
        sw, sh   = self.screen.get_size()

        if self._pre_transition_state == "title":
            self.title_screen.draw(current_time)
        else:
            self.level_select.draw(current_time)

        scale = 1.0 + ease * 0.5
        if scale != 1.0:
            copy   = self.screen.copy()
            scaled = pygame.transform.smoothscale(copy, (int(sw * scale), int(sh * scale)))
            ox, oy = self.transition_origin
            self.screen.fill((0, 0, 0))
            self.screen.blit(scaled, (int(ox - ox * scale), int(oy - oy * scale)))

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(255 * ease)))
        self.screen.blit(overlay, (0, 0))

    def _start_transition(self, target_state, origin, selected=-1):
        self._pre_transition_state   = self.state
        self.state                   = "transition"
        self.transition_start        = time.time()
        self.transition_origin       = origin
        self.transition_target_state = target_state
        self.transition_selected     = selected


# ─── Pause overlay ────────────────────────────────────────────────────────────

class PauseScreen:
    BORDER_THICKNESS = 6
    FADE_DURATION    = 0.25

    def __init__(self, screen):
        self.screen = screen
        sw, sh = screen.get_size()
        btn_font = pygame.font.Font(_FONT, 56)
        self.resume_button = Button(
            (sw // 2 - 120, sh // 2 - 70, 240, 60), "RESUME", btn_font,
        )
        self.menu_button = Button(
            (sw // 2 - 120, sh // 2 + 50, 240, 60), "MAIN MENU", btn_font,
        )
        self.open_time = time.time()

    def update(self, mouse_pos, mouse_clicked):
        self.resume_button.check_hover(mouse_pos)
        self.menu_button.check_hover(mouse_pos)
        if self.resume_button.check_click(mouse_pos, mouse_clicked):
            return "resume"
        if self.menu_button.check_click(mouse_pos, mouse_clicked):
            return "menu"
        return None

    def draw(self, current_time):
        sw, sh = self.screen.get_size()
        t    = min(1.0, (current_time - self.open_time) / self.FADE_DURATION)
        ease = 1 - (1 - t) ** 3

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(80 * ease)))
        self.screen.blit(overlay, (0, 0))

        thickness = int(self.BORDER_THICKNESS * ease)
        if thickness > 0:
            bright = int(255 * ease)
            c = (bright, bright, bright)
            pygame.draw.rect(self.screen, c, (0, 0, sw, thickness))
            pygame.draw.rect(self.screen, c, (0, sh - thickness, sw, thickness))
            pygame.draw.rect(self.screen, c, (0, 0, thickness, sh))
            pygame.draw.rect(self.screen, c, (sw - thickness, 0, thickness, sh))

        self.resume_button.draw(self.screen, current_time)
        self.menu_button.draw(self.screen, current_time)
