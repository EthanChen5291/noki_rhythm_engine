"""
FinishScreen — post-level results overlay shown after the outro deceleration.

Layout (inside a curved box, ~76% × 78% of screen, centered):
  • Level name — large, marquee if too wide
  • Rank (left) and Score (right) — both scale in from large → normal in 0.3 s
  • Replay / Exit — circular buttons at bottom
"""
from __future__ import annotations
import math
import os
import pygame

from ..menu_utils import _FONT
from ..screens._constants import RANKS, MARQUEE_PX_PER_SEC, MARQUEE_PAUSE_SEC
from .. import audio_manager


def _get_rank(score: int) -> tuple[str, tuple[int, int, int]]:
    for threshold, letter, color in RANKS:
        if score >= threshold:
            return letter, tuple(color)  # type: ignore[return-value]
    return "D", (210, 90, 90)


def _ease_out_expo(t: float) -> float:
    return 1.0 if t >= 1.0 else 1.0 - 2.0 ** (-10.0 * t)


def _ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    t = max(0.0, min(1.0, t))
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


class FinishScreen:
    """Run with .run() — returns 'replay' or 'exit'."""

    # Timing constants (seconds)
    BOX_EXPAND_DUR  = 0.30   # box scales in from center
    CONTENT_START   = 0.28   # when rank/score start scaling in
    CONTENT_DUR     = 0.30   # duration of rank/score scale-in
    BTN_FADE_START  = 0.52   # when buttons start fading in
    BTN_FADE_DUR    = 0.22   # fade-in duration for buttons

    # Layout fractions
    BOX_W_FRAC = 0.76
    BOX_H_FRAC = 0.78

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        backdrop: pygame.Surface,
        level_name: str,
        score: int,
        total_notes: int,
        misses: int,
    ) -> None:
        self.screen     = screen
        self.clock      = clock
        self._backdrop  = backdrop
        self.level_name = level_name
        self.score      = score
        self.t          = 0.0

        self.rank_letter, self.rank_color = _get_rank(score)

        sw, sh = screen.get_size()
        self.sw, self.sh = sw, sh
        self.box_w = int(sw * self.BOX_W_FRAC)
        self.box_h = int(sh * self.BOX_H_FRAC)
        self.box_cx = sw // 2
        self.box_cy = sh // 2

        # ── Fonts ─────────────────────────────────────────────────────────────
        _hv = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                           'assets', 'fonts', 'Heavitas.ttf')
        try:
            self._name_font  = pygame.font.Font(_hv, 64)
            self._rank_font  = pygame.font.Font(_hv, 128)
            self._label_font = pygame.font.Font(_hv, 22)
            self._btn_font   = pygame.font.Font(_hv, 40)
        except Exception:
            self._name_font  = pygame.font.Font(_FONT, 64)
            self._rank_font  = pygame.font.Font(_FONT, 128)
            self._label_font = pygame.font.Font(_FONT, 22)
            self._btn_font   = pygame.font.Font(_FONT, 40)

        self._score_font = pygame.font.Font(_FONT, 76)

        # ── Marquee state ─────────────────────────────────────────────────────
        self._marquee_offset = 0.0
        self._marquee_dir    = 1
        self._marquee_pause  = MARQUEE_PAUSE_SEC   # start with a pause

        # ── Button state ──────────────────────────────────────────────────────
        self._btn_r = int(sh * 0.072)   # radius scales with screen height
        self._replay_cx = sw // 2 - self.box_w // 4
        self._exit_cx   = sw // 2 + self.box_w // 4
        self._btn_cy    = sh // 2 + int(self.box_h * 0.30)

        self._replay_scale = 1.0
        self._exit_scale   = 1.0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _in_circle(self, pos: tuple, cx: int, cy: int, r: float) -> bool:
        dx, dy = pos[0] - cx, pos[1] - cy
        return dx * dx + dy * dy <= r * r

    def _render_name(self, clip_w: int, clip_x: int, clip_y: int) -> None:
        """Draw level name with marquee clipping if it overflows clip_w."""
        surf = self._name_font.render(self.level_name, True, (255, 255, 255))
        sw = surf.get_width()
        if sw <= clip_w:
            self.screen.blit(surf, (clip_x + (clip_w - sw) // 2, clip_y))
        else:
            excess = sw - clip_w
            clip_surf = pygame.Surface((clip_w, surf.get_height()), pygame.SRCALPHA)
            clip_surf.blit(surf, (-int(self._marquee_offset), 0))
            # Soft left/right fade edges
            for edge_x, flip in ((0, False), (clip_w - 28, True)):
                fade = pygame.Surface((28, surf.get_height()), pygame.SRCALPHA)
                for px in range(28):
                    a = int(255 * (px / 28))
                    if flip:
                        a = 255 - a
                    pygame.draw.line(fade, (0, 0, 0, 255 - a), (px, 0), (px, surf.get_height()))
                clip_surf.blit(fade, (edge_x, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(clip_surf, (clip_x, clip_y))

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float, mouse_pos: tuple, mouse_clicked: bool) -> str | None:
        self.t += dt

        # Marquee update
        name_surf = self._name_font.render(self.level_name, True, (255, 255, 255))
        clip_w = self.box_w - 80
        if name_surf.get_width() > clip_w:
            excess = name_surf.get_width() - clip_w
            if self._marquee_pause > 0:
                self._marquee_pause -= dt
            else:
                self._marquee_offset += MARQUEE_PX_PER_SEC * self._marquee_dir * dt
                if self._marquee_offset >= excess:
                    self._marquee_offset = float(excess)
                    self._marquee_dir    = -1
                    self._marquee_pause  = MARQUEE_PAUSE_SEC
                elif self._marquee_offset <= 0:
                    self._marquee_offset = 0.0
                    self._marquee_dir    = 1
                    self._marquee_pause  = MARQUEE_PAUSE_SEC

        # Button hover
        r = self._btn_r
        replay_hov = self._in_circle(mouse_pos, self._replay_cx, self._btn_cy, r)
        exit_hov   = self._in_circle(mouse_pos, self._exit_cx,   self._btn_cy, r)
        self._replay_scale += ((1.14 if replay_hov else 1.0) - self._replay_scale) * min(1.0, 14.0 * dt)
        self._exit_scale   += ((1.14 if exit_hov   else 1.0) - self._exit_scale)   * min(1.0, 14.0 * dt)

        if self.t >= self.BTN_FADE_START and mouse_clicked:
            if replay_hov:
                audio_manager.play_click()
                return "replay"
            if exit_hov:
                audio_manager.play_click()
                return "exit"

        return None

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self) -> None:
        t  = self.t
        sw, sh = self.sw, self.sh

        # Backdrop (last game frame, dimmed)
        self.screen.blit(self._backdrop, (0, 0))
        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, int(160 * min(1.0, t / 0.18))))
        self.screen.blit(dim, (0, 0))

        # ── Box scale-in from center ──────────────────────────────────────────
        box_t     = min(1.0, t / self.BOX_EXPAND_DUR)
        box_scale = _ease_out_back(box_t)
        bw = max(4, int(self.box_w * box_scale))
        bh = max(4, int(self.box_h * box_scale))
        bx = sw // 2 - bw // 2
        by = sh // 2 - bh // 2

        # Draw the box
        box_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(box_surf, (0, 0, 0, 255), (0, 0, bw, bh), border_radius=32)
        # Subtle inner gradient feel — a slightly lighter top strip
        stripe = pygame.Surface((bw, bh // 3), pygame.SRCALPHA)
        stripe.fill((255, 255, 255, 8))
        box_surf.blit(stripe, (0, 0))
        # Border
        pygame.draw.rect(box_surf, (70, 120, 210, 180), (0, 0, bw, bh), width=6, border_radius=32)
        self.screen.blit(box_surf, (bx, by))

        if box_t < 0.45:
            return  # wait until box is mostly open before drawing content

        # ── Level name ────────────────────────────────────────────────────────
        clip_w  = bw - 80
        clip_x  = bx + 40
        name_y  = by + int(bh * 0.10)
        self._render_name(clip_w, clip_x, name_y)

        # Thin divider line below name
        div_y = name_y + self._name_font.get_height() + 12
        pygame.draw.line(self.screen, (60, 90, 160), (bx + 30, div_y), (bx + bw - 30, div_y), 1)

        # ── Rank + Score scale-in ─────────────────────────────────────────────
        content_elapsed = t - self.CONTENT_START
        if content_elapsed > 0:
            ct      = min(1.0, content_elapsed / self.CONTENT_DUR)
            ease_ct = _ease_out_expo(ct)
            # starts at scale 3.5, shrinks to 1.0
            scale = 3.5 - 2.5 * ease_ct
            alpha = int(255 * min(1.0, ct * 2.5))

            content_cy = by + int(bh * 0.50)
            rank_cx    = bx + bw // 4
            score_cx   = bx + bw * 3 // 4

            # — Rank letter —
            rank_surf = self._rank_font.render(self.rank_letter, True, self.rank_color)
            rs_w = max(1, int(rank_surf.get_width()  * scale))
            rs_h = max(1, int(rank_surf.get_height() * scale))
            rank_scaled = pygame.transform.smoothscale(rank_surf, (rs_w, rs_h))
            rank_scaled.set_alpha(alpha)
            self.screen.blit(rank_scaled, rank_scaled.get_rect(center=(rank_cx, content_cy)))

            # — Score —
            score_surf = self._score_font.render(f"{self.score:,}", True, (200, 220, 255))
            ss_w = max(1, int(score_surf.get_width()  * scale))
            ss_h = max(1, int(score_surf.get_height() * scale))
            score_scaled = pygame.transform.smoothscale(score_surf, (ss_w, ss_h))
            score_scaled.set_alpha(alpha)
            self.screen.blit(score_scaled, score_scaled.get_rect(center=(score_cx, content_cy)))

            # "RANK" and "SCORE" labels — both pinned to the same y so they align
            if ct > 0.5:
                lbl_alpha = int(255 * min(1.0, (ct - 0.5) * 4))
                label_y = content_cy + max(rs_h, ss_h) // 2 + 6
                for text, cx in [("RANK", rank_cx), ("SCORE", score_cx)]:
                    lbl = self._label_font.render(text, True, (160, 185, 220))
                    lbl.set_alpha(lbl_alpha)
                    self.screen.blit(lbl, lbl.get_rect(midtop=(cx, label_y)))

        # ── Circular buttons ──────────────────────────────────────────────────
        btn_elapsed = t - self.BTN_FADE_START
        if btn_elapsed > 0:
            btn_alpha = int(255 * min(1.0, btn_elapsed / self.BTN_FADE_DUR))
            base_r    = self._btn_r

            for label, cx, scl in [
                ("REPLAY", self._replay_cx, self._replay_scale),
                ("EXIT",   self._exit_cx,   self._exit_scale),
            ]:
                r = int(base_r * scl)

                # Circle background
                csurf = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
                is_hov = scl > 1.05
                fill_a = min(btn_alpha, 210 if is_hov else 160)
                pygame.draw.circle(csurf, (55, 100, 200, fill_a), (r + 3, r + 3), r)
                # Glow ring
                pygame.draw.circle(csurf, (120, 175, 255, min(btn_alpha, 180)), (r + 3, r + 3), r, 3)
                self.screen.blit(csurf, csurf.get_rect(center=(cx, self._btn_cy)))

                # Label text
                txt = self._btn_font.render(label, True, (255, 255, 255))
                txt.set_alpha(btn_alpha)
                self.screen.blit(txt, txt.get_rect(center=(cx, self._btn_cy)))

                # Decorative circle below the button
                deco_y = self._btn_cy + base_r + 14
                deco_r = int(base_r * 0.18)
                deco_surf = pygame.Surface((deco_r * 2 + 4, deco_r * 2 + 4), pygame.SRCALPHA)
                deco_alpha = int(btn_alpha * 0.55)
                pygame.draw.circle(deco_surf, (100, 160, 255, deco_alpha), (deco_r + 2, deco_r + 2), deco_r)
                self.screen.blit(deco_surf, deco_surf.get_rect(center=(cx, deco_y)))

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> str:
        """Block until user picks replay or exit. Returns 'replay' or 'exit'."""
        while True:
            dt = min(0.05, self.clock.tick(60) / 1000.0)
            mouse_pos     = pygame.mouse.get_pos()
            mouse_clicked = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "exit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        audio_manager.play_click()
                        return "exit"
                    if event.key == pygame.K_r:
                        audio_manager.play_click()
                        return "replay"
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_clicked = True

            result = self.update(dt, mouse_pos, mouse_clicked)
            self.draw()
            pygame.display.flip()

            if result is not None:
                return result
