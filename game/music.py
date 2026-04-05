"""
UI Music Manager
----------------
Created once per app launch in main.py and passed through to MenuManager.
Uses pygame.mixer.Sound on dedicated channels (8, 9) — completely separate
from pygame.mixer.music which the game engine uses for song playback.

State machine:
  INTRO         321.wav plays at 180/110 speed (once)
  TITLE         titleloop.wav loops
  CROSSFADE     titleloop fades out / levels1 fades in  (1.5 s)
  LEVELS_INTRO  levels1.wav plays once
  LEVELS_LOOP   levelsloop.wav loops forever
  GAME          both channels paused while game song plays
"""

import os
import time
import numpy as np
import pygame

_AUDIO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "audios")


def _load_speeded(path: str, speed: float) -> pygame.mixer.Sound:
    """Load a WAV and return it resampled to play at `speed` × normal speed."""
    import soundfile as sf
    data, _sr = sf.read(path, dtype="int16", always_2d=True)  # (N, ch) int16
    n_orig   = data.shape[0]
    n_target = max(1, int(round(n_orig / speed)))

    idx  = np.linspace(0, n_orig - 1, n_target)
    i0   = idx.astype(np.int64)
    i1   = np.minimum(i0 + 1, n_orig - 1)
    frac = (idx - i0).astype(np.float32)[:, np.newaxis]
    resampled = (
        data[i0].astype(np.float32) * (1.0 - frac)
        + data[i1].astype(np.float32) * frac
    ).astype(np.int16)

    # Conform to mixer channel count (mono ↔ stereo)
    init = pygame.mixer.get_init()
    mix_ch = init[2] if init else 2
    if mix_ch == 2 and resampled.shape[1] == 1:
        resampled = np.repeat(resampled, 2, axis=1)
    elif mix_ch == 1 and resampled.shape[1] == 2:
        resampled = resampled.mean(axis=1, keepdims=True).astype(np.int16)

    return pygame.sndarray.make_sound(np.ascontiguousarray(resampled))


class MusicManager:
    """
    Instantiate once before the main loop.  Pass to MenuManager every time
    it is created — the state machine remembers where it left off so the
    "only reset on relaunch" behaviour is automatic.
    """

    # States
    _INTRO        = "intro"
    _TITLE        = "title"
    _CROSSFADE    = "crossfade"
    _LEVELS_INTRO = "levels_intro"
    _LEVELS_LOOP  = "levels_loop"
    _GAME         = "game"

    _CROSSFADE_DUR = 0.5   # seconds — levels1 fades in over 0.5 s
    _MASTER        = 0.75  # master volume for UI music

    def __init__(self):
        # Reserve high-numbered channels so the game engine's Sound effects
        # (if any) don't collide with ours.
        pygame.mixer.set_num_channels(max(pygame.mixer.get_num_channels(), 16))
        self._ch0 = pygame.mixer.Channel(8)   # title side
        self._ch1 = pygame.mixer.Channel(9)   # levels side

        # Load sounds (321 gets resampled for speed, others are normal)
        self._snd_321     = _load_speeded(os.path.join(_AUDIO, "321.wav"), 180 / 110)
        self._snd_title   = pygame.mixer.Sound(os.path.join(_AUDIO, "titleloop.wav"))
        self._snd_levels1 = pygame.mixer.Sound(os.path.join(_AUDIO, "levels1.wav"))
        self._snd_loop    = pygame.mixer.Sound(os.path.join(_AUDIO, "levelsloop.wav"))

        self._state          = self._INTRO
        self._pre_game       = None
        self._fade_t         = 0.0
        self._intro_start_t  = time.time()

        # Kick off the intro
        self._ch0.set_volume(self._MASTER)
        self._ch1.set_volume(0.0)
        self._ch0.play(self._snd_321)

    # ── Called every frame from MenuManager.run() ────────────────────────────

    def update(self, dt: float) -> None:
        if self._state == self._INTRO:
            if not self._ch0.get_busy():
                # 321 finished → start titleloop
                self._state = self._TITLE
                self._ch0.set_volume(self._MASTER)
                self._ch0.play(self._snd_title, loops=-1)

        elif self._state == self._CROSSFADE:
            self._fade_t = min(self._fade_t + dt, self._CROSSFADE_DUR)
            t    = self._fade_t / self._CROSSFADE_DUR
            ease = t * t * (3.0 - 2.0 * t)          # smoothstep
            self._ch0.set_volume(self._MASTER * (1.0 - ease))
            self._ch1.set_volume(self._MASTER * ease)
            if self._fade_t >= self._CROSSFADE_DUR:
                self._ch0.stop()
                self._ch0.set_volume(0.0)
                self._state = self._LEVELS_INTRO

        elif self._state == self._LEVELS_INTRO:
            if not self._ch1.get_busy():
                # levels1 finished → start levelsloop
                self._state = self._LEVELS_LOOP
                self._ch1.set_volume(self._MASTER)
                self._ch1.play(self._snd_loop, loops=-1)

    # ── Event hooks ──────────────────────────────────────────────────────────

    @property
    def intro_elapsed(self) -> float:
        """Seconds since 321.wav started; inf once intro is over."""
        if self._state != self._INTRO:
            return float('inf')
        return time.time() - self._intro_start_t

    @property
    def title_ready(self) -> bool:
        """True once 321.wav has finished and titleloop is (or will be) playing."""
        return self._state != self._INTRO

    def on_play_pressed(self) -> None:
        """Call when the title-screen play button is clicked."""
        if self._state == self._TITLE:
            self._state  = self._CROSSFADE
            self._fade_t = 0.0
            self._ch1.set_volume(0.0)
            self._ch1.play(self._snd_levels1)
        # All other states: already past intro → do nothing

    def pause_for_game(self) -> None:
        """Silence UI music while the game's own song is playing."""
        self._pre_game = self._state
        self._state    = self._GAME
        self._ch0.pause()
        self._ch1.pause()

    def resume_from_game(self) -> None:
        """Restore UI music after returning from game."""
        self._state = self._pre_game or self._LEVELS_LOOP
        self._ch0.unpause()
        self._ch1.unpause()
