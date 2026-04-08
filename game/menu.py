"""
Menu state machine and pause overlay.
UI widgets → ui_components.py
Screen views → screens.py
Utility functions → menu_utils.py
"""
import pygame
import time
import os
import shutil

from .menu_utils import (
    _FONT,
    pick_audio_file,
    DEFAULT_WORD_BANK,
    _load_scores,
    _load_custom_songs,
    _save_custom_songs,
    _load_word_banks,
    _save_word_banks,
)
from .ui_components import Button, Petal
from .screens import TitleScreen, LevelSelect, LevelMenu, FileUploadScreen


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

        # Canon = built-in songs only; custom songs loaded from disk are excluded
        _persisted_custom       = set(_load_custom_songs())
        self._canon_names       = [n for n in song_names if n not in _persisted_custom]
        # Add any persisted custom songs into song_names if not already present
        for _cs in _load_custom_songs():
            if _cs not in self.song_names:
                self.song_names.insert(0, _cs)
        self.title_screen       = TitleScreen(screen)
        self.level_select       = LevelSelect(screen, song_names, self._scores,
                                              canon_names=self._canon_names)
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
        self._show_waiting  = (music is not None and music.needs_start)
        self._dots_timer    = 0.0
        self._dots_count    = 1
        self._waiting_elapsed = 0.0
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
                    while self._video_acc >= self._video_frame_dur:
                        self._video_acc -= self._video_frame_dur
                        ret, frame = self._video_cap.read()
                        if not ret:
                            self._video_cap.release()
                            self._video_cap   = None
                            self._video_done  = True
                            if self._music:
                                self._music.on_intro_video_done()
                            break
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        fh, fw = frame_rgb.shape[:2]
                        surf = pygame.surfarray.make_surface(
                            frame_rgb.transpose(1, 0, 2)
                        )
                        sw2, sh2 = self.screen.get_size()
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

            elif self.state == "level_select":
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
                    fpath = pick_audio_file()
                    if fpath:
                        ok, msg = self._handle_upload(fpath, None)
                        if ok:
                            self.level_select = LevelSelect(self.screen, self.song_names,
                                                            self._scores, self._canon_names)
                            self.level_select.switch_tab(1)
                            self.level_select.begin_rename(0)
                elif action == "cancel_upload":
                    cancel_idx = idx
                    if 0 <= cancel_idx < len(self.song_names):
                        removed = self.song_names.pop(cancel_idx)
                        self.song_word_banks.pop(removed, None)
                        ls = self.level_select
                        if cancel_idx < len(ls.level_buttons):
                            ls.level_buttons.pop(cancel_idx)
                            ls.difficulty_selectors.pop(cancel_idx)
                            ls._full_names.pop(cancel_idx)
                        ls._tab_indices = [[], []]
                        for j, name in enumerate(self.song_names):
                            t = 0 if name in ls._canon_set else 1
                            ls._tab_indices[t].append(j)
                        ls._recompute_max_scrolls()
                elif action == "rename":
                    rename_idx, new_name = self.level_select._rename_result
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
                        self.level_select = LevelSelect(self.screen, self.song_names,
                                                        self._scores, self._canon_names)
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
            if filename in self.song_names:
                self.song_names.remove(filename)
            self.song_names.insert(0, filename)
            self.song_word_banks[filename] = word_bank if word_bank is not None else DEFAULT_WORD_BANK[:]
            _save_word_banks(self.song_word_banks)
            _custom = _load_custom_songs()
            if filename not in _custom:
                _custom.append(filename)
                _save_custom_songs(_custom)
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
