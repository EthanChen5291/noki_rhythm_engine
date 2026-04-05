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
    "dream","shadow","echo","spark","surge","drift","pulse","blaze","veil",
    "flame","tide","glow","flare","dusk","dawn","haze","mist","void","flux",
    "soar","hush","fierce","bold","wild","still","bright","deep","vast",
    "pure","clear","gold","silver","crystal","prism","spiral","phantom",
    "rhythm","melody","tempo","chord","verse","motion","balance","grace",
    "valor","quest","mirage","cipher","zenith","solace","reverie","luster",
    "cascade","emblem","fractal","haven","mystic","nimble","oracle","radiant",
    "serene","tranquil","umbra","vivid","wander","marvel","fortune","legend",
    "glory","infinite",
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
    LABELS = ["Easy",    "Medium",  "Hard"  ]
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


# ─── Title screen ────────────────────────────────────────────────────────────

class TitleScreen:
    _ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "images")

    # play-button animation constants
    _HOVER_SCALE   = 1.18
    _CLICK_SHRINK  = 0.72
    _CLICK_BOUNCE  = 1.22
    _LERP_NORMAL   = 0.10
    _LERP_FAST     = 0.22

    def __init__(self, screen):
        self.screen = screen
        sw, sh = screen.get_size()

        # ── Title image (35 % smaller than the 50 % version → 32.5 % of sw) ──
        raw_title = pygame.image.load(
            os.path.join(self._ASSETS, "noki_maintitle.png")
        ).convert_alpha()
        target_w      = int(sw * 0.325)
        target_h      = int(raw_title.get_height() * target_w / raw_title.get_width())
        self.title_img = pygame.transform.smoothscale(raw_title, (target_w, target_h))
        # moved down: centre title slightly below the screen midpoint
        self.title_cx  = sw // 2
        self.title_cy_base = sh // 2 - target_h // 2 + 20

        # ── Play button image ─────────────────────────────────────────────────
        raw_btn = pygame.image.load(
            os.path.join(self._ASSETS, "playbutton.png")
        ).convert_alpha()
        btn_size = int(sh * 0.10)          # base display size
        self._btn_base = pygame.transform.smoothscale(raw_btn, (btn_size, btn_size))
        self._btn_size = btn_size
        # position: below the title, shifted down a bit further
        self.btn_cx = sw // 2
        self.btn_cy = sh // 2 + target_h // 2 + 60

        # animation state
        self._scale        = 1.0
        self._click_phase  = None   # None | "shrink" | "bounce"

        # rect used by MenuManager as the transition origin
        self.play_button_rect = pygame.Rect(
            self.btn_cx - btn_size // 2,
            self.btn_cy - btn_size // 2,
            btn_size, btn_size,
        )

    def _btn_hovered(self, mouse_pos) -> bool:
        half = int(self._btn_size * self._scale) // 2
        r = pygame.Rect(self.btn_cx - half, self.btn_cy - half, half * 2, half * 2)
        return r.collidepoint(mouse_pos)

    def update(self, mouse_pos, mouse_clicked, _current_time):
        hovered = self._btn_hovered(mouse_pos)

        if mouse_clicked and hovered and self._click_phase is None:
            self._click_phase = "shrink"

        # drive scale state machine
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
            target = self._HOVER_SCALE if hovered else 1.0
            self._scale += (target - self._scale) * self._LERP_NORMAL

        return None

    def draw(self, current_time):
        sw = self.screen.get_width()

        # floating title
        y_offset = 8 * math.sin(current_time * 2)
        self.screen.blit(
            self.title_img,
            self.title_img.get_rect(center=(self.title_cx, self.title_cy_base + y_offset)),
        )

        # scaled play button
        disp_size = max(1, int(self._btn_size * self._scale))
        btn_surf  = pygame.transform.smoothscale(self._btn_base, (disp_size, disp_size))
        self.screen.blit(btn_surf, btn_surf.get_rect(center=(self.btn_cx, self.btn_cy)))


# ─── Level select screen ─────────────────────────────────────────────────────

class LevelSelect:
    _LEFT_FRAC  = 0.35
    _RIGHT_FRAC = 0.65

    def __init__(self, screen, song_names):
        self.screen     = screen
        self.song_names = song_names
        sw, sh = screen.get_size()

        self.header_font  = pygame.font.Font(None, 60)
        self.button_font  = pygame.font.Font(None, 42)
        self.back_font    = pygame.font.Font(None, 52)
        self.diff_font    = pygame.font.Font(None, 36)
        self.upload_font1 = pygame.font.Font(None, 96)
        self.upload_font2 = pygame.font.Font(None, 78)

        self.scroll_offset  = 0
        self.button_height  = 56
        self.button_spacing = 14
        self.list_top       = 120

        # ── Upload zone (left 35%) ───────────────────────────────────────
        div_x = int(sw * self._LEFT_FRAC)
        self.upload_cx = div_x // 2
        self.upload_cy = sh // 2

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

        # ── Song list (right 65%) ────────────────────────────────────────
        right_start = div_x
        right_cx    = right_start + (sw - right_start) // 2

        diff_max_lw = max(self.diff_font.size(l)[0] for l in DifficultySelector.LABELS)
        diff_half_w = diff_max_lw // 2 + 30

        self.btn_w = min(300, (sw - right_start) // 2 - diff_half_w - 60)
        self.btn_x = right_cx - self.btn_w // 2 - diff_half_w - 30
        self.diff_cx = self.btn_x + self.btn_w + 60 + diff_half_w

        self.level_buttons:        list[Button]             = []
        self.difficulty_selectors: list[DifficultySelector] = []

        for i, name in enumerate(song_names):
            raw = os.path.splitext(name)[0]
            display = raw
            while self.button_font.size(display)[0] > self.btn_w - 16 and len(display) > 4:
                display = display[:-1]
            if display != raw:
                display = display[:-2] + "…"
            btn_y = self.list_top + i * (self.button_height + self.button_spacing)
            self.level_buttons.append(Button(
                (self.btn_x, btn_y, self.btn_w, self.button_height), display, self.button_font
            ))
            self.difficulty_selectors.append(
                DifficultySelector(self.diff_cx, btn_y + self.button_height // 2, self.diff_font)
            )

        self.back_button = Button(
            (30, 30, 120, 50), "BACK", self.back_font,
            base_color=(180, 180, 180), hover_color=(255, 255, 255),
        )
        total = len(song_names) * (self.button_height + self.button_spacing)
        self.max_scroll = max(0, total - (sh - self.list_top - 40))

    def handle_scroll(self, event):
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_offset -= event.y * 30
            self.scroll_offset  = max(0, min(self.scroll_offset, self.max_scroll))

    def update(self, mouse_pos, mouse_clicked, _current_time):
        self.back_button.check_hover(mouse_pos)
        if self.back_button.check_click(mouse_pos, mouse_clicked):
            return "back", -1

        self._upload_hovered = self.upload_rect.collidepoint(mouse_pos)
        if mouse_clicked and self._upload_hovered:
            return "upload", -1

        adj = (mouse_pos[0], mouse_pos[1] + self.scroll_offset)
        for i, btn in enumerate(self.level_buttons):
            btn.check_hover(adj)
            self.difficulty_selectors[i].check_click(adj, mouse_clicked)
            if btn.check_click(adj, mouse_clicked):
                return "select", i

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

        # Right panel header
        right_cx = div_x + (sw - div_x) // 2
        hdr = self.header_font.render("SONGS", True, (255, 255, 255))
        self.screen.blit(hdr, hdr.get_rect(center=(right_cx, 68)))

        # Scrollable list
        clip_rect = pygame.Rect(div_x + 1, self.list_top - 10, sw, sh - self.list_top)
        self.screen.set_clip(clip_rect)

        for i, btn in enumerate(self.level_buttons):
            vis_y   = btn.rect.y - self.scroll_offset
            shifted = Button(
                (btn.rect.x, vis_y, btn.rect.w, btn.rect.h),
                btn.text, btn.font, btn.base_color, btn.hover_color,
            )
            shifted.is_hovered = btn.is_hovered
            shifted._scale     = btn._scale
            shifted.draw(self.screen, current_time)
            self.difficulty_selectors[i].draw(self.screen, current_time,
                                               y_offset=self.scroll_offset)

        self.screen.set_clip(None)


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

        title_font  = pygame.font.Font(None, 72)
        label_font  = pygame.font.Font(None, 32)
        input_font  = pygame.font.Font(None, 36)
        btn_font    = pygame.font.Font(None, 48)
        back_font   = pygame.font.Font(None, 52)
        status_font = pygame.font.Font(None, 30)

        self.title_font  = title_font
        self.label_font  = label_font
        self.status_font = status_font

        self.selected_path  = None
        self.status_msg     = "Choose a .mp3 or .wav file."
        self.status_color   = (160, 160, 160)

        # buttons
        self.back_button = Button(
            (30, 30, 120, 50), "BACK", back_font,
            base_color=(180, 180, 180), hover_color=(255, 255, 255),
        )
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
        self.back_button.check_hover(mouse_pos)
        if self.back_button.check_click(mouse_pos, mouse_clicked):
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
            spin_font = pygame.font.Font(None, 52)
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
            hint_font = pygame.font.Font(None, 26)
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

    def __init__(self, screen, clock, song_names, start_state="title"):
        self.screen     = screen
        self.clock      = clock
        self.song_names = song_names
        self.state      = start_state

        self.title_screen       = TitleScreen(screen)
        self.level_select       = LevelSelect(screen, song_names)
        self.file_upload_screen = FileUploadScreen(screen)

        self.transition_start        = 0.0
        self.transition_duration     = 0.5
        self.transition_origin       = (screen.get_width() // 2, screen.get_height() // 2)
        self.transition_target_state = ""
        self.transition_selected     = -1
        self._pre_transition_state   = ""

        sw, sh = screen.get_size()
        self._petals = [Petal(sw, sh, randomize_y=True) for _ in range(self._PETAL_COUNT)]

        # per-song word banks (filename → word list)
        self.song_word_banks: dict[str, list[str]] = _load_word_banks()

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

            self.screen.fill((0, 0, 0))
            for petal in self._petals:
                petal.update()
                petal.draw(self.screen)

            if self.state == "title":
                action = self.title_screen.update(mouse_pos, mouse_clicked, current_time)
                self.title_screen.draw(current_time)
                if action == "play":
                    self._start_transition("level_select",
                                           self.title_screen.play_button_rect.center)

            elif self.state == "level_select":
                action, idx = self.level_select.update(mouse_pos, mouse_clicked, current_time)
                self.level_select.draw(current_time)
                if action == "back":
                    self._start_transition("title", self.level_select.back_button.rect.center)
                elif action == "upload":
                    self.file_upload_screen = FileUploadScreen(self.screen)
                    origin = self.level_select.upload_rect.center
                    self._start_transition("upload", origin)
                elif action == "select":
                    btn    = self.level_select.level_buttons[idx]
                    origin = (btn.rect.centerx,
                              btn.rect.centery - self.level_select.scroll_offset)
                    self._start_transition("launch", origin, idx)

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
                        self.level_select = LevelSelect(self.screen, self.song_names)
                        self.state = "level_select"
                    else:
                        self.file_upload_screen.show_error(msg)

            elif self.state == "transition":
                self._draw_transition(current_time)
                progress = (current_time - self.transition_start) / self.transition_duration
                if progress >= 1.0:
                    if self.transition_target_state == "launch":
                        idx        = self.transition_selected
                        difficulty = self.level_select.difficulty_selectors[idx].difficulty
                        word_bank  = self._word_bank_for(idx)
                        return (idx, difficulty, word_bank)
                    self.state = self.transition_target_state

            pygame.display.flip()
            self.clock.tick(60)

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
        btn_font = pygame.font.Font(None, 56)
        self.resume_button = Button(
            (sw // 2 - 120, sh // 2 - 50, 240, 60), "RESUME", btn_font,
        )
        self.menu_button = Button(
            (sw // 2 - 120, sh // 2 + 30, 240, 60), "MAIN MENU", btn_font,
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
        overlay.fill((0, 0, 0, int(120 * ease)))
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
