"""
Reusable UI widgets for the menu system.
Petal, Button, TextInput, DifficultySelector, ImageButton, PNGSequenceSprite.
"""
import pygame
import math
import os
import random

from .menu_utils import _FONT

_EXIT_IMG = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets", "images", "exitbutton.png",
)


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
    _LERP_SPD = 0.22   # per-frame lerp toward target (0 = instant, 1 = never)

    def __init__(self, center_x, center_y, font):
        self.cx, self.cy = center_x, center_y
        self.font        = font
        self.selected    = 1

        # slide_offset: pixels the current label is displaced from center.
        # Positive = incoming from right, negative = incoming from left.
        self._slide_offset  = 0.0
        self._prev_label: str | None  = None  # label sliding out
        self._prev_color: tuple | None = None
        self._prev_offset   = 0.0            # where the outgoing label is sliding to
        self._left_rect:  pygame.Rect | None = None
        self._right_rect: pygame.Rect | None = None

        self._max_label_w = max(font.size(l)[0] for l in self.LABELS)

    @property
    def difficulty(self) -> str:
        return self.KEYS[self.selected]

    def check_hover(self, _pos):
        pass

    def _go(self, direction: int):
        """Advance selection by +1 (right) or -1 (left), wrapping at ends."""
        n = len(self.LABELS)
        self._prev_label  = self.LABELS[self.selected]
        self._prev_color  = self.COLORS[self.selected]
        self._prev_offset = 0.0
        self.selected = (self.selected + direction) % n
        # incoming label starts off-screen in the opposite direction
        self._slide_offset = -direction * self._max_label_w * 1.1

    def check_click(self, mouse_pos, mouse_clicked) -> bool:
        if not mouse_clicked:
            return False
        if self._left_rect and self._left_rect.collidepoint(mouse_pos):
            self._go(-1)
            return True
        if self._right_rect and self._right_rect.collidepoint(mouse_pos):
            self._go(1)
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
        spd = self._LERP_SPD
        self._slide_offset += (0.0 - self._slide_offset) * spd
        if abs(self._slide_offset) < 0.5:
            self._slide_offset = 0.0

        # Outgoing label slides further away
        if self._prev_label is not None:
            # direction it's moving: opposite of incoming
            sign = 1 if self._prev_offset <= 0 else -1
            target_prev = sign * self._max_label_w * 1.1
            self._prev_offset += (target_prev - self._prev_offset) * spd
            if abs(self._prev_offset - target_prev) < 1.0:
                self._prev_label = None  # done sliding out

        eff_cy = self.cy - y_offset
        th = self.font.get_height()

        clip_rect = pygame.Rect(
            int(self.cx - self._max_label_w // 2), int(eff_cy - th // 2 - 2),
            self._max_label_w, th + 4,
        )
        old_clip = screen.get_clip()
        screen.set_clip(clip_rect)

        # Draw outgoing label
        if self._prev_label is not None:
            prev_surf = self.font.render(self._prev_label, True, self._prev_color)
            ptw = prev_surf.get_width()
            screen.blit(prev_surf, (int(self.cx + self._prev_offset - ptw // 2), int(eff_cy - th // 2)))

        # Draw incoming (current) label
        label = self.LABELS[self.selected]
        color = self.COLORS[self.selected]
        text_surf = self.font.render(label, True, color)
        tw = text_surf.get_width()
        screen.blit(text_surf, (int(self.cx + self._slide_offset - tw // 2), int(eff_cy - th // 2)))

        screen.set_clip(old_clip)

        arrow_color = (160, 160, 160)
        arrow_gap   = 12
        aw, ah      = 11, 16
        label_left  = self.cx - self._max_label_w // 2
        label_right = self.cx + self._max_label_w // 2

        # Always show both arrows (wrap)
        tip_cx = label_left - arrow_gap - aw // 2
        self._draw_arrow(screen, arrow_color, tip_cx, eff_cy, 'left', aw, ah)
        self._left_rect = pygame.Rect(tip_cx - aw - 4, eff_cy - ah // 2 - 4, aw * 2 + 8, ah + 8)

        tip_cx = label_right + arrow_gap + aw // 2
        self._draw_arrow(screen, arrow_color, tip_cx, eff_cy, 'right', aw, ah)
        self._right_rect = pygame.Rect(tip_cx - aw - 4, eff_cy - ah // 2 - 4, aw * 2 + 8, ah + 8)


# ─── Image button (hover scale + click shrink→bounce) ────────────────────────

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
