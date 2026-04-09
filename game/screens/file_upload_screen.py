"""
File upload screen — four-step flow:
  1. Browse for a .mp3 or .wav file (minimum 30 s)
  2. Enter optional Song Name + Artist
  3. Click "Add to Game!"
  4. Lyrics fetched in a background thread; spinner shown
  5. Returns ("upload", file_path, word_bank) when ready

update() is split into:
  _handle_input  — back, browse, add-to-game clicks
  _update_fetch  — check if background thread finished
  _update_spinner — advance the braille spinner animation
"""
from __future__ import annotations
import os
import threading
import pygame

from ..menu_utils import _FONT, pick_audio_file, _audio_duration, _fetch_lyrics_words, DEFAULT_WORD_BANK
from ..ui_components import _EXIT_IMG, Button, TextInput, ImageButton
from ._constants import SPINNER_FRAMES, SPINNER_INTERVAL


class FileUploadScreen:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        sw, sh = screen.get_size()
        cy = sh // 2

        self.title_font  = pygame.font.Font(_FONT, 72)
        self.label_font  = pygame.font.Font(_FONT, 32)
        self.status_font = pygame.font.Font(_FONT, 30)
        btn_font         = pygame.font.Font(_FONT, 48)
        input_font       = pygame.font.Font(_FONT, 36)

        self.selected_path = None
        self.status_msg    = "Choose a .mp3 or .wav file."
        self.status_color  = (160, 160, 160)

        btn_sz = 52
        self.back_button = ImageButton(
            30 + btn_sz // 2, 30 + btn_sz // 2, btn_sz, _EXIT_IMG
        )
        self.browse_button = Button(
            (sw // 2 - 160, cy - 160, 320, 54),
            "Browse Files…", btn_font,
            base_color=(140, 180, 255), hover_color=(200, 225, 255),
        )
        self.add_button = Button(
            (sw // 2 - 160, cy + 120, 320, 54),
            "Add to Game!", btn_font,
            base_color=(80, 200, 120), hover_color=(120, 240, 160),
        )

        field_w = 360
        self.input_title = TextInput(
            (sw // 2 - field_w // 2, cy - 60,  field_w, 44),
            input_font, placeholder="Song Name  (optional)",
        )
        self.input_artist = TextInput(
            (sw // 2 - field_w // 2, cy + 12, field_w, 44),
            input_font, placeholder="Artist  (optional)",
        )

        # Fetch state
        self._fetching:    bool                     = False
        self._fetch_done:  bool                     = False
        self._fetch_words: list[str]                = []
        self._fetch_thread: threading.Thread | None = None
        self._result_box:   list[list[str]]         = [[]]

        # Spinner state
        self._spinner_idx: int   = 0
        self._spinner_acc: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def show_error(self, message: str) -> None:
        self.status_msg   = message
        self.status_color = (255, 120, 120)

    def update(self, dt: float, mouse_pos, mouse_clicked, current_time, events):
        """Returns (action, file_path, word_bank).  action is 'back', 'upload', or None."""
        self.input_title.handle_events(events)
        self.input_artist.handle_events(events)

        if self.back_button.update(mouse_pos, mouse_clicked):
            return "back", None, None

        fetch_result = self._update_fetch()
        if fetch_result is not None:
            return fetch_result

        if self._fetching:
            self._update_spinner(dt)
            return None, None, None

        return self._handle_input(mouse_pos, mouse_clicked)

    def draw(self, current_time: float) -> None:
        sw, sh = self.screen.get_size()
        cy = sh // 2

        title = self.title_font.render("Upload a Song", True, (255, 255, 255))
        self.screen.blit(title, title.get_rect(center=(sw // 2, cy - 230)))

        self.browse_button.draw(self.screen, current_time)

        status = self.status_font.render(self.status_msg, True, self.status_color)
        self.screen.blit(status, status.get_rect(center=(sw // 2, cy - 96)))

        if self._fetching:
            spin_font = pygame.font.Font(_FONT, 52)
            spin_surf = spin_font.render(
                f"Fetching lyrics…  {SPINNER_FRAMES[self._spinner_idx]}",
                True, (180, 180, 220),
            )
            self.screen.blit(spin_surf, spin_surf.get_rect(center=(sw // 2, cy + 60)))
            self.back_button.draw(self.screen, current_time)
            return

        lbl_color = (130, 130, 160)
        lbl1 = self.label_font.render("Song Name", True, lbl_color)
        lbl2 = self.label_font.render("Artist",    True, lbl_color)
        self.screen.blit(lbl1, lbl1.get_rect(
            bottomleft=(self.input_title.rect.x,  self.input_title.rect.y  - 4)
        ))
        self.screen.blit(lbl2, lbl2.get_rect(
            bottomleft=(self.input_artist.rect.x, self.input_artist.rect.y - 4)
        ))
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

    # ── Private helpers ───────────────────────────────────────────────────────

    def _handle_input(self, mouse_pos, mouse_clicked) -> tuple:
        self.browse_button.check_hover(mouse_pos)
        if self.browse_button.check_click(mouse_pos, mouse_clicked):
            path = pick_audio_file()
            if path:
                ext = os.path.splitext(path)[1].lower()
                if ext not in (".mp3", ".wav"):
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

    def _update_fetch(self) -> tuple | None:
        """Check if the background fetch thread finished.  Returns upload tuple or None."""
        if self._fetching and self._fetch_thread and not self._fetch_thread.is_alive():
            self._fetching   = False
            self._fetch_done = True
            self._fetch_words = self._result_box[0]

        if self._fetch_done:
            self._fetch_done = False
            return "upload", self.selected_path, self._fetch_words

        return None

    def _update_spinner(self, dt: float):
        self._spinner_acc += dt
        if self._spinner_acc >= SPINNER_INTERVAL:
            self._spinner_acc  = 0.0
            self._spinner_idx  = (self._spinner_idx + 1) % len(SPINNER_FRAMES)

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
