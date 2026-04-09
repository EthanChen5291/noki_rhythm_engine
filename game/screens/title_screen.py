"""
Title screen: noki_bop looping video, beat-synced title image, play button.

Responsibilities:
  - Render the noki_bop video and spotlight overlay (left side)
  - Beat-pulse the title image in sync with the music BPM
  - Animate the play button (hover scale, click shrink → bounce)
  - Return "play" when the click animation completes
"""
from __future__ import annotations
import os
import pygame

from ..menu_utils import _FONT          # noqa: F401 – imported for side-effects in sibling modules
from ._constants import (
    BTN_HOVER_SCALE, BTN_CLICK_SHRINK, BTN_CLICK_BOUNCE,
    BTN_LERP_NORMAL, BTN_LERP_FAST, CLICK_THRESHOLD,
    BEAT_BPM_INTRO, BEAT_BPM_RETURN,
    BEAT_TITLE_PEAK, BEAT_BTN_PEAK, BEAT_LERP_SPEED,
    BOP_PLAYBACK_SPEED,
)
from ._video import VideoPlayer

_ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "assets", "images",
)


class TitleScreen:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        sw, sh = screen.get_size()

        # ── Title image ───────────────────────────────────────────────────────
        raw_title  = pygame.image.load(
            os.path.join(_ASSETS, "noki_maintitle.png")
        ).convert_alpha()
        target_w   = int(sw * 0.325)
        target_h   = int(raw_title.get_height() * target_w / raw_title.get_width())
        self.title_img     = raw_title       # full-res copy kept for smooth scaling
        self._title_base_w = target_w
        self._title_base_h = target_h
        self.title_cx      = sw // 2 + int(sw * 0.15)
        self.title_cy      = sh // 2 - target_h // 2 + 20

        # Beat-pulse scale state
        self._title_scale        = 1.0
        self._title_scale_target = 1.0

        # ── Play button ───────────────────────────────────────────────────────
        raw_btn  = pygame.image.load(
            os.path.join(_ASSETS, "playbutton.png")
        ).convert_alpha()
        btn_size = int(sh * 0.10 * 1.20)   # 20 % larger than legacy size
        self._btn_base = raw_btn
        self._btn_size = btn_size
        self.btn_cx = sw // 2 + int(sw * 0.15)
        self.btn_cy = sh // 2 + target_h // 2 + 60

        self._scale       = 1.0
        self._click_phase: str | None = None  # None | "shrink" | "bounce"

        # Exposed so MenuManager can use it as the transition origin
        self.play_button_rect = pygame.Rect(
            self.btn_cx - btn_size // 2,
            self.btn_cy - btn_size // 2,
            btn_size, btn_size,
        )

        # ── Beat tracking ─────────────────────────────────────────────────────
        self._beat_period = 60.0 / BEAT_BPM_INTRO
        self._last_beat   = -1

        # ── Noki bop video (left side) ────────────────────────────────────────
        bop_h      = int(sh * 0.40)
        btn_bottom = self.btn_cy + btn_size // 2
        self._bop_cx = sw // 4 + int(sw * 0.06)
        self._bop_cy = btn_bottom - bop_h // 2

        self._video = VideoPlayer(os.path.join(_ASSETS, "noki_bop.mov"), bop_h)

        # Spotlight overlay (drawn on top of the video at low opacity)
        self._spotlight_surf: pygame.Surface | None = None
        if self._video.is_available:
            spot_w = int(self._video.display_width * 0.78)
            spot_h = int((btn_bottom + int(sh * 0.10)) * 1.15)
            raw_spot = pygame.image.load(
                os.path.join(_ASSETS, "spotlight.png")
            ).convert_alpha()
            spot = pygame.transform.smoothscale(raw_spot, (spot_w, spot_h))
            spot.set_alpha(int(255 * 0.19))
            self._spotlight_surf = spot

    # ── Public API ────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Switch to return-visit BPM and clear all animation state."""
        self._beat_period        = 60.0 / BEAT_BPM_RETURN
        self._last_beat          = -1
        self._title_scale        = 1.0
        self._title_scale_target = 1.0
        self._scale              = 1.0
        self._click_phase        = None
        self._video.reset()

    def update(self, dt: float, mouse_pos: tuple, mouse_clicked: bool,
               current_time: float) -> str | None:
        """
        Advance all animation state.
        Returns "play" when the click animation finishes; None otherwise.
        """
        hovered = self._btn_hovered(mouse_pos)

        if mouse_clicked and hovered and self._click_phase is None:
            self._click_phase = "shrink"

        result = self._update_click_animation(dt, hovered)
        if result is not None:
            return result

        # Idle path only — skip while a click animation is running so the
        # beat-pulse scale lerp doesn't fight the shrink/bounce lerp.
        if self._click_phase is None:
            self._video.update(dt * BOP_PLAYBACK_SPEED)
            self._update_beat(dt, hovered, current_time)
        return None

    def draw(self, _current_time: float) -> None:
        # Noki bop video
        bop_surf = self._video.get_surface()
        if bop_surf is not None:
            self.screen.blit(
                bop_surf,
                bop_surf.get_rect(center=(self._bop_cx, self._bop_cy)),
            )

        # Spotlight on top of video
        if self._spotlight_surf is not None:
            sh    = self.screen.get_height()
            bop_h = self._video.display_height
            self.screen.blit(
                self._spotlight_surf,
                self._spotlight_surf.get_rect(
                    midbottom=(
                        self._bop_cx,
                        self._bop_cy + bop_h // 2 + int(sh * 0.05),
                    )
                ),
            )

        # Beat-scaled title image
        tw = max(1, int(self._title_base_w * self._title_scale))
        th = max(1, int(self._title_base_h * self._title_scale))
        title_surf = pygame.transform.smoothscale(self.title_img, (tw, th))
        self.screen.blit(
            title_surf,
            title_surf.get_rect(center=(self.title_cx, self.title_cy)),
        )

        # Play button
        disp_size = max(1, int(self._btn_size * self._scale))
        btn_surf  = pygame.transform.smoothscale(self._btn_base, (disp_size, disp_size))
        self.screen.blit(btn_surf, btn_surf.get_rect(center=(self.btn_cx, self.btn_cy)))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _btn_hovered(self, mouse_pos: tuple) -> bool:
        half = int(self._btn_size * self._scale) // 2
        r = pygame.Rect(self.btn_cx - half, self.btn_cy - half, half * 2, half * 2)
        return r.collidepoint(mouse_pos)

    def _update_click_animation(self, dt: float, hovered: bool) -> str | None:
        """Drive shrink → bounce.  Returns 'play' when the bounce finishes."""
        if self._click_phase is None:
            return None
        k = min(1.0, BTN_LERP_FAST * dt)
        if self._click_phase == "shrink":
            target = BTN_CLICK_SHRINK
            self._scale += (target - self._scale) * k
            if abs(self._scale - target) < CLICK_THRESHOLD:
                self._click_phase = "bounce"
        elif self._click_phase == "bounce":
            target = BTN_CLICK_BOUNCE
            self._scale += (target - self._scale) * k
            if abs(self._scale - target) < CLICK_THRESHOLD:
                self._click_phase = None
                self._scale = BTN_HOVER_SCALE if hovered else 1.0
                return "play"
        return None

    def _update_beat(self, dt: float, hovered: bool, current_time: float) -> None:
        """Fire beat pulses and decay title / button scales each frame."""
        k = min(1.0, BEAT_LERP_SPEED * dt)

        # Detect a new beat
        beat_idx = int(current_time / self._beat_period)
        if beat_idx != self._last_beat:
            self._last_beat          = beat_idx
            self._title_scale_target = BEAT_TITLE_PEAK
            if not hovered:
                self._scale = 1.0 + (BEAT_BTN_PEAK - 1.0)

        # Decay title scale back toward 1.0
        self._title_scale_target += (1.0 - self._title_scale_target) * k
        self._title_scale        += (self._title_scale_target - self._title_scale) * k

        # Lerp button scale toward hover/rest target
        base_target = BTN_HOVER_SCALE if hovered else 1.0
        self._scale += (base_target - self._scale) * min(1.0, BTN_LERP_NORMAL * dt)
