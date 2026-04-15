"""
UI audio manager — alternating click sounds, level-click, and level-finish sounds.
All sounds are loaded lazily on first use.
"""
import os
import pygame

_EFFECTS = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'assets', 'audios', 'effects',
)

_sounds: dict = {}
_click_idx: int = 0


def _load(name: str) -> 'pygame.mixer.Sound | None':
    if name in _sounds:
        return _sounds[name]
    path = os.path.join(_EFFECTS, name)
    try:
        s = pygame.mixer.Sound(path)
        _sounds[name] = s
        return s
    except Exception:
        _sounds[name] = None
        return None


def play_click() -> None:
    """Alternate between click.wav and click2.wav on every call."""
    global _click_idx
    name = 'click.wav' if _click_idx % 2 == 0 else 'click2.wav'
    _click_idx += 1
    s = _load(name)
    if s:
        s.set_volume(0.65)
        s.play()


def play_level_click() -> None:
    """Play the level-start click sound."""
    s = _load('levelclick.mp3')
    if s:
        s.set_volume(0.975)
        s.play()


def play_level_finish() -> None:
    """Play both levelfinish sounds simultaneously (on separate mixer channels)."""
    s1 = _load('levelfinish.mp3')
    s2 = _load('levelfinish2.mp3')
    if s1:
        s1.set_volume(1.0)
        s1.play()
    if s2:
        s2.set_volume(1.0)
        s2.play()
