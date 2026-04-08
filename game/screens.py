"""
Full-screen menu views: TitleScreen, LevelSelect, LevelMenu, FileUploadScreen.
MenuManager and PauseScreen live in menu.py.
"""
import pygame
import math
import time
import os
import threading

from .menu_utils import (
    _FONT,
    _audio_duration,
    pick_audio_file,
    _fetch_lyrics_words,
    DEFAULT_WORD_BANK,
)
from .ui_components import (
    _EXIT_IMG,
    Button,
    TextInput,
    DifficultySelector,
    ImageButton,
    PNGSequenceSprite,
)


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

    def __init__(self, screen, song_names, scores=None, canon_names=None):
        self.screen     = screen
        self.song_names = song_names
        self._scores    = scores or {}
        self._canon_set: set[str] = set(canon_names) if canon_names else set(song_names)
        sw, sh = screen.get_size()

        self.header_font  = pygame.font.Font(_FONT, 60)
        self.button_font  = pygame.font.Font(_FONT, 42)
        self.diff_font    = pygame.font.Font(_FONT, 36)
        self.upload_font1 = pygame.font.Font(_FONT, 96)
        self.upload_font2 = pygame.font.Font(_FONT, 78)

        self.button_height  = 56
        self.button_spacing = 22      # more breathing room between rows

        # ── Tab geometry ──────────────────────────────────────────────────
        self.list_top       = 148     # pushed down to make room for tabs
        self._tab_font      = pygame.font.Font(_FONT, 48)
        self._active_tab    = 0       # 0 = Canon, 1 = Custom
        self._tab_lerp      = 0.0    # 0.0 → tab 0, 1.0 → tab 1 (drives highlight lerp)
        self._TAB_LERP_SPD  = 8.0    # lerp speed (units/sec)

        # ── Scrollbar geometry (right edge of right panel) ───────────────
        self._sb_w      = 6
        self._sb_margin = 12
        self._sb_x      = sw - self._sb_margin - self._sb_w
        self._sb_y      = self.list_top  # updated after list_top is set above
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

        # parallel lists of per-song_names index, one per tab
        # _tab_indices[t] = list of indices into song_names for that tab
        self._tab_indices: list[list[int]] = [[], []]  # [0]=canon, [1]=custom

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
            tab = 0 if name in self._canon_set else 1
            self._tab_indices[tab].append(i)

        # Now _tab_indices is complete — compute per-tab max scrolls
        self._recompute_max_scrolls(sh)

        # inline rename state (set by begin_rename after upload)
        self._rename_idx: int | None = None
        self._rename_input: TextInput | None = None
        self._rename_result: tuple[int, str] = (0, "")
        self._rename_font = pygame.font.Font(_FONT, 42)   # matches button_font

        # rename push animation — songs below the new slot lerp down then back up
        _RENAME_PUSH_AMOUNT    = (self.button_height + self.button_spacing) * 0.75
        self._rename_push_px   = _RENAME_PUSH_AMOUNT   # pixels to push songs below
        self._rename_push_t    = 0.0    # 0 = normal, 1 = fully pushed
        self._rename_push_dir  = 0      # +1 opening, -1 closing
        self._rename_push_start: float = 0.0
        self._RENAME_PUSH_DUR  = 0.22   # seconds

        _btn_sz = 52
        self.back_button = ImageButton(30 + _btn_sz // 2, 30 + _btn_sz // 2, _btn_sz, _EXIT_IMG)
        self._scroll_offsets  = [0, 0]   # per-tab scroll (max scrolls already computed above)

        # ── Tab geometry (built after div_x is known) ────────────────────
        # Two chrome tabs centered across the right panel.
        # Bottom of tabs aligns with list_top (where songs start clipping).
        tab_panel_x = div_x + 1
        tab_panel_w = sw - tab_panel_x
        self._tab_labels    = ["Canon", "Custom"]
        self._tab_rects: list[pygame.Rect] = []
        self._tab_div_x     = div_x          # saved for underline drawing
        # Underline position + 3% of screen height offset
        self._tab_underline_y = int(self.list_top * 0.75) + int(sh * 0.03)
        # Top of tab has a fixed margin so it's never clipped by the screen edge
        _tab_top = 8 + int(sh * 0.03)
        _tab_h   = self._tab_underline_y - _tab_top
        # Width: 2.5× the old ~130 cap ≈ 325, capped so both fit in panel
        _tab_w   = min(int(tab_panel_w * 0.38), 325)
        _tab_gap = 10
        _total_tabs_w = 2 * _tab_w + _tab_gap
        _tabs_left = tab_panel_x + (tab_panel_w - _total_tabs_w) // 2
        for t in range(2):
            self._tab_rects.append(pygame.Rect(
                _tabs_left + t * (_tab_w + _tab_gap),
                _tab_top, _tab_w, _tab_h,
            ))

    # ── per-tab scroll helpers ────────────────────────────────────────────

    def _recompute_max_scrolls(self, sh=None):
        if sh is None:
            sh = self.screen.get_height()
        viewport = sh - self.list_top - 40
        self._max_scrolls = [
            max(0, len(self._tab_indices[t]) * (self.button_height + self.button_spacing) - viewport)
            for t in range(2)
        ]

    @property
    def max_scroll(self) -> int:
        return self._max_scrolls[self._active_tab]

    @property
    def scroll_offset(self) -> int:
        return self._scroll_offsets[self._active_tab]

    @scroll_offset.setter
    def scroll_offset(self, v: int):
        self._scroll_offsets[self._active_tab] = max(0, min(v, self._max_scrolls[self._active_tab]))

    def switch_tab(self, tab: int):
        if tab != self._active_tab:
            self._active_tab = tab

    def begin_rename(self, idx: int):
        """Start an inline rename for the slot at idx and animate songs below downward."""
        self._rename_idx = idx
        btn = self.level_buttons[idx]
        rect = pygame.Rect(btn.rect.x + 8, btn.rect.y + 8,
                           btn.rect.w - 16, btn.rect.h - 16)
        self._rename_input = TextInput(rect, self._rename_font, placeholder="Enter song name…")
        self._rename_input.active = True
        # snap scroll to top so new slot is always visible
        self.scroll_offset = 0
        # kick off open animation
        self._rename_push_dir   = 1
        self._rename_push_start = time.time()

    def cancel_rename_anim(self):
        """Start the close animation (songs lerp back up)."""
        self._rename_push_dir   = -1
        self._rename_push_start = time.time()

    def _finish_rename(self) -> tuple[int, str] | None:
        """Commit rename; returns (idx, new_display) or None if blank (keep original)."""
        idx   = self._rename_idx
        inp   = self._rename_input
        self._rename_idx   = None
        self._rename_input = None
        # snap push back to 0 immediately on commit
        self._rename_push_t   = 0.0
        self._rename_push_dir = 0
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
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._sb_drag = False
        elif event.type == pygame.MOUSEMOTION and self._sb_drag:
            dy = event.pos[1] - self._sb_drag_start_y
            ms = self.max_scroll
            if self._sb_h > 0 and ms > 0:
                self.scroll_offset = self._sb_drag_start_offset + int(
                    dy * 0.9 * ms / self._sb_h
                )

    def _sb_thumb_rect(self) -> pygame.Rect | None:
        ms = self.max_scroll
        if ms <= 0:
            return None
        n = len(self._tab_indices[self._active_tab])
        if n == 0:
            return None
        viewport_h = self._sb_h
        total_h    = n * (self.button_height + self.button_spacing)
        thumb_h    = max(24, int(viewport_h * viewport_h / total_h))
        thumb_y    = self._sb_y + int((viewport_h - thumb_h) * self.scroll_offset / ms)
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
                        self.cancel_rename_anim()
                        return "cancel_upload", cancel_idx
                    elif ev.key == pygame.K_BACKSPACE:
                        self._rename_input.text = self._rename_input.text[:-1]
                    elif ev.unicode.isprintable():
                        if len(self._rename_input.text) < 80:
                            self._rename_input.text += ev.unicode
            return None, -1  # swallow all other actions while renaming

        if self.back_button.update(mouse_pos, mouse_clicked):
            return "back", -1

        # ── Tab clicks ───────────────────────────────────────────────────
        if mouse_clicked:
            for t, tr in enumerate(self._tab_rects):
                if tr.collidepoint(mouse_pos):
                    self.switch_tab(t)

        self._upload_hovered = self.upload_rect.collidepoint(mouse_pos)
        if mouse_clicked and self._upload_hovered:
            return "upload", -1

        # Scrollbar click / drag start
        ms = self.max_scroll
        if mouse_clicked and ms > 0:
            thumb = self._sb_thumb_rect()
            if thumb and thumb.collidepoint(mouse_pos):
                self._sb_drag = True
                self._sb_drag_start_y      = mouse_pos[1]
                self._sb_drag_start_offset = self.scroll_offset
            else:
                track = pygame.Rect(self._sb_x, self._sb_y, self._sb_w, self._sb_h)
                if track.collidepoint(mouse_pos):
                    t = (mouse_pos[1] - self._sb_y) / self._sb_h
                    self.scroll_offset = int(t * ms)

        # Hit-test active-tab buttons using their tab-row vis_y
        row_h = self.button_height + self.button_spacing
        for row, song_i in enumerate(self._tab_indices[self._active_tab]):
            btn = self.level_buttons[song_i]
            row_y = self.list_top + row * row_h - self.scroll_offset
            btn_rect = pygame.Rect(btn.rect.x, row_y, btn.rect.w, btn.rect.h)
            hovered = btn_rect.collidepoint(mouse_pos)
            btn.is_hovered = hovered
            btn._target_scale = 1.08 if hovered else 1.0
            if hovered and mouse_clicked:
                return "select", song_i

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

        # ── Tab lerp ─────────────────────────────────────────────────────
        target_lerp = float(self._active_tab)
        self._tab_lerp += (target_lerp - self._tab_lerp) * min(1.0, self._TAB_LERP_SPD / 60.0)

        # ── Chrome tabs ──────────────────────────────────────────────────
        _ul_y   = self._tab_underline_y   # y of the horizontal underline
        _radius = 12                       # top-corner radius

        def _draw_chrome_tab(surf, rect, bg_col, bord_col):
            """Draw a chrome-style tab: rounded top corners, open/flat bottom."""
            x, y, w, h = rect.x, rect.y, rect.width, rect.height
            r = _radius

            pygame.draw.rect(surf, bg_col, rect, border_radius=r)
            pygame.draw.rect(surf, bg_col, pygame.Rect(x, y + h - r, w, r))

            pts: list[tuple[float, float]] = []
            pts.append((x, y + h))
            pts.append((x, y + r))
            for i in range(11):
                a = math.pi + i * (math.pi / 2) / 10
                pts.append((x + r + r * math.cos(a), y + r + r * math.sin(a)))
            for i in range(11):
                a = -math.pi / 2 + i * (math.pi / 2) / 10
                pts.append((x + w - r + r * math.cos(a), y + r + r * math.sin(a)))
            pts.append((x + w, y + r))
            pts.append((x + w, y + h))
            if len(pts) >= 2:
                pygame.draw.lines(surf, bord_col, False, pts, 2)

        for t, (tr, label) in enumerate(zip(self._tab_rects, self._tab_labels)):
            if t == 0:
                hi = 1.0 - self._tab_lerp
            else:
                hi = self._tab_lerp
            bg_r   = int(18 + 40 * hi)
            bg_col = (bg_r, bg_r, bg_r + 10)
            bord_col = (int(55 + 130 * hi),) * 3
            _draw_chrome_tab(self.screen, tr, bg_col, bord_col)
            txt_col = (int(170 + 85 * hi),) * 3
            ts = self._tab_font.render(label, True, txt_col)
            self.screen.blit(ts, ts.get_rect(center=tr.center))

        # Horizontal underline from the vertical divider to the right edge
        pygame.draw.line(
            self.screen,
            (70, 70, 80),
            (self._tab_div_x, _ul_y),
            (sw, _ul_y),
            2,
        )
        # Erase underline beneath the active tab so it looks "open" at the bottom
        _active_idx = int(round(self._tab_lerp))
        _active_tr  = self._tab_rects[_active_idx]
        _hi_active  = 1.0 - self._tab_lerp if _active_idx == 0 else self._tab_lerp
        _erase_r    = int(18 + 40 * _hi_active)
        _erase_col  = (_erase_r, _erase_r, _erase_r + 10)
        pygame.draw.line(
            self.screen, _erase_col,
            (_active_tr.left + 3, _ul_y),
            (_active_tr.right - 3, _ul_y),
            3,
        )

        # ── advance rename push animation ────────────────────────────────
        if self._rename_push_dir != 0:
            raw = (current_time - self._rename_push_start) / self._RENAME_PUSH_DUR
            t   = min(1.0, max(0.0, raw))
            ease = t * t * (3.0 - 2.0 * t)   # smoothstep
            if self._rename_push_dir == 1:
                self._rename_push_t = ease
            else:
                self._rename_push_t = 1.0 - ease
                if t >= 1.0:
                    self._rename_push_dir = 0   # animation done

        # Scrollable list
        scroll_clip = pygame.Rect(div_x + 1, self.list_top - 10, sw, sh - self.list_top)
        self.screen.set_clip(scroll_clip)

        _SCROLL_SPEED = 48   # px / sec  — how fast the marquee moves
        _PAUSE        = 2.0  # sec pause at left edge before scrolling

        _push_offset = int(self._rename_push_px * self._rename_push_t)
        _rename_row  = self._rename_idx if self._rename_idx is not None else -1
        _row_h       = self.button_height + self.button_spacing
        _active_indices = self._tab_indices[self._active_tab]

        # Empty Custom tab message
        if self._active_tab == 1 and not _active_indices:
            _empty_font = pygame.font.Font(_FONT, 52)
            _empty_surf = _empty_font.render("No levels uploaded", True, (120, 120, 130))
            sw2, sh2 = self.screen.get_size()
            div_x2 = int(sw2 * self._LEFT_FRAC)
            _empty_rect = _empty_surf.get_rect(
                center=(div_x2 + (sw2 - div_x2) // 2,
                        self.list_top + (sh2 - self.list_top) // 2)
            )
            self.screen.blit(_empty_surf, _empty_rect)

        for row, i in enumerate(_active_indices):
            btn   = self.level_buttons[i]
            extra = _push_offset if i > _rename_row else 0
            vis_y = self.list_top + row * _row_h - self.scroll_offset + extra

            # ── hover glow ──────────────────────────────────────────────
            btn._scale += (btn._target_scale - btn._scale) * 0.18
            if btn.is_hovered:
                glow = pygame.Rect(btn.rect.x, vis_y, btn.rect.w, btn.rect.h).inflate(8, 8)
                pygame.draw.rect(self.screen, (80, 80, 100), glow, 2, border_radius=8)

            # ── marquee text (skip for the slot currently being renamed) ──
            is_renaming_slot = (self._rename_input is not None and self._rename_idx == i)

            if not is_renaming_slot:
                color     = btn.hover_color if btn.is_hovered else btn.base_color
                text_surf = btn.font.render(self._full_names[i], True, color)
                tw        = text_surf.get_width()
                pad       = 10
                clip_w    = btn.rect.w - pad
                text_y    = vis_y + (btn.rect.h - text_surf.get_height()) // 2

                if tw > clip_w:
                    max_off   = tw - clip_w
                    scroll_t  = max_off / _SCROLL_SPEED
                    cycle     = _PAUSE + scroll_t + _PAUSE + scroll_t
                    t         = (current_time + i * 0.4) % cycle
                    if t < _PAUSE:
                        x_off = 0
                    elif t < _PAUSE + scroll_t:
                        x_off = int((t - _PAUSE) * _SCROLL_SPEED)
                    elif t < _PAUSE + scroll_t + _PAUSE:
                        x_off = max_off
                    else:
                        x_off = int(max_off - (t - _PAUSE - scroll_t - _PAUSE) * _SCROLL_SPEED)
                    draw_x = btn.rect.x + pad - x_off
                else:
                    draw_x = btn.rect.x + (btn.rect.w - tw) // 2

                text_clip = pygame.Rect(btn.rect.x + pad, vis_y, clip_w, btn.rect.h)
                old_clip  = self.screen.get_clip()
                self.screen.set_clip(text_clip.clip(old_clip))
                self.screen.blit(text_surf, (draw_x, text_y))
                self.screen.set_clip(old_clip)

            # ── inline rename textbox ────────────────────────────────────
            if is_renaming_slot and self._rename_input is not None:
                inp = self._rename_input
                cx  = btn.rect.x + btn.rect.w // 2
                cy  = vis_y + btn.rect.h // 2

                tsurf = self._rename_font.render(inp.text, True, (255, 255, 255)) if inp.text \
                        else None
                th = self._rename_font.get_height()

                if tsurf is not None:
                    old_clip  = self.screen.get_clip()
                    slot_clip = pygame.Rect(btn.rect.x, vis_y, btn.rect.w, btn.rect.h)
                    self.screen.set_clip(slot_clip.clip(old_clip))
                    self.screen.blit(tsurf, tsurf.get_rect(center=(cx, cy)))
                    self.screen.set_clip(old_clip)

                # blinking cursor — taller and thicker
                if int(current_time * 2) % 2 == 0:
                    tw_half = (tsurf.get_width() // 2) if tsurf else 0
                    cur_x   = min(cx + tw_half + 4, btn.rect.x + btn.rect.w - 6)
                    cur_h   = int(th * 0.85)
                    pygame.draw.line(self.screen, (200, 200, 255),
                                     (cur_x, cy - cur_h // 2),
                                     (cur_x, cy + cur_h // 2), 3)
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
    """Popup shown when a level row is clicked."""
    _BORD     = 2
    _ANIM_DUR = 0.13   # seconds for enter / exit

    def __init__(self, screen, song_idx, song_name, initial_diff_idx, scores,
                 origin_rect=None):
        self.screen    = screen
        self.song_idx  = song_idx
        self.song_name = song_name
        self._scores   = scores

        sw, sh = screen.get_size()

        pw = int(sw * 0.78)
        ph = int(sh * 0.56)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        self.rect = pygame.Rect(px, py, pw, ph)

        self._px, self._py, self._pw, self._ph = px, py, pw, ph
        _pad              = max(24, pw // 30)
        self._pad         = _pad
        self._mid_x       = px + pw // 2
        self._top_h       = int(ph * 0.20)
        self._bot_h       = int(ph * 0.28)
        self._body_top    = py + self._top_h
        self._body_bottom = py + ph - self._bot_h
        self._body_cy     = (self._body_top + self._body_bottom) // 2

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

        self._overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)

        self._origin = origin_rect.copy() if origin_rect else pygame.Rect(
            px + pw // 2, py + ph // 2, 0, 0
        )
        self._anim_start  = time.time()
        self._closing     = False
        self._close_start = 0.0

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
        """0 → 1 while opening; 1 → 0 while closing."""
        if self._closing:
            raw = (current_time - self._close_start) / self._ANIM_DUR
            t   = min(1.0, raw)
            return 1.0 - t * t
        else:
            raw = (current_time - self._anim_start) / self._ANIM_DUR
            t   = min(1.0, raw)
            return 1.0 - (1.0 - t) ** 3

    def update(self, mouse_pos, mouse_clicked, current_time):
        """Returns 'play', 'close', or None."""
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
        at = self._anim_t(current_time)
        cur = self._lerp_rect(self._origin, self.rect, at)
        pad = self._pad

        self._overlay.fill((0, 0, 0, int(155 * at)))
        self.screen.blit(self._overlay, (0, 0))

        pygame.draw.rect(self.screen, (8, 8, 14),     cur, border_radius=14)
        pygame.draw.rect(self.screen, (255, 255, 255), cur, self._BORD, border_radius=14)

        if at < 0.55:
            return

        content_a = min(255, int(255 * (at - 0.55) / 0.45))

        def _blit_a(surf, rect):
            surf = surf.copy()
            surf.set_alpha(content_a)
            self.screen.blit(surf, rect)

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

        field_w = 360
        self.input_title = TextInput(
            (sw // 2 - field_w // 2, cy - 60, field_w, 44),
            input_font, placeholder="Song Name  (optional)",
        )
        self.input_artist = TextInput(
            (sw // 2 - field_w // 2, cy + 12, field_w, 44),
            input_font, placeholder="Artist  (optional)",
        )

        self._fetching    = False
        self._fetch_done  = False
        self._fetch_words: list[str] = []
        self._fetch_thread: threading.Thread | None = None
        self._spinner_idx = 0
        self._spinner_t   = 0.0

    def show_error(self, message):
        self.status_msg   = message
        self.status_color = (255, 120, 120)

    def _start_fetch(self):
        title  = self.input_title.text.strip()
        artist = self.input_artist.text.strip()
        result_box: list[list[str]] = [[]]

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

    def update(self, mouse_pos, mouse_clicked, current_time, events):
        self.input_title.handle_events(events)
        self.input_artist.handle_events(events)

        if self.back_button.update(mouse_pos, mouse_clicked):
            return "back", None, None

        if self._fetching:
            if self._fetch_thread and not self._fetch_thread.is_alive():
                self._fetching   = False
                self._fetch_done = True
                self._fetch_words = self._result_box[0]
            return None, None, None

        if self._fetch_done:
            self._fetch_done = False
            return "upload", self.selected_path, self._fetch_words

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

        status = self.status_font.render(self.status_msg, True, self.status_color)
        self.screen.blit(status, status.get_rect(center=(sw // 2, cy - 96)))

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

        lbl_color = (130, 130, 160)
        lbl1 = self.label_font.render("Song Name", True, lbl_color)
        lbl2 = self.label_font.render("Artist", True, lbl_color)
        self.screen.blit(lbl1, lbl1.get_rect(bottomleft=(self.input_title.rect.x,
                                                          self.input_title.rect.y - 4)))
        self.screen.blit(lbl2, lbl2.get_rect(bottomleft=(self.input_artist.rect.x,
                                                          self.input_artist.rect.y - 4)))
        self.input_title.draw(self.screen, current_time)
        self.input_artist.draw(self.screen, current_time)

        if not (self.input_title.text or self.input_artist.text):
            hint_font = pygame.font.Font(_FONT, 26)
            hint = hint_font.render(
                "Leave blank to use a built-in word set.", True, (70, 70, 90)
            )
            self.screen.blit(hint, hint.get_rect(center=(sw // 2, cy + 68)))

        if self.selected_path:
            self.add_button.draw(self.screen, current_time)

        self.back_button.draw(self.screen, current_time)
