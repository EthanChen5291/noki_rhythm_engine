import pygame
import sys
import time
import os
import math

_FONT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets", "images", "fonts", "tacobae-font", "Tacobae-pge2K.otf",
)

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
)
from . import models as M
from .menu import PauseScreen, Button
from dataclasses import dataclass

pygame.init()

@dataclass
class BounceEvent:
    time: float          # song-time of the obstacle
    section_start: float
    section_end: float

class Game:
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
        self._score_popups: list[dict] = []  # each: {delta, y, alpha}
        self._score_font = pygame.font.Font(_FONT, 56)
        self._popup_font = pygame.font.Font(_FONT, 38)
        
        self.message = None
        self.message_duration = 0.0

        self.message = None
        self.message_duration = 0.0

        # word transition animation
        self._last_displayed_word = None
        self._previous_word = None
        self._word_transition_start = 0.0

        # --- load quick assets first (cat frames, timeline, spinner petals)
        self.level = level
        abs_song_path = C._to_abs_path(level.song_path)
        if abs_song_path is None:
            raise ValueError(f"Invalid song path: {level.song_path}")
        self.song_path = abs_song_path

        assets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'images')
        # ── noki_bop: pre-decode all frames into pygame surfaces ─────────
        # Done before the heavy worker thread so frames are ready instantly.
        import cv2 as _cv2
        _bop_path = os.path.join(assets_path, "noki_bop.mov")
        _bop_target_h = 300
        self._bop_frames: list[pygame.Surface] = []
        self._bop_fps    = 30.0
        # noki_bop native BPM: one L/R cycle = 2 beats at 100 BPM = 1.2 s
        self._bop_native_bpm = 100.0
        self._bop_surf   = None

        _pre_cap = _cv2.VideoCapture(_bop_path)
        if _pre_cap.isOpened():
            _fps_raw = _pre_cap.get(_cv2.CAP_PROP_FPS)
            if _fps_raw > 0:
                self._bop_fps = _fps_raw
            while True:
                _ret, _frm = _pre_cap.read()
                if not _ret:
                    break
                _rgb = _cv2.cvtColor(_frm, _cv2.COLOR_BGR2RGB)
                _fh, _fw = _rgb.shape[:2]
                _fw_scaled = int(_fw * _bop_target_h / _fh)
                _s = pygame.surfarray.make_surface(_rgb.transpose(1, 0, 2))
                _s = pygame.transform.smoothscale(_s, (_fw_scaled, _bop_target_h))
                self._bop_frames.append(_s)
        _pre_cap.release()

        self.cat_frame = None  # kept for draw compatibility

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

        # Petal spinner images
        _psz   = 40
        _p1    = pygame.transform.smoothscale(
            pygame.image.load(os.path.join(assets_path, 'petal1.png')).convert_alpha(),
            (_psz, _psz))
        _p2    = pygame.transform.smoothscale(
            pygame.image.load(os.path.join(assets_path, 'petal2.png')).convert_alpha(),
            (_psz, _psz))
        _cx, _cy   = screen_width // 2, screen_height // 2
        _radius    = 50

        # --- run all heavy analysis + beatmap generation in a background thread
        # so we can animate the spinner on the main thread
        import threading as _threading
        _result: dict  = {}
        _errors: list  = []

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
                _result.update(song=song, beat_duration=bdur, pace_profile=pace,
                               dual_side_sections=dual_secs, difficulty_profile=diff_prof,
                               rhythm=rhythm, drop_events=drops, scroll_tiers=tiers,
                               energy_shifts=shifts)
            except Exception as exc:
                _errors.append(exc)

        _thread = _threading.Thread(target=_worker, daemon=True)
        _thread.start()

        # --- petal spinner loop (runs until thread finishes) ---
        #
        # Two independent petals with different periods — not in sync.
        # Each maps t_norm [0,1) → angle with ease-in fall / ease-out rise.
        # Petal 2 starts 3π/4 ahead in phase and runs at 65 % of petal 1's period.

        _P1 = (60.0 / 45.0) / 0.7   # petal 1: 30% slower
        _P2 = _P1 * 0.65             # petal 2: noticeably faster
        # 3π/4 out of 2π = 3/8 of a cycle → time offset for petal 2
        _P2_OFFSET = _P2 * 0.375

        _spin_start = time.time()
        _spin_clock = pygame.time.Clock()

        _SHADOW_STEPS  = 3
        _SHADOW_ALPHAS = [120, 60, 25]   # most-recent ghost → oldest

        def _petal_angle(t_norm: float) -> float:
            """Non-uniform orbital angle: ease-in fall, quartic ease-out rise (teeters at top)."""
            if t_norm < 0.5:
                p    = t_norm / 0.5
                ease = p * p                           # quadratic ease-in: accelerates into fall
                return math.pi / 2 - math.pi * ease
            else:
                p    = (t_norm - 0.5) / 0.5
                ease = 1.0 - (1.0 - p) ** 4           # quartic ease-out: rises fast, crawls to top
                return -math.pi / 2 - math.pi * ease

        # Each ghost lags behind by _LAG_TIME * step seconds in actual time.
        # We evaluate _petal_angle at those earlier t_norms so the ghost is always
        # where the petal *was* — no direction arithmetic, no wraparound bugs.
        _LAG_TIME = 0.045   # seconds each consecutive ghost lags behind

        def _draw_petal_with_shadow(pimg, elapsed, period, offset):
            t_now  = ((elapsed + offset) % period) / period
            a_now  = _petal_angle(t_now)
            # draw ghosts from oldest → newest so newer ones paint over older
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
            # main petal
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
        self.song              = _result['song']
        self.beat_duration     = _result['beat_duration']
        self.pace_profile      = _result['pace_profile']
        self.dual_side_sections = _result['dual_side_sections']
        self.difficulty_profile = _result['difficulty_profile']
        self.rhythm            = _result['rhythm']
        self.drop_events       = _result['drop_events']
        self.scroll_tiers      = _result['scroll_tiers']
        self.energy_shifts     = _result['energy_shifts']

        self.input = Input()

        self.shockwaves: list[M.Shockwave] = []
        self.drops_triggered: set[int] = set()
        self.drop_note_indices = self._find_drop_note_indices()

        # --- scroll speed (derived from pace profile) ---
        self.base_scroll_speed = C.SCROLL_SPEED * self.difficulty_profile.scroll_scale
        self.pace_bias         = 0.85 + self.pace_profile.pace_score * 1.3
        self.scroll_speed      = self.base_scroll_speed * self.pace_bias

        # --- bounce mode
        self.bounce_events: list[BounceEvent] = []
        self.bounce_active: bool = False
        self.bounce_reversed: bool = False
        self._next_bounce_idx: int = 0
        self._build_bounce_events()
        self._apply_bounce_grace_periods()

        # --- cat position for dual-side mode animation
        self.cat_base_x = 150 - int(screen_width * 0.02)  # normal left position
        self.cat_center_x = screen_width // 2 - 115 - int(screen_width * 0.065)  # center position (accounting for cat width)
        self.cat_current_x = float(self.cat_base_x)
        self.cat_velocity = 0.0  # for momentum animation
        self.dual_side_active = False
        self.dual_side_visuals_active = False

        # --- timeline animation for dual-side mode
        self.timeline_normal_start = 300
        self.timeline_normal_end = 1500
        self.timeline_dual_start = 0
        self.timeline_dual_end = screen_width
        self.timeline_current_start = float(self.timeline_normal_start)
        self.timeline_current_end = float(self.timeline_normal_end)
        self.timeline_start_velocity = 0.0
        self.timeline_end_velocity = 0.0
        # Hit marker positions
        self.hit_marker_normal_x = C.HIT_X - C.HIT_MARKER_X_OFFSET
        self.hit_marker_dual_x = screen_width // 2
        self.hit_marker_current_x = float(self.hit_marker_normal_x)
        self.hit_marker_velocity = 0.0

        # Word y-position animation for dual-side mode
        self.word_normal_y = 180  # Normal position (top area)
        self.word_dual_y = 480  # Above the cat during dual mode
        self.word_current_y = float(self.word_normal_y)
        self.word_y_velocity = 0.0

        # --- track missed notes for shockwave effect in dual mode
        self.missed_note_shockwaves: set[int] = set()  # indices of notes that triggered miss shockwave
        self._last_dual_end_time: float = -10.0  # song_time when dual mode last ended

        # --- timeline miss flash (red flash + tiny shake on wrong/miss)
        self._timeline_flash: float = 0.0  # 1.0 → 0.0 decay
        self._timeline_shake_offset: float = 0.0

        # --- pause state
        self.paused = False
        self.pause_screen: PauseScreen | None = None
        self.pause_time_accumulated = 0.0  # total time spent paused
        self._pause_start = 0.0
        pause_font = pygame.font.Font(_FONT, 36)
        self.pause_button = Button(
            (screen_width - 100, 20, 80, 40),
            "II",
            pause_font,
            base_color=(120, 120, 120),
            hover_color=(255, 255, 255),
        )

        # --- play music
        pygame.mixer.init()
        pygame.mixer.music.load(self.song_path)
        pygame.mixer.music.play()

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
        # shift rhythm start time forward so game time is unaffected
        self.rhythm.start_time += pause_elapsed
        self.paused = False
        self.pause_screen = None
        pygame.mixer.music.unpause()

    def _update_paused(self, *_):
        # blit the frozen snapshot captured when pause was entered
        self.screen.blit(self._pause_snapshot, (0, 0))

        # draw pause overlay
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

    def update_cat_animation(self):
        """Select noki_bop frame, synced to song beat_times.
        Uses elapsed time from level start during lead-in so animation never freezes."""
        if not self._bop_frames:
            return

        n = len(self._bop_frames)
        elapsed   = time.perf_counter() - self.rhythm.start_time
        song_time = elapsed - self.rhythm.lead_in
        beat_times = self.song.beat_times

        if beat_times and len(beat_times) >= 2 and song_time >= beat_times[0]:
            # inside the song — follow actual beat_times for accurate sync
            current_beat_idx = 0
            for i, bt in enumerate(beat_times):
                if bt <= song_time:
                    current_beat_idx = i
                else:
                    break
            if current_beat_idx < len(beat_times) - 1:
                beat_start = beat_times[current_beat_idx]
                beat_end   = beat_times[current_beat_idx + 1]
                phase = (song_time - beat_start) / (beat_end - beat_start)
            else:
                phase = 0.0
            normalized = ((current_beat_idx % 2) + phase) / 2.0
        else:
            # lead-in or no beat_times — run at song BPM from level start
            beat_dur   = 60.0 / self.song.bpm
            normalized = (elapsed / beat_dur % 2.0) / 2.0

        frame_idx = int(normalized * n) % n
        self._bop_surf = self._bop_frames[frame_idx]

    def _find_drop_note_indices(self) -> dict[int, int]:
        """Find beatmap note indices closest to each drop timestamp.
        Returns dict mapping drop_index -> note_index."""
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

    def trigger_shockwave(self):
        """Spawn multiple expanding shockwave rings and boost screen shake"""
        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2

        num_rings = 5
        for i in range(num_rings):
            initial_radius = i * 30
            shockwave = M.Shockwave(
                center_x=center_x,
                center_y=center_y,
                radius=initial_radius,
                max_radius=800,
                alpha=150,
                thickness=4,
                speed=400 + i * 50
            )
            self.shockwaves.append(shockwave)

    def trigger_hit_ripple(self, x: int, y: int):
        """Spawn three small, transparent ripple rings from varied offset centers"""
        import random
        offsets = [
            (random.randint(-25, 25), random.randint(-15, 15)),
            (random.randint(-30, 30), random.randint(-18, 18)),
            (random.randint(-22, 22), random.randint(-12, 12)),
        ]
        configs = [
            # (start_radius, max_radius, alpha, thickness, speed)
            (0,  35, 120, 2, 90),
            (3,  45, 90,  1, 130),
            (6,  55, 70,  1, 170),
        ]
        for (ox, oy), (start_r, max_r, alpha, thick, spd) in zip(offsets, configs):
            self.shockwaves.append(M.Shockwave(
                center_x=x + ox,
                center_y=y + oy,
                radius=start_r,
                max_radius=max_r,
                alpha=alpha,
                thickness=thick,
                speed=spd,
            ))

    def trigger_miss_shockwave(self, x: int, y: int):
        """Spawn a small shockwave at a missed note position"""
        shockwave = M.Shockwave(
            center_x=x,
            center_y=y,
            radius=5,
            max_radius=40,
            alpha=200,
            thickness=2,
            speed=150
        )
        self.shockwaves.append(shockwave)

    def check_drop_note_hit(self, hit_note_idx: int):
        """Check if the hit note is any drop note and trigger shockwave"""
        for drop_idx, note_idx in self.drop_note_indices.items():
            if drop_idx not in self.drops_triggered and hit_note_idx == note_idx:
                self.trigger_shockwave()
                self.drops_triggered.add(drop_idx)

    def update_shockwaves(self, dt: float):
        """Update and render active shockwaves"""
        surviving = []
        for wave in self.shockwaves:
            if wave.update(dt):
                surviving.append(wave)
                self.render_shockwave(wave)

        self.shockwaves = surviving

    def update_dynamic_scroll_speed(self, current_time: float):
        """Smoothly interpolate scroll speed based on intensity tiers + energy shifts"""
        song_time = current_time - self.rhythm.lead_in

        # Start with base speed, then apply intensity tier
        tier_mult = 1.0
        for t_start, t_end, mult in self.scroll_tiers:
            if t_start <= song_time < t_end:
                tier_mult = mult
                break

        target_speed = self.base_scroll_speed * self.pace_bias * tier_mult

        active_shift = None
        for shift in self.energy_shifts:
            if shift.start_time <= song_time < shift.end_time:
                active_shift = shift
                break

        if active_shift:
            if self.dual_side_active:
                # Less dampening for fast songs so climaxes still hit
                damp_factor = 0.3 if self.pace_profile.pace_score < 0.5 else 0.7
                dampened_modifier = 1.0 + (active_shift.scroll_modifier - 1.0) * damp_factor
                target_speed *= dampened_modifier
            else:
                target_speed *= active_shift.scroll_modifier

        if self.dual_side_active:
            # Less speed reduction for fast songs
            dual_slow = 0.7 if self.pace_profile.pace_score < 0.5 else 0.82
            target_speed *= dual_slow

        if target_speed > self.scroll_speed:
            lerp_factor = 0.06
        else:
            lerp_factor = 0.04

        self.scroll_speed += (target_speed - self.scroll_speed) * lerp_factor

    def _build_bounce_events(self):
        """Build bounce events from energy shifts with positive energy_delta."""
        dual_ranges = [(ds.start_time, ds.end_time) for ds in self.dual_side_sections]

        for shift in self.energy_shifts:
            if shift.energy_delta <= C.BOUNCE_THRESHOLD:
                continue

            overlaps = False
            for ds_start, ds_end in dual_ranges:
                if shift.start_time < ds_end and shift.end_time > ds_start:
                    overlaps = True
                    break
            if overlaps:
                continue

            measure_beats = []
            for i, bt in enumerate(self.song.beat_times):
                if bt < shift.start_time:
                    continue
                if bt >= shift.end_time:
                    break
                if i % 8 == 0:
                    measure_beats.append(bt)

            for bt in measure_beats:
                self.bounce_events.append(BounceEvent(
                    time=bt,
                    section_start=shift.start_time,
                    section_end=shift.end_time,
                ))

        self.bounce_events.sort(key=lambda e: e.time)

    def _apply_bounce_grace_periods(self):
        """Mark beatmap notes within 2 beats of each bounce event as rests.
        If any char of a word falls in the grace window, blank the entire word
        so the player never gets a partial word with some chars active and some rests.
        Does not blank notes inside dual-side sections."""
        if not self.bounce_events:
            return
        grace_beats = 2
        grace_duration = self.beat_duration * grace_beats
        lead_in = self.rhythm.lead_in
        dual_ranges = [(ds.start_time, ds.end_time) for ds in self.dual_side_sections]

        # Collect (word_text, section) keys that have at least one char in any grace window
        tainted_words: set[tuple[str, int]] = set()
        for event in self.bounce_events:
            bounce_time = event.time + lead_in
            for note in self.rhythm.beat_map:
                if note.is_rest or not note.char:
                    continue
                note_song_time = note.timestamp - lead_in
                in_dual = any(ds <= note_song_time < de for ds, de in dual_ranges)
                if in_dual:
                    continue
                dt = note.timestamp - bounce_time
                if -self.beat_duration <= dt <= grace_duration:
                    tainted_words.add((note.word_text, note.section))

        # Blank all chars that belong to any tainted word
        for note in self.rhythm.beat_map:
            if note.is_rest or not note.char:
                continue
            if (note.word_text, note.section) in tainted_words:
                note.is_rest = True
                note.char = ""

    def update_bounce_state(self, current_time: float):
        """Update bounce mode: toggle direction when crossing bounce obstacles."""
        song_time = current_time - self.rhythm.lead_in

        was_active = self.bounce_active
        self.bounce_active = False

        if not self.dual_side_active:
            for evt in self.bounce_events:
                if evt.section_start <= song_time < evt.section_end:
                    self.bounce_active = True
                    break

        while (self._next_bounce_idx < len(self.bounce_events)
               and self.bounce_events[self._next_bounce_idx].time <= song_time):
            if not self.dual_side_active:
                self.bounce_reversed = not self.bounce_reversed
            self._next_bounce_idx += 1

        if was_active and not self.bounce_active:
            self.bounce_reversed = False

    def update_cat_position(self, current_time: float, dt: float):
        """
        Update cat position with momentum-style animation for dual-side mode.
        Quick acceleration when entering, slow deceleration to final position.
        """
        song_time = current_time - self.rhythm.lead_in

        visual_exit_delay = self.beat_duration * 1

        was_dual_active = self.dual_side_active
        self.dual_side_active = False
        self.dual_side_visuals_active = False

        for dual_sec in self.dual_side_sections:
            if dual_sec.start_time <= song_time < dual_sec.end_time:
                self.dual_side_active = True
                self.dual_side_visuals_active = True
                break
            elif dual_sec.end_time <= song_time < dual_sec.end_time + visual_exit_delay:
                self.dual_side_visuals_active = True
                break

        # Keep dual mode active if current note is a dual-mode note (from_left)
        if not self.dual_side_active and self.rhythm.char_event_idx < len(self.rhythm.beat_map):
            current_evt = self.rhythm.beat_map[self.rhythm.char_event_idx]
            if current_evt.from_left:
                self.dual_side_active = True
                self.dual_side_visuals_active = True

        # Track when dual mode ends for note teleport suppression
        if was_dual_active and not self.dual_side_active:
            self._last_dual_end_time = song_time

        if self.dual_side_visuals_active:
            target_x = self.cat_center_x
        else:
            target_x = self.cat_base_x

        distance = target_x - self.cat_current_x

        if self.dual_side_visuals_active:
            if abs(distance) > 5:
                spring_strength = 8.0
                damping = 4.0
            else:
                spring_strength = 5.0
                damping = 6.0
        else:
            if abs(distance) > 5:
                spring_strength = 5.0
                damping = 5.0
            else:
                spring_strength = 4.0
                damping = 7.0

        acceleration = spring_strength * distance - damping * self.cat_velocity
        self.cat_velocity += acceleration * dt
        self.cat_current_x += self.cat_velocity * dt

        if self.dual_side_visuals_active:
            self.cat_current_x = max(self.cat_base_x, min(self.cat_current_x, self.cat_center_x + 50))
        else:
            self.cat_current_x = max(self.cat_base_x - 50, min(self.cat_current_x, self.cat_center_x))

    def update_timeline_animation(self, dt: float):
        """
        Animate timeline expansion/contraction for dual-side mode.
        Uses spring physics for momentum feel.
        """
        if self.dual_side_visuals_active:
            target_start = self.timeline_dual_start
            target_end = self.timeline_dual_end
            target_hit = self.hit_marker_dual_x
            target_word_y = self.word_dual_y
        else:
            target_start = self.timeline_normal_start
            target_end = self.timeline_normal_end
            if self.bounce_active:
                target_hit = self.hit_marker_normal_x
            else:
                grace = (C.GRACE * self.scroll_speed)
                target_hit = self.hit_marker_normal_x - grace/6
            target_word_y = self.word_normal_y

        if not hasattr(self, '_timeline_initialized'):
            self.timeline_current_start = target_start
            self.timeline_current_end = target_end
            self.hit_marker_current_x = target_hit
            self.word_current_y = target_word_y
            self._timeline_initialized = True
            return

        if self.dual_side_visuals_active:
            spring_strength = 12.0
            damping = 5.0
        else:
            spring_strength = 6.0
            damping = 7.0

        dist_start = target_start - self.timeline_current_start
        accel_start = spring_strength * dist_start - damping * self.timeline_start_velocity
        self.timeline_start_velocity += accel_start * dt
        self.timeline_current_start += self.timeline_start_velocity * dt

        dist_end = target_end - self.timeline_current_end
        accel_end = spring_strength * dist_end - damping * self.timeline_end_velocity
        self.timeline_end_velocity += accel_end * dt
        self.timeline_current_end += self.timeline_end_velocity * dt

        dist_hit = target_hit - self.hit_marker_current_x
        accel_hit = spring_strength * dist_hit - damping * self.hit_marker_velocity
        self.hit_marker_velocity += accel_hit * dt
        self.hit_marker_current_x += self.hit_marker_velocity * dt

        dist_word_y = target_word_y - self.word_current_y
        accel_word_y = spring_strength * dist_word_y - damping * self.word_y_velocity
        self.word_y_velocity += accel_word_y * dt
        self.word_current_y += self.word_y_velocity * dt

    def draw_dual_side_marker(self, x: int, timeline_y: int):
        """Draw a dual-side mode activation marker (two arrows pointing inward)"""
        arrow_height = 60
        arrow_width = 12

        left_color = (100, 200, 255)
        right_color = (255, 200, 100)

        top_y = timeline_y - arrow_height // 2
        bottom_y = timeline_y + arrow_height // 2
        center_y = timeline_y

        left_x = x - 15
        left_points = [
            (left_x + arrow_width, center_y),
            (left_x, top_y),
            (left_x, bottom_y),
        ]
        pygame.draw.polygon(self.screen, left_color, left_points)
        pygame.draw.polygon(self.screen, (255, 255, 255), left_points, 2)

        right_x = x + 15
        right_points = [
            (right_x - arrow_width, center_y),
            (right_x, top_y),
            (right_x, bottom_y),
        ]
        pygame.draw.polygon(self.screen, right_color, right_points)
        pygame.draw.polygon(self.screen, (255, 255, 255), right_points, 2)

    def draw_speed_arrow(self, x: int, timeline_y: int, timeline_height: int, speed_up: bool):
        """Draw a speed change arrow spanning the full measure line"""
        if speed_up:
            arrow_color = (0, 200, 255)
        else:
            arrow_color = (200, 150, 100)

        arrow_height = timeline_height
        arrow_width = 24

        top_y = timeline_y - arrow_height // 2
        bottom_y = timeline_y + arrow_height // 2
        center_y = timeline_y

        if speed_up:
            for offset in [-8, 8]:
                points = [
                    (x - arrow_width // 2 + offset, top_y),
                    (x + arrow_width // 2 + offset, center_y),
                    (x - arrow_width // 2 + offset, bottom_y),
                ]
                pygame.draw.polygon(self.screen, arrow_color, points)
                pygame.draw.polygon(self.screen, (255, 255, 255), points, 2)
        else:
            for offset in [-8, 8]:
                points = [
                    (x + arrow_width // 2 + offset, top_y),
                    (x - arrow_width // 2 + offset, center_y),
                    (x + arrow_width // 2 + offset, bottom_y),
                ]
                pygame.draw.polygon(self.screen, arrow_color, points)
                pygame.draw.polygon(self.screen, (200, 220, 255), points, 2)

    def render_shockwave(self, wave: M.Shockwave):
        """Render a single shockwave ring with realistic gray coloring"""
        if wave.alpha <= 0 or wave.radius <= 0:
            return

        diameter = int(wave.radius * 2) + wave.thickness * 2
        if diameter <= 0:
            return

        surface = pygame.Surface((diameter, diameter), pygame.SRCALPHA)

        gray_value = 180
        color = (gray_value, gray_value, gray_value, wave.alpha)

        center = diameter // 2
        if wave.thickness > 0 and wave.radius > 0:
            pygame.draw.circle(
                surface,
                color,
                (center, center),
                int(wave.radius),
                wave.thickness
            )

        blit_x = int(wave.center_x - center)
        blit_y = int(wave.center_y - center)
        self.screen.blit(surface, (blit_x, blit_y))

    def update(self, dt: float) -> None:
        self.screen.fill((0, 0, 0))

        current_time = time.perf_counter() - self.rhythm.start_time

        self.update_dynamic_scroll_speed(current_time)
        self.update_bounce_state(current_time)
        self.update_cat_position(current_time, dt)
        self.update_timeline_animation(dt)

        self.update_shockwaves(dt)

        self.update_cat_animation()
        if self._bop_surf is not None:
            self.screen.blit(self._bop_surf, (int(self.cat_current_x), 520))
        
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
        
        if self.rhythm.is_finished():
            self.show_message("Congratulations!", 5)
            self._exit_to_menu = True
            self.running = False
            return
        
        current_char_idx = self.rhythm.char_event_idx
        
        if current_char_idx != self.last_char_idx:
            if not self.used_current_char and self.last_char_idx != -1:
                self.misses += 1
                self.show_message("Missed!", 1)
            
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

                    # Ripple effect at hit marker on correct press
                    self.trigger_hit_ripple(
                        int(self.hit_marker_current_x), 380
                    )

                    if judgment == 'perfect':
                        self.show_message(f"PERFECT! ×{combo}", 0.8)
                    elif judgment == 'good':
                        self.show_message(f"Good ×{combo}", 0.8)
                    elif judgment == 'ok':
                        self.show_message(f"OK ×{combo}", 0.8)

                    self.score = self.rhythm.get_score()
                    self.used_current_char = True
                else:
                    judgment = result['judgment']
                    if judgment == 'wrong':
                        self.show_message("Wrong Key!", 0.8)
                    else:
                        self.show_message("Miss!", 0.8)

                    # Flash timeline red + tiny shake on miss/wrong
                    self._timeline_flash = 1.0
                    self._timeline_shake_offset = 6.0

                    self.misses = self.rhythm.miss_count
                    self.used_current_char = True

        self.render_timeline()
        
        # ----- SCORE / MISSES

        stats = self.rhythm.get_stats()
        current_score = stats['score']

        sw, sh = self.screen.get_size()
        margin_x, margin_y = 20, 20

        # Spawn a popup when score increases
        if current_score > self._last_score:
            delta = current_score - self._last_score
            ref_h = self._score_font.get_height()
            self._score_popups.append({
                "delta": delta,
                "y": float(sh - margin_y - ref_h - 8),
                "alpha": 255.0,
            })
        self._last_score = current_score

        # Draw and tick popups
        for p in self._score_popups:
            surf = self._popup_font.render(f"+{p['delta']}", True, (255, 220, 80))
            surf.set_alpha(int(p["alpha"]))
            self.screen.blit(surf, surf.get_rect(bottomright=(sw - margin_x, int(p["y"]))))
            p["y"]     -= 0.9
            p["alpha"] -= 4.5
        self._score_popups = [p for p in self._score_popups if p["alpha"] > 0]

        score_text = self._score_font.render(f"{current_score}", True, (255, 255, 255))
        self.screen.blit(score_text, score_text.get_rect(bottomright=(sw - margin_x, sh - margin_y)))

        # pause button
        self.pause_button.draw(self.screen, time.time())

        # Enter pause after all rendering so the snapshot includes the full frame
        if pause_requested:
            self._enter_pause()
            return


    def get_next_word(self) -> str | None:
        """Get the next word that will be typed after current word completes (display chars only)"""
        if not self.rhythm.beat_map:
            return None

        next_word_text = None
        for i in range(self.rhythm.char_event_idx, len(self.rhythm.beat_map)):
            event = self.rhythm.beat_map[i]
            if event.word_text and event.char_idx == 0 and not event.is_rest:
                if event.word_text != self.rhythm.current_expected_word():
                    next_word_text = event.word_text
                    break

        if next_word_text is None:
            return None

        # Find the highest char_idx mapped for this next word
        max_char_idx = -1
        for i in range(self.rhythm.char_event_idx, len(self.rhythm.beat_map)):
            ev = self.rhythm.beat_map[i]
            if ev.is_rest or ev.word_text != next_word_text:
                continue
            if ev.char_idx > max_char_idx:
                max_char_idx = ev.char_idx

        if max_char_idx < 0:
            return next_word_text
        return next_word_text[:max_char_idx + 1]

    def draw_word_animated(
        self,
        word: str,
        position: str,  # 'left', 'center', 'right'
        transition_progress: float,
        is_current: bool,
        fading_out: bool = False,
        adjacent_word_width: int = 0,
        y_offset: float = 0
    ):
        """Draw a word with 3D carousel rotation animation"""
        if not word:
            return

        base_char_spacing = 60

        if position == 'right':
            char_spacing = base_char_spacing * 0.7
        elif position == 'left':
            char_spacing = base_char_spacing * 0.7
        else:
            char_spacing = base_char_spacing

        total_width = len(word) * char_spacing

        radius = 350  # radius of rotation circle
        center_offset = base_char_spacing / 2
        center_x = self.screen.get_width() // 2 + center_offset  # center of screen
        center_y = 180 + y_offset  # vertical position (like in 3d space)
        
        base_spacing = 100
        
        if position == 'center':
            target_angle = 0  # front center
            target_scale = 1.0
            target_alpha = 255
            target_color = (255, 255, 255)
            target_char_spacing = base_char_spacing
        elif position == 'right':
            # adjust angle based off combined word widths
            width_factor = (total_width + adjacent_word_width) / 2
            dynamic_spacing = base_spacing + width_factor * 0.3
            target_angle = dynamic_spacing / radius
            target_scale = 0.75
            target_alpha = 180
            target_color = (150, 150, 150)
            target_char_spacing = base_char_spacing * 0.7
        else:
            width_factor = (total_width + adjacent_word_width) / 2
            dynamic_spacing = base_spacing + width_factor * 0.3
            target_angle = -dynamic_spacing / radius
            target_scale = 0.75
            target_alpha = int(180 * (1 - transition_progress)) if fading_out else 180
            target_color = (150, 150, 150)
            target_char_spacing = base_char_spacing * 0.7
            
        if position == 'center' and transition_progress < 1.0:
            width_factor = (total_width + adjacent_word_width) / 2
            dynamic_spacing = base_spacing + width_factor * 0.3
            start_angle = dynamic_spacing / radius
            current_angle = start_angle + (target_angle - start_angle) * transition_progress
            
            current_scale = 0.75 + (target_scale - 0.75) * transition_progress
            current_alpha = int(180 + (target_alpha - 180) * transition_progress)
            
            gray_amount = int(150 + (255 - 150) * transition_progress)
            current_color = (gray_amount, gray_amount, gray_amount)

            start_char_spacing = base_char_spacing * 0.7
            current_char_spacing = start_char_spacing + (target_char_spacing - start_char_spacing) * transition_progress
        else:
            current_angle = target_angle
            current_scale = target_scale
            current_alpha = target_alpha
            current_color = target_color
            current_char_spacing = char_spacing
        
        x_offset = radius * math.sin(current_angle)
        z = radius * (1 - math.cos(current_angle))
        
        perspective_scale = 1.0 / (1.0 + z / 1000)
        final_scale = current_scale * perspective_scale
        final_alpha = int(current_alpha * perspective_scale)
        
        animated_total_width = len(word) * current_char_spacing * final_scale
    
        current_x = center_x + x_offset - animated_total_width / 2
        
        for i, char in enumerate(word):
            font_size = int(48 * final_scale)
            char_font = pygame.font.Font(_FONT, font_size)
            
            char_surface = char_font.render(char, True, current_color)
            char_surface.set_alpha(final_alpha)
            
            char_x = current_x + i * (current_char_spacing * final_scale)
            char_y = center_y
            
            self.screen.blit(char_surface, (int(char_x), int(char_y)))
            
            if position == 'center' and is_current and self.rhythm.char_event_idx < len(self.rhythm.beat_map):
                current_event = self.rhythm.beat_map[self.rhythm.char_event_idx]
                if (not current_event.is_rest
                        and current_event.word_text.startswith(word)
                        and current_event.char_idx == i):
                    underline_width = int(C.UNDERLINE_LEN * final_scale)
                    line_x = char_x - 10 * final_scale
                    line_y = char_y + 50
                    
                    pygame.draw.line(
                        self.screen,
                        (255, 255, 255),
                        (int(line_x), int(line_y)),
                        (int(line_x + underline_width), int(line_y)),
                        3
                    )

    def draw_background_word(self, word: str):
        """Draw the current word as a large, faded background element during dual-side mode"""
        if not word:
            return

        # Large font for background word
        font_size = 180
        bg_font = pygame.font.Font(_FONT, font_size)

        # Gray, semi-transparent color
        bg_color = (60, 60, 60)

        # Render each character with spacing
        char_spacing = 120
        total_width = len(word) * char_spacing
        start_x = (self.screen.get_width() - total_width) // 2
        center_y = self.screen.get_height() // 2 - 50  # Slightly above center

        for i, char in enumerate(word):
            char_surface = bg_font.render(char, True, bg_color)
            char_x = start_x + i * char_spacing
            char_rect = char_surface.get_rect(center=(char_x + char_spacing // 2, center_y))
            self.screen.blit(char_surface, char_rect)

    def draw_bounce_obstacle(self, x: int, timeline_y: int):
        """Draw a diamond-shaped bounce obstacle."""
        size = 12
        points = [
            (x, timeline_y - size),
            (x + size, timeline_y),
            (x, timeline_y + size),
            (x - size, timeline_y), 
        ]
        pygame.draw.polygon(self.screen, (255, 80, 200), points)
        pygame.draw.polygon(self.screen, (255, 255, 255), points, 2)

    # --- RENDER TIMELINE

    def render_timeline(self):
        current_time = time.perf_counter() - self.rhythm.start_time
        
        current_word = self.rhythm.current_display_word()
        next_word = self.get_next_word()
        
        char_spacing = 60
        current_word_width = len(current_word) * char_spacing if current_word else 0
        next_word_width = len(next_word) * char_spacing if next_word else 0
        
        if current_word != getattr(self, '_last_displayed_word', None):
            self._word_transition_start = current_time
            self._last_displayed_word = current_word
        
        transition_duration = 0.3  # secs
        if hasattr(self, '_word_transition_start'):
            transition_progress = min(1.0, (current_time - self._word_transition_start) / transition_duration)
        else:
            transition_progress = 1.0
        
        ease_progress = 1 - (1 - transition_progress) ** 3

        word_y_offset = self.word_current_y - self.word_normal_y

        if current_word:
            self.draw_word_animated(
                current_word,
                position='center',
                transition_progress=ease_progress,
                is_current=True,
                adjacent_word_width=next_word_width,
                y_offset=word_y_offset
            )

        if next_word:
            self.draw_word_animated(
                next_word,
                position='right',
                transition_progress=ease_progress,
                is_current=False,
                adjacent_word_width=current_word_width,
                y_offset=word_y_offset
            )

        if hasattr(self, '_previous_word') and self._previous_word is not None and transition_progress < 1.0:
            self.draw_word_animated(
                self._previous_word,
                position='left',
                transition_progress=ease_progress,
                is_current=False,
                fading_out=True,
                adjacent_word_width=current_word_width,
                y_offset=word_y_offset
            )

        if transition_progress >= 1.0:
            self._previous_word = current_word

        # --- draw timeline (using animated positions)
        timeline_y = 380
        # Apply miss shake offset
        if self._timeline_shake_offset > 0.3:
            timeline_y += int(self._timeline_shake_offset)
            self._timeline_shake_offset *= -0.5  # oscillate and decay
        else:
            self._timeline_shake_offset = 0.0

        timeline_start_x = int(self.timeline_current_start)
        timeline_end_x = int(self.timeline_current_end)
        hit_marker_x = self.hit_marker_current_x

        # Flash timeline red on miss, decay to white
        if self._timeline_flash > 0.01:
            r = int(255)
            g = int(255 * (1.0 - self._timeline_flash))
            b = int(255 * (1.0 - self._timeline_flash))
            timeline_color = (r, g, b)
            self._timeline_flash *= 0.85
        else:
            timeline_color = (255, 255, 255)
            self._timeline_flash = 0.0

        pygame.draw.line(self.screen, timeline_color,
                        (timeline_start_x, timeline_y),
                        (timeline_end_x, timeline_y), 6)

        # Draw visual hit marker at the fixed position (no bounce offset)
        _hm_rect = self.hitmarker_img.get_rect(
            center=(int(hit_marker_x), timeline_y)
        )
        self.screen.blit(self.hitmarker_img, _hm_rect)

        # --- beat grid lines (using beat times from librosa)
        beat_times = self.song.beat_times
        lead_in = self.rhythm.lead_in


        for i, beat_time in enumerate(beat_times):
            t = beat_time + lead_in
            time_until = t - current_time
            # Reverse grid direction during bounce mode
            if self.bounce_active and not self.dual_side_active and self.bounce_reversed:
                x = hit_marker_x - time_until * self.scroll_speed
            else:
                x = hit_marker_x + time_until * self.scroll_speed

            if timeline_start_x <= x <= timeline_end_x:
                if i % 4 == 0:
                    self.screen.blit(self._measureline_img,
                                     self._measureline_img.get_rect(center=(int(x), timeline_y)))
                else:
                    self.screen.blit(self._beatline_img,
                                     self._beatline_img.get_rect(center=(int(x), timeline_y)))

        # --- draw dual-side mode indicators
        if self.dual_side_visuals_active:
            arrow_size = 15
            arrow_y = timeline_y

            left_arrow_x = timeline_start_x + 30
            pygame.draw.polygon(
                self.screen,
                (100, 200, 255),
                [
                    (left_arrow_x, arrow_y),
                    (left_arrow_x - arrow_size, arrow_y - arrow_size // 2),
                    (left_arrow_x - arrow_size, arrow_y + arrow_size // 2),
                ]
            )

            right_arrow_x = timeline_end_x - 30
            pygame.draw.polygon(
                self.screen,
                (255, 200, 100),
                [
                    (right_arrow_x, arrow_y),
                    (right_arrow_x + arrow_size, arrow_y - arrow_size // 2),
                    (right_arrow_x + arrow_size, arrow_y + arrow_size // 2),
                ]
            )

        # --- draw dual-side section start markers (like speed arrows)
        for dual_sec in self.dual_side_sections:
            section_time = dual_sec.start_time + self.rhythm.lead_in
            time_until = section_time - current_time

            if -0.5 < time_until < 5.0:
                marker_x = hit_marker_x + time_until * self.scroll_speed

                if timeline_start_x <= marker_x <= timeline_end_x:
                    self.draw_dual_side_marker(int(marker_x), timeline_y)

        # --- draw speed change arrows at energy shift boundaries (render BEFORE notes)
        timeline_height = 100

        for i, shift in enumerate(self.energy_shifts):
            shift_time = shift.start_time + lead_in
            time_until = shift_time - current_time

            if -0.5 < time_until < 5.0:
                if self.dual_side_active:
                    arrow_from_left = (i % 2 == 1)
                    if arrow_from_left:
                        arrow_x = hit_marker_x - (time_until * self.scroll_speed)
                    else:
                        arrow_x = hit_marker_x + (time_until * self.scroll_speed)
                elif self.bounce_active and self.bounce_reversed:
                    arrow_x = hit_marker_x - time_until * self.scroll_speed
                else:
                    arrow_x = hit_marker_x + time_until * self.scroll_speed

                if timeline_start_x <= arrow_x <= timeline_end_x:
                    speed_up = shift.energy_delta > 0
                    self.draw_speed_arrow(int(arrow_x), timeline_y, timeline_height, speed_up)

        # --- draw bounce obstacles
        for evt in self.bounce_events:
            evt_time = evt.time + lead_in
            time_until = evt_time - current_time
            if -0.5 < time_until < 5.0:
                if self.bounce_active and self.bounce_reversed:
                    obs_x = hit_marker_x - time_until * self.scroll_speed
                else:
                    obs_x = hit_marker_x + time_until * self.scroll_speed
                if timeline_start_x <= obs_x <= timeline_end_x:
                    self.draw_bounce_obstacle(int(obs_x), timeline_y)

        # --- draw beat markers/notes (render AFTER arrows so notes appear on top)

        # Grace window after dual mode ends: suppress leftover notes to prevent teleporting
        song_time = current_time - lead_in
        dual_exit_grace = self.beat_duration * 2
        in_dual_exit_grace = (not self.dual_side_active
                              and song_time - self._last_dual_end_time < dual_exit_grace)

        for note_idx, event in enumerate(self.rhythm.beat_map):
            time_until_hit = event.timestamp - current_time

            # --- calculate position

            if -0.75 < time_until_hit < 5.0:
                # Skip unhit notes that were in a dual-side section (they'd teleport)
                if in_dual_exit_grace and not event.hit and time_until_hit < 0:
                    continue

                note_from_left = False
                if self.dual_side_active and event.char_idx >= 0:
                    note_from_left = (event.char_idx % 2 == 1)

                if self.bounce_active and not self.dual_side_active:
                    if time_until_hit < 0 and not event.hit:
                        continue
                    # Compute the bounce direction at this note's timestamp
                    # so notes keep their original approach direction after a flip
                    note_reversed = False
                    for bevt in self.bounce_events:
                        if bevt.time <= event.timestamp - self.rhythm.lead_in:
                            note_reversed = not note_reversed
                        else:
                            break
                    note_from_left = note_reversed

                if note_from_left:
                    marker_x = hit_marker_x - (time_until_hit * self.scroll_speed)
                else:
                    marker_x = hit_marker_x + (time_until_hit * self.scroll_speed)

                if timeline_start_x <= marker_x <= timeline_end_x:
                    if event.char != "" and not event.hit:
                        is_missed = time_until_hit < 0
                        radius = 14

                        if self.dual_side_active and is_missed:
                            if note_idx not in self.missed_note_shockwaves:
                                self.trigger_miss_shockwave(int(marker_x), timeline_y)
                                self.missed_note_shockwaves.add(note_idx)
                            continue

                        if is_missed:
                            color = C.MISSED_COLOR
                        else:
                            color = C.COLOR

                        # Draw the main note circle
                        pygame.draw.circle(
                            self.screen,
                            color,
                            (int(marker_x), timeline_y),
                            radius
                        )

        # --- draw progress bar on the left side of the timeline
        progress_bar_x = timeline_start_x - 30
        progress_bar_height = 200
        progress_bar_width = 8
        progress_bar_top = timeline_y - progress_bar_height // 2
        progress_bar_bottom = timeline_y + progress_bar_height // 2

        total_notes = len(self.rhythm.beat_map)
        if total_notes > 0:
            level_progress = min(1.0, self.rhythm.char_event_idx / total_notes)
        else:
            level_progress = 0.0

        pygame.draw.rect(
            self.screen,
            (40, 40, 40),
            (progress_bar_x - progress_bar_width // 2, progress_bar_top, progress_bar_width, progress_bar_height),
            border_radius=4
        )

        filled_height = int(progress_bar_height * level_progress)
        if filled_height > 0:
            pygame.draw.rect(
                self.screen,
                (100, 200, 255),
                (progress_bar_x - progress_bar_width // 2, progress_bar_bottom - filled_height, progress_bar_width, filled_height),
                border_radius=4
            )

    def show_message(self, txt: str, secs: float):
        self.message = txt
        self.message_duration = secs
    
    def draw_text(self, txt: str, left: bool):
        text_surface = self.font.render(txt, True, (255, 255, 255))
        if left:
            self.screen.blit(text_surface, (100, 100))
        else:
            text_rect = text_surface.get_rect(center=(1100, 250))
            self.screen.blit(text_surface, text_rect)
    
    def draw_curr_word(self, txt: str):
        self.draw_text(txt, True)