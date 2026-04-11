"""
Core Game class — init, run loop, pause, and main update tick.
Visual effects  → effects.py      (EffectsMixin)
Game mechanics  → mechanics.py    (MechanicsMixin)
Word rendering  → word_renderer.py     (WordRenderer)
Timeline render → timeline_renderer.py (TimelineRenderer)
Note rendering  → note_renderer.py     (NoteRenderer)
"""
import pygame
import sys
import time
import os
import math

from . import constants as C
from .rhythm import RhythmManager, calculate_lead_in
from .input import Input
from .beatmap_generator import generate_beatmap
from analysis.audio_analysis import (
    get_song_info,
    detect_drops,
    classify_pace,
    calculate_energy_shifts,
    calculate_scroll_tiers,
    detect_dual_side_sections,
    detect_climax_shake_beats,
)
from . import models as M
from .menu import PauseScreen, Button
from .menu_utils import _FONT
from .effects import EffectsMixin
from .mechanics import MechanicsMixin, BounceEvent
from .word_renderer import WordRenderer
from .timeline_renderer import TimelineRenderer
from .note_renderer import NoteRenderer

pygame.init()


class Game(EffectsMixin, MechanicsMixin):
    def __init__(self, level, screen=None, clock=None) -> None:
        if screen is not None:
            self.screen = screen
        else:
            info = pygame.display.Info()
            screen_width, screen_height = info.current_w, info.current_h
            self.screen = pygame.display.set_mode((screen_width, screen_height), pygame.RESIZABLE)
            pygame.display.set_caption("Rhythm Typing Game")
        self.clock = clock if clock is not None else pygame.time.Clock()
        screen_width, screen_height = self.screen.get_size()
        self.running = False
        self.last_char_idx = -1
        self.used_current_char = False

        self.score = 0
        self.misses = 0
        self.font = pygame.font.Font(_FONT, 48)
        self._last_score = 0
        self._score_popups: list[dict] = []
        self._score_font = pygame.font.Font(_FONT, 56)
        self._popup_font = pygame.font.Font(_FONT, 38)

        self._hold_particles: list[dict] = []
        self._hit_bursts: list[dict] = []

        self.message = None
        self.message_duration = 0.0

        self._last_displayed_word = None
        self._previous_word = None
        self._word_transition_start = 0.0

        # --- load quick assets first
        self.level = level
        abs_song_path = C._to_abs_path(level.song_path)
        if abs_song_path is None:
            raise ValueError(f"Invalid song path: {level.song_path}")
        self.song_path = abs_song_path

        assets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'images')

        import cv2 as _cv2
        # Match title screen: cat height = 38% of screen (title screen uses 40%).
        _bop_target_h = max(300, int(screen_height * 0.38))
        self._bop_frames: list[pygame.Surface] = []
        self._bop_fps    = 30.0
        self._bop_native_bpm = 100.0
        self._bop_surf   = None
        self._hurt_frames: list[pygame.Surface] = []
        self._hurt_fps: float = 30.0

        self._hurt_playing: bool = False
        self._hurt_frame_idx: float = 0.0
        self._hurt_queued: int = 0

        self.cat_frame = None

        timeline_file = os.path.join(assets_path, 'noki_timeline.png')
        self.timeline_img = pygame.image.load(timeline_file).convert_alpha()
        self.timeline_img = pygame.transform.scale(self.timeline_img, (1920, 200))

        def _scale_to_height(surf, h):
            w0, h0 = surf.get_size()
            return pygame.transform.smoothscale(surf, (max(1, int(w0 * h / h0)), h))

        self._measureline_img = _scale_to_height(
            pygame.image.load(os.path.join(assets_path, 'measureline.png')).convert_alpha(), 100)
        self._beatline_img = _scale_to_height(
            pygame.image.load(os.path.join(assets_path, 'beatline.png')).convert_alpha(), 60)

        _hm_w = 2 * abs(C.HIT_MARKER_X_OFFSET)
        _hm_h = 2 * abs(C.HIT_MARKER_Y_OFFSET)
        self.hitmarker_img = pygame.transform.smoothscale(
            pygame.image.load(os.path.join(assets_path, 'hitmarker.png')).convert_alpha(),
            (_hm_w, _hm_h)
        )
        self.glowed_hitmarker_img = pygame.transform.smoothscale(
            pygame.image.load(os.path.join(assets_path, 'glowed_hitmarker.png')).convert_alpha(),
            (_hm_w, _hm_h)
        )
        self.glowed_hitmarker_golden_img = pygame.transform.smoothscale(
            pygame.image.load(os.path.join(assets_path, 'glowed_hitmarker_golden.png')).convert_alpha(),
            (_hm_w, _hm_h)
        )
        # Glow flash state: elapsed seconds since trigger, -1 = inactive
        self._glow_press_t: float = -1.0

        # Petal spinner images
        _psz = 40
        _p1  = pygame.transform.smoothscale(
            pygame.image.load(os.path.join(assets_path, 'petal1.png')).convert_alpha(), (_psz, _psz))
        _p2  = pygame.transform.smoothscale(
            pygame.image.load(os.path.join(assets_path, 'petal2.png')).convert_alpha(), (_psz, _psz))
        _cx, _cy = screen_width // 2, screen_height // 2
        _radius  = 50

        # --- run heavy analysis in background thread ---
        import threading as _threading
        _result: dict = {}
        _errors: list = []

        def _worker():
            try:
                song       = get_song_info(self.song_path, expected_bpm=level.bpm, normalize=True)
                bdur       = 60 / song.bpm
                pace       = classify_pace(self.song_path, song.bpm)
                dual_secs  = detect_dual_side_sections(
                    self.song_path, song.bpm, pace.pace_score, song.beat_times)
                diff_prof  = C.DIFFICULTY_PROFILES.get(
                    level.difficulty, C.DIFFICULTY_PROFILES["classic"])
                beatmap    = generate_beatmap(
                    word_list=level.word_bank, song=song,
                    dual_side_sections=dual_secs, difficulty=level.difficulty)
                lead_in    = calculate_lead_in(song.beat_times)
                rhythm     = RhythmManager(
                    beatmap, song.bpm, lead_in=lead_in,
                    timing_scale=diff_prof.timing_scale)
                drops      = detect_drops(song.beat_times, self.song_path, song.bpm)
                tiers      = calculate_scroll_tiers(
                    self.song_path, song.bpm, pace.pace_score, song.beat_times)
                shifts     = calculate_energy_shifts(
                    self.song_path, song.bpm, pace.pace_score, song.beat_times)
                shake_beats = detect_climax_shake_beats(
                    pace.pace_score, song.bpm, self.song_path, song.beat_times, tiers)
                print(f"[shake] pace_score={pace.pace_score:.3f}  bpm={song.bpm:.1f}  shake_beats={len(shake_beats)}")
                _result.update(song=song, beat_duration=bdur, pace_profile=pace,
                               dual_side_sections=dual_secs, difficulty_profile=diff_prof,
                               rhythm=rhythm, drop_events=drops, scroll_tiers=tiers,
                               energy_shifts=shifts, climax_shake_beats=shake_beats)
            except Exception as exc:
                _errors.append(exc)

        _thread = _threading.Thread(target=_worker, daemon=True)
        _thread.start()

        # ── Decode noki_bop / noki_hurt frames while analysis runs in bg ──
        # cv2.resize on the numpy array before make_surface avoids creating
        # a full 1920×1500 pygame surface for each frame (~10× faster).
        def _decode_video_frames(path: str) -> tuple[list[pygame.Surface], float]:
            frames: list[pygame.Surface] = []
            fps = 30.0
            cap = _cv2.VideoCapture(path)
            if cap.isOpened():
                _r = cap.get(_cv2.CAP_PROP_FPS)
                if _r > 0:
                    fps = _r
                while True:
                    ret, frm = cap.read()
                    if not ret:
                        break
                    rgb = _cv2.cvtColor(frm, _cv2.COLOR_BGR2RGB)
                    fh, fw = rgb.shape[:2]
                    fw_scaled = max(1, int(fw * _bop_target_h / fh))
                    rgb_small = _cv2.resize(rgb, (fw_scaled, _bop_target_h),
                                            interpolation=_cv2.INTER_AREA)
                    frames.append(pygame.surfarray.make_surface(
                        rgb_small.transpose(1, 0, 2)))
            cap.release()
            return frames, fps

        _bop_path  = os.path.join(assets_path, "noki_bop.mov")
        _hurt_path = os.path.join(assets_path, "noki_hurt.mov")
        self._bop_frames,  self._bop_fps  = _decode_video_frames(_bop_path)
        self._hurt_frames, self._hurt_fps = _decode_video_frames(_hurt_path)

        # --- petal spinner loop ---
        _P1 = (60.0 / 45.0) / 0.7
        _P2 = _P1 * 0.65
        _P2_OFFSET = _P2 * 0.375

        _spin_start = time.time()
        _spin_clock = pygame.time.Clock()

        _SHADOW_STEPS  = 3
        _SHADOW_ALPHAS = [120, 60, 25]

        def _petal_angle(t_norm: float) -> float:
            if t_norm < 0.5:
                p    = t_norm / 0.5
                ease = p * p
                return math.pi / 2 - math.pi * ease
            else:
                p    = (t_norm - 0.5) / 0.5
                ease = 1.0 - (1.0 - p) ** 4
                return -math.pi / 2 - math.pi * ease

        _LAG_TIME = 0.045

        def _draw_petal_with_shadow(pimg, elapsed, period, offset):
            t_now  = ((elapsed + offset) % period) / period
            a_now  = _petal_angle(t_now)
            for step in range(_SHADOW_STEPS, 0, -1):
                past_elapsed = elapsed - _LAG_TIME * step
                t_past = ((past_elapsed + offset) % period) / period
                ghost_a = _petal_angle(t_past)
                gx  = _cx + _radius * math.cos(ghost_a)
                gy  = _cy - _radius * math.sin(ghost_a)
                grot  = pygame.transform.rotate(pimg, math.degrees(ghost_a))
                gsurf = grot.copy()
                gsurf.set_alpha(_SHADOW_ALPHAS[step - 1])
                self.screen.blit(gsurf, gsurf.get_rect(center=(int(gx), int(gy))))
            px  = _cx + _radius * math.cos(a_now)
            py  = _cy - _radius * math.sin(a_now)
            rot = pygame.transform.rotate(pimg, math.degrees(a_now))
            self.screen.blit(rot, rot.get_rect(center=(int(px), int(py))))

        while _thread.is_alive():
            _spin_clock.tick(60)
            _elapsed = time.time() - _spin_start

            self.screen.fill((0, 0, 0))
            _draw_petal_with_shadow(_p1, _elapsed, _P1, 0.0)
            _draw_petal_with_shadow(_p2, _elapsed, _P2, _P2_OFFSET)
            pygame.display.flip()

            for _ev in pygame.event.get():
                if _ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

        if _errors:
            raise _errors[0]

        # --- unpack thread results ---
        self.song               = _result['song']
        self.beat_duration      = _result['beat_duration']
        self.pace_profile       = _result['pace_profile']
        self.dual_side_sections = _result['dual_side_sections']
        self.difficulty_profile = _result['difficulty_profile']
        self.rhythm             = _result['rhythm']
        self.drop_events        = _result['drop_events']
        self.scroll_tiers          = _result['scroll_tiers']
        self.energy_shifts         = _result['energy_shifts']
        self._climax_shake_beats   = _result['climax_shake_beats']  # [(song_time, intensity), ...]
        if self._climax_shake_beats and self.song.beat_times:
            # Only allow shaking after the first 20% of the song has passed
            _cutoff = self.song.beat_times[-1] * 0.20
            self._climax_shake_beats = [(t, i) for t, i in self._climax_shake_beats if t >= _cutoff]
            # Guard: at most one shake per 2-beat window (keep highest intensity per window)
            _window = self.beat_duration * 2
            _by_window: dict[int, tuple] = {}
            for _t, _i in self._climax_shake_beats:
                _w = int(_t / _window)
                if _w not in _by_window or _i > _by_window[_w][1]:
                    _by_window[_w] = (_t, _i)
            self._climax_shake_beats = sorted(_by_window.values())
        self._climax_shake_idx     = 0

        # --- screen shake state ---
        self._shake_x: float            = 0.0
        self._shake_sequence: list      = []
        self._shake_seq_idx: int        = 0
        self._shake_step_elapsed: float = 0.0

        self.input = Input()

        self.shockwaves: list[M.Shockwave] = []
        self.drops_triggered: set[int] = set()
        self.drop_note_indices = self._find_drop_note_indices()

        # --- scroll speed ---
        self.base_scroll_speed = C.SCROLL_SPEED * self.difficulty_profile.scroll_scale
        self.pace_bias         = 0.85 + self.pace_profile.pace_score * 1.3
        self.scroll_speed      = self.base_scroll_speed * self.pace_bias

        # --- outro deceleration ---
        self._outro_active     = False
        self._outro_start_time = 0.0
        self._outro_dur        = 3.0
        self._outro_start_spd  = 0.0

        _silence_start = self.song.duration
        _bt = self.song.beat_times
        if len(_bt) > 8:
            _avg_gap = (_bt[-1] - _bt[0]) / max(1, len(_bt) - 1)
            for _bi in range(len(_bt) - 1, 0, -1):
                if (_bt[_bi] - _bt[_bi - 1]) > _avg_gap * 2.5:
                    _silence_start = _bt[_bi - 1]
                    break
        if self.song.duration - _silence_start < 2.0:
            _silence_start = self.song.duration
        self._silence_start = _silence_start

        # --- bounce mode ---
        self.bounce_events: list[BounceEvent] = []
        self.bounce_active: bool = False
        self.bounce_reversed: bool = False
        self._next_bounce_idx: int = 0
        self._build_bounce_events()
        self._apply_bounce_grace_periods()

        # --- cat position ---
        self.cat_base_x    = 150 - int(screen_width * 0.02)
        self.cat_center_x  = screen_width // 2 - 115 - int(screen_width * 0.065)
        self.cat_current_x = float(self.cat_base_x)
        self.cat_velocity  = 0.0
        self.dual_side_active        = False
        self.dual_side_visuals_active = False

        # --- timeline animation ---
        self.timeline_normal_start = 300
        self.timeline_normal_end   = 1500
        self.timeline_dual_start   = 0
        self.timeline_dual_end     = screen_width
        self.timeline_current_start = float(self.timeline_normal_start)
        self.timeline_current_end   = float(self.timeline_normal_end)
        self.timeline_start_velocity = 0.0
        self.timeline_end_velocity   = 0.0
        self.hit_marker_normal_x     = C.HIT_X - C.HIT_MARKER_X_OFFSET
        self.hit_marker_dual_x       = screen_width // 2
        self.hit_marker_current_x    = float(self.hit_marker_normal_x)
        self.hit_marker_velocity     = 0.0

        self.word_normal_y  = 180
        self.word_dual_y    = 480
        self.word_current_y = float(self.word_normal_y)
        self.word_y_velocity = 0.0

        self.missed_note_shockwaves: set[int] = set()
        self._last_dual_end_time: float = -10.0

        self._timeline_flash: float = 0.0
        self._timeline_shake_offset: float = 0.0

        # --- pause state ---
        self.paused = False
        self.pause_screen: PauseScreen | None = None
        self.pause_time_accumulated = 0.0
        self._pause_start = 0.0
        pause_font = pygame.font.Font(_FONT, 36)
        self.pause_button = Button(
            (screen_width - 100, 20, 80, 40),
            "II",
            pause_font,
            base_color=(120, 120, 120),
            hover_color=(255, 255, 255),
        )

        # --- renderer managers ---
        self.word_renderer = WordRenderer(self)
        self.timeline_renderer = TimelineRenderer(self)
        self.note_renderer = NoteRenderer(self)

        # --- play music ---
        pygame.mixer.init()
        pygame.mixer.music.load(self.song_path)
        pygame.mixer.music.play()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def show_message(self, txt: str, secs: float) -> None:
        self.message = txt
        self.message_duration = secs

    def render_timeline(self) -> None:
        current_time = time.perf_counter() - self.rhythm.start_time

        self.word_renderer.render(current_time)

        timeline_y = 380
        if self._timeline_shake_offset > 0.3:
            timeline_y += int(self._timeline_shake_offset)
            self._timeline_shake_offset *= -0.5
        else:
            self._timeline_shake_offset = 0.0

        timeline_start_x = int(self.timeline_current_start)
        timeline_end_x = int(self.timeline_current_end)
        hit_marker_x = self.hit_marker_current_x

        self.timeline_renderer.render(
            current_time, timeline_y, timeline_start_x, timeline_end_x, hit_marker_x)
        self.note_renderer.render(
            current_time, timeline_y, timeline_start_x, timeline_end_x, hit_marker_x)

    def run(self):
        """Run the game loop. Returns 'menu' if player exits to menu, None otherwise."""
        self.running = True
        self._exit_to_menu = False
        while self.running:
            dt = self.clock.tick(60) / 1000
            if self.paused:
                self._update_paused(dt)
            else:
                self.update(dt)
            pygame.display.flip()

        pygame.mixer.music.stop()
        return "menu" if self._exit_to_menu else None

    def _enter_pause(self):
        self.paused = True
        self._pause_start = time.perf_counter()
        self._pause_snapshot = self.screen.copy()
        self.pause_screen = PauseScreen(self.screen)
        pygame.mixer.music.pause()

    def _exit_pause(self):
        pause_elapsed = time.perf_counter() - self._pause_start
        self.pause_time_accumulated += pause_elapsed
        self.rhythm.start_time += pause_elapsed
        self.paused = False
        self.pause_screen = None
        pygame.mixer.music.unpause()

    def _update_paused(self, *_):
        self.screen.blit(self._pause_snapshot, (0, 0))

        mouse_pos = pygame.mouse.get_pos()
        mouse_clicked = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._exit_pause()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_clicked = True

        if self.pause_screen is not None:
            action = self.pause_screen.update(mouse_pos, mouse_clicked)
            self.pause_screen.draw(time.time())
        else:
            action = None

        if action == "resume":
            self._exit_pause()
        elif action == "menu":
            self._exit_to_menu = True
            self.running = False

    def _find_drop_note_indices(self) -> dict[int, int]:
        """Find beatmap note indices closest to each drop timestamp."""
        if not self.drop_events or not self.rhythm.beat_map:
            return {}

        drop_to_note: dict[int, int] = {}

        for drop_idx, drop in enumerate(self.drop_events):
            drop_time = drop.timestamp + self.rhythm.lead_in
            best_note_idx = -1
            best_diff = float('inf')

            for i, event in enumerate(self.rhythm.beat_map):
                if event.is_rest or not event.char:
                    continue

                diff = abs(event.timestamp - drop_time)
                if diff < best_diff:
                    best_diff = diff
                    best_note_idx = i

            if best_note_idx >= 0:
                drop_to_note[drop_idx] = best_note_idx

        return drop_to_note

    def update(self, dt: float) -> None:
        self.screen.fill((0, 0, 0))

        current_time = time.perf_counter() - self.rhythm.start_time

        self.update_dynamic_scroll_speed(current_time)
        self.update_bounce_state(current_time)
        self.update_cat_position(current_time, dt)
        self.update_timeline_animation(dt)

        self.update_shockwaves(dt)
        self.update_hold_particles(dt)
        self.update_hit_bursts(dt)
        self.update_hitmarker_glow(dt)

        self.update_cat_animation()
        hurt_surf = self.update_hurt_animation(dt)
        if self._bop_surf is not None:
            self.screen.blit(self._bop_surf, (int(self.cat_current_x), 520))
        if hurt_surf is not None:
            self.screen.blit(hurt_surf, (int(self.cat_current_x), 520))

        events = pygame.event.get()
        mouse_pos = pygame.mouse.get_pos()
        mouse_clicked = False
        pause_requested = False
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pause_requested = True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_clicked = True

        self.pause_button.check_hover(mouse_pos)
        if self.pause_button.check_click(mouse_pos, mouse_clicked):
            pause_requested = True

        self.input.update(events=events)
        self.rhythm.update()

        # ── end-of-song outro deceleration ───────────────────────────────
        song_time_now = current_time - self.rhythm.lead_in
        _trigger_outro = (self.rhythm.is_finished()
                          or song_time_now >= self._silence_start)
        if _trigger_outro:
            if not self._outro_active:
                self._outro_active     = True
                self._outro_start_time = current_time
                self._outro_start_spd  = self.scroll_speed
            outro_elapsed = current_time - self._outro_start_time
            t    = min(1.0, outro_elapsed / self._outro_dur)
            ease = 1.0 - (1.0 - t) ** 3
            _min_spd = self._outro_start_spd * 0.15
            self.scroll_speed = max(_min_spd, self._outro_start_spd * (1.0 - ease * 0.85))
            if outro_elapsed >= self._outro_dur:
                self.show_message("Congratulations!", 5)
                self._exit_to_menu = True
                self.running = False
                return
            self.render_timeline()
            return

        # ── climax screen-shake beat triggers ────────────────────────────────
        while (self._climax_shake_idx < len(self._climax_shake_beats)
               and song_time_now >= self._climax_shake_beats[self._climax_shake_idx][0]):
            _, _intensity = self._climax_shake_beats[self._climax_shake_idx]
            self._trigger_screen_shake(_intensity)
            self._climax_shake_idx += 1

        current_char_idx = self.rhythm.char_event_idx

        if current_char_idx != self.last_char_idx:
            if not self.used_current_char and self.last_char_idx != -1:
                _prev = self.rhythm.beat_map[self.last_char_idx] if self.last_char_idx < len(self.rhythm.beat_map) else None
                if _prev and not _prev.is_rest and _prev.char:
                    self.misses += 1
                    self.show_message("Missed!", 1)
                    self.trigger_hurt()

            self.used_current_char = False
            self.last_char_idx = current_char_idx

        if self.input.typed_chars:
            for key in self.input.typed_chars:
                if self.used_current_char:
                    continue

                expected = self.rhythm.current_expected_char()
                if expected is None:
                    break

                result = self.rhythm.check_input(key)

                if result['hit']:
                    judgment = result['judgment']
                    combo = result['combo']

                    self.check_drop_note_hit(current_char_idx)

                    _hx, _hy = int(self.hit_marker_current_x), 380
                    if judgment != 'hold_started':
                        self.trigger_hit_ripple(_hx, _hy)
                    self._spawn_hit_particles(_hx, _hy)

                    if judgment == 'hold_started':
                        self.show_message("HOLD...", 0.5)
                    elif judgment == 'perfect':
                        self._glow_press_t = 0.0
                        self.show_message(f"PERFECT! ×{combo}", 0.8)
                    elif judgment == 'good':
                        self._glow_press_t = 0.0
                        self.show_message(f"Good ×{combo}", 0.8)
                    elif judgment == 'ok':
                        self._glow_press_t = 0.0
                        self.show_message(f"OK ×{combo}", 0.8)

                    self.score = self.rhythm.get_score()
                    self.used_current_char = True
                else:
                    judgment = result['judgment']
                    if judgment == 'wrong':
                        self.show_message("Wrong Key!", 0.8)
                    else:
                        self.show_message("Miss!", 0.8)
                    self.trigger_hurt()

                    self._timeline_flash = 1.0
                    self._timeline_shake_offset = 6.0

                    self.misses = self.rhythm.miss_count
                    self.used_current_char = True

        if self.input.released_chars:
            for rel_char in self.input.released_chars:
                hold_result = self.rhythm.on_key_release(rel_char)
                if hold_result:
                    if hold_result['hit']:
                        j = hold_result['judgment']
                        combo = hold_result['combo']
                        if 'perfect' in j:
                            self.show_message(f"HOLD PERFECT! ×{combo}", 1.0)
                        elif 'good' in j:
                            self.show_message(f"HOLD Good ×{combo}", 1.0)
                        else:
                            self.show_message(f"HOLD OK ×{combo}", 1.0)
                        self.trigger_hit_ripple(int(self.hit_marker_current_x), 380)
                        self.score = self.rhythm.get_score()
                    else:
                        self.show_message("Hold broken!", 0.8)
                        self.trigger_hurt()
                        self._timeline_flash = 1.0
                        self._timeline_shake_offset = 6.0
                        self.misses = self.rhythm.miss_count

        self.render_timeline()

        # ----- SCORE / MISSES
        stats = self.rhythm.get_stats()
        current_score = stats['score']

        sw, sh = self.screen.get_size()
        margin_x, margin_y = 20, 20

        if current_score > self._last_score:
            delta = current_score - self._last_score
            ref_h = self._score_font.get_height()
            self._score_popups.append({
                "delta": delta,
                "y": float(sh - margin_y - ref_h - 8),
                "alpha": 255.0,
            })
        self._last_score = current_score

        for p in self._score_popups:
            surf = self._popup_font.render(f"+{p['delta']}", True, (255, 220, 80))
            surf.set_alpha(int(p["alpha"]))
            self.screen.blit(surf, surf.get_rect(bottomright=(sw - margin_x, int(p["y"]))))
            p["y"]     -= 0.9
            p["alpha"] -= 4.5
        self._score_popups = [p for p in self._score_popups if p["alpha"] > 0]

        score_text = self._score_font.render(f"{current_score}", True, (255, 255, 255))
        self.screen.blit(score_text, score_text.get_rect(bottomright=(sw - margin_x, sh - margin_y)))

        self.pause_button.draw(self.screen, time.time())

        if pause_requested:
            self._enter_pause()
            return

        # ── apply screen shake (rotation with per-frame roughness noise) ────────
        self.update_screen_shake(dt)
        if abs(self._shake_x) > 0.05:
            import random as _rnd
            angle   = self._shake_x + _rnd.uniform(-0.18, 0.18)
            _snap   = self.screen.copy()
            rotated = pygame.transform.rotate(_snap, angle)
            self.screen.fill((0, 0, 0))
            self.screen.blit(rotated, rotated.get_rect(center=self.screen.get_rect().center))
