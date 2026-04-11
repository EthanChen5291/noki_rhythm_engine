import time
from . import constants as C
from . import models as M
from typing import Optional


def calculate_lead_in(
    beat_times: list[float],
    min_seconds: float = C.LEAD_IN_MIN_SECONDS
) -> float:
    """
    Calculate lead-in time snapped to exact measure boundaries using actual beat frames.
    Returns the time of the first measure boundary that exceeds min_seconds.
    """
    if len(beat_times) < C.BEATS_PER_MEASURE * 2:
        return min_seconds

    for i in range(0, len(beat_times), C.BEATS_PER_MEASURE):
        measure_time = beat_times[i]
        if measure_time >= min_seconds:
            return measure_time

    last_measure_idx = (len(beat_times) // C.BEATS_PER_MEASURE) * C.BEATS_PER_MEASURE
    if last_measure_idx < len(beat_times):
        return beat_times[last_measure_idx]

    return min_seconds

class RhythmManager:
    """
    Manages rhythm gameplay timing, scoring, and feedback.
    """
    def __init__(self, beat_map: list[M.CharEvent], bpm: float, lead_in: float = 0.0, timing_scale: float = 1.0):
        self.bpm = bpm
        self.beat_duration = 60 / bpm
        self.lead_in = lead_in
        self.timing_scale = timing_scale

        self.beat_map = [
            M.CharEvent(
                char=e.char,
                timestamp=e.timestamp + lead_in,
                word_text=e.word_text,
                char_idx=e.char_idx,
                beat_position=e.beat_position,
                section=e.section,
                is_rest=e.is_rest,
                hit=e.hit,
                from_left=e.from_left,
                hold_duration=e.hold_duration,
            )
            for e in beat_map
        ]

        # playback state
        self.char_event_idx = 0
        self.start_time = time.perf_counter()

        # word tracking
        self.current_word_idx = 0
        self.last_word = None

        # accuracy tracking
        self.combo = 0
        self.max_combo = 0
        self.perfect_hits = 0
        self.good_hits = 0
        self.hold_perfect_hits = 0
        self.hold_good_hits = 0
        self.miss_count = 0

        self.playable_events = [e for e in self.beat_map if not e.is_rest]

        # hold note tracking
        self._active_hold: Optional[M.CharEvent] = None
        self._hold_press_time: float = 0.0
        self._hold_judgment: str = 'ok'
        # grace: player may release this fraction before the full duration and still score
        self._hold_release_grace = 0.12  # 12% early-release tolerance

        self._setup_timing_windows()
    
    def _setup_timing_windows(self):
        """Define timing windows like modern rhythm games"""
        base_window = min(0.15, self.beat_duration * 0.4)
        
        self.timing_windows = {
            'perfect': base_window * 0.5 * self.timing_scale,
            'good': base_window * self.timing_scale,
            'ok': base_window * 1.5 * self.timing_scale,
        }
    
    def update(self):
        """Advance through the beatmap based on elapsed time"""
        if self.is_finished():
            return

        elapsed = time.perf_counter() - self.start_time

        # Auto-complete a hold only when the fixed musical end time has elapsed
        if self._active_hold is not None:
            hold_end_time = self._active_hold.timestamp + self._active_hold.hold_duration
            if elapsed >= hold_end_time:
                self._complete_hold(self._hold_judgment)
            return  # while holding, don't advance past the hold note

        while self.char_event_idx < len(self.beat_map):
            current_event = self.beat_map[self.char_event_idx]

            if current_event.is_rest:
                if elapsed >= current_event.timestamp:
                    self.char_event_idx += 1
                    continue
                else:
                    break

            miss_threshold = current_event.timestamp + self.timing_windows['ok']

            if elapsed > miss_threshold:
                self._register_miss()
                self.char_event_idx += 1
            else:
                break
    
    def check_input(self, typed_char: str) -> dict:
        """
        Check if typed character matches current expected character.
        Returns judgment info like modern rhythm games.

        For hold notes, returns judgment='hold_started' and defers scoring to on_key_release().
        Returns:
            dict with keys: 'hit', 'judgment', 'time_diff', 'combo'
        """
        if self.is_finished():
            return {'hit': False, 'judgment': 'miss', 'time_diff': 0, 'combo': self.combo}

        # If a hold is currently active, ignore further input until it resolves
        if self._active_hold is not None:
            return {'hit': False, 'judgment': 'miss', 'time_diff': 0, 'combo': self.combo}

        current_event = self.current_event()
        if not current_event or current_event.is_rest:
            return {'hit': False, 'judgment': 'miss', 'time_diff': 0, 'combo': self.combo}

        expected_char = current_event.char

        if typed_char != expected_char:
            self._register_miss()
            return {'hit': False, 'judgment': 'wrong', 'time_diff': 0, 'combo': 0}

        elapsed = time.perf_counter() - self.start_time
        time_diff = abs(elapsed - current_event.timestamp)

        judgment = self._get_judgment(time_diff)

        if judgment == 'miss':
            self._register_miss()
            return {'hit': False, 'judgment': 'miss', 'time_diff': time_diff, 'combo': 0}

        # Hold note: start tracking — score is given on release
        if current_event.hold_duration > 0:
            self._active_hold = current_event
            self._hold_press_time = elapsed
            self._hold_judgment = judgment
            current_event.hit = True
            self.char_event_idx += 1
            return {
                'hit': True,
                'judgment': 'hold_started',
                'time_diff': time_diff,
                'combo': self.combo,
                'is_word_complete': False,
            }

        self._register_hit(judgment)
        current_event.hit = True
        self.char_event_idx += 1

        return {
            'hit': True,
            'judgment': judgment,
            'time_diff': time_diff,
            'combo': self.combo,
            'is_word_complete': self._is_word_complete()
        }

    def on_key_release(self, released_char: str) -> dict:
        """
        Called when a key is released. If a hold note is active for that char,
        checks whether the player held long enough and scores accordingly.
        Returns result dict (same shape as check_input), or empty dict if irrelevant.
        """
        if self._active_hold is None:
            return {}
        if released_char != self._active_hold.char:
            return {}

        elapsed = time.perf_counter() - self.start_time
        hold_end_time = self._active_hold.timestamp + self._active_hold.hold_duration
        required_time = hold_end_time - self._active_hold.hold_duration * self._hold_release_grace

        if elapsed >= required_time:
            return self._complete_hold(self._hold_judgment)
        else:
            # Released too early — miss
            self._active_hold = None
            self._register_miss()
            return {'hit': False, 'judgment': 'hold_broken', 'time_diff': 0, 'combo': 0}

    def _complete_hold(self, judgment: str) -> dict:
        """Score a successfully completed hold note and clear hold state."""
        self._register_hold_hit(judgment)
        self._active_hold = None
        return {
            'hit': True,
            'judgment': f'hold_{judgment}',
            'time_diff': 0,
            'combo': self.combo,
            'is_word_complete': self._is_word_complete(),
        }
    
    def _get_judgment(self, time_diff: float) -> str:
        """Determine hit quality based on timing accuracy"""
        if time_diff <= self.timing_windows['perfect']:
            return 'perfect'
        elif time_diff <= self.timing_windows['good']:
            return 'good'
        elif time_diff <= self.timing_windows['ok']:
            return 'ok'
        else:
            return 'miss'
    
    def _register_hit(self, judgment: str):
        """Register a successful hit and update combo"""
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)

        if judgment == 'perfect':
            self.perfect_hits += 1
        elif judgment == 'good':
            self.good_hits += 1

    def _register_hold_hit(self, judgment: str):
        """Register a completed hold note — worth more than a tap."""
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)

        if judgment == 'perfect':
            self.hold_perfect_hits += 1
        elif judgment == 'good':
            self.hold_good_hits += 1
    
    def _register_miss(self):
        """Register a miss and break combo"""
        self.combo = 0
        self.miss_count += 1
    
    def _is_word_complete(self) -> bool:
        """Check if the current word was just completed"""
        if self.char_event_idx >= len(self.beat_map):
            return True
        
        prev_idx = self.char_event_idx - 1
        if prev_idx < 0:
            return False
        
        prev_event = self.beat_map[prev_idx]
        if prev_event.is_rest:
            return False
        
        return (prev_event.char_idx == len(prev_event.word_text) - 1 if prev_event.word_text else False)
    
    # ==================== TIMING CHECKS ====================
    
    def on_beat(self) -> bool:
        """Check if current time is within the 'ok' timing window"""
        if self.is_finished():
            return False
        
        current_event = self.current_event()
        if not current_event or current_event.is_rest:
            return False
        
        elapsed = time.perf_counter() - self.start_time
        time_diff = abs(elapsed - current_event.timestamp)
        
        return time_diff <= self.timing_windows['ok']
    
    def is_in_perfect_window(self) -> bool:
        """Check if within perfect timing window (for visual feedback)"""
        if self.is_finished():
            return False
        
        current_event = self.current_event()
        if not current_event or current_event.is_rest:
            return False
        
        elapsed = time.perf_counter() - self.start_time
        time_diff = abs(elapsed - current_event.timestamp)
        
        return time_diff <= self.timing_windows['perfect']
    
    # ==================== GETTERS ====================
    
    def current_event(self) -> Optional[M.CharEvent]:
        """Gets the current beat event"""
        if self.char_event_idx >= len(self.beat_map):
            return None
        return self.beat_map[self.char_event_idx]
    
    def current_expected_char(self) -> Optional[str]:
        """Get the character the player should type currently"""
        event = self.current_event()
        if not event or event.is_rest or not event.char:
            return None
        return event.char
    
    def current_expected_word(self) -> Optional[str]:
        """Get the current word being typed"""
        event = self.current_event()

        if not event:
            return self.last_word

        if event.is_rest:
            for i in range(self.char_event_idx + 1, len(self.beat_map)):
                next_event = self.beat_map[i]
                if not next_event.is_rest and next_event.word_text:
                    return next_event.word_text
            return self.last_word

        if event.word_text:
            self.last_word = event.word_text

        return self.last_word
    
    def current_display_word(self) -> Optional[str]:
        """Return only the chars of the current word that were actually mapped to beat events."""
        word_text = self.current_expected_word()
        if not word_text:
            return word_text

        # Find the highest char_idx mapped for this word starting from the current position
        max_char_idx = -1
        for i in range(self.char_event_idx, len(self.beat_map)):
            ev = self.beat_map[i]
            if ev.is_rest:
                continue
            if ev.word_text != word_text:
                # Stop once we've moved past this word's block
                if max_char_idx >= 0:
                    break
                continue
            if ev.char_idx > max_char_idx:
                max_char_idx = ev.char_idx

        if max_char_idx < 0:
            return word_text  # fallback: show full word if nothing found ahead

        return word_text[:max_char_idx + 1]

    def get_upcoming_events(self, lookahead_time: float = 3.0) -> list[M.CharEvent]:
        """
        Get events coming up in the next N seconds (for visualization).
        Useful for scrolling note highways.
        """
        if self.is_finished():
            return []
        
        current_time = time.perf_counter() - self.start_time
        upcoming = []
        
        for event in self.beat_map[self.char_event_idx:]:
            if event.timestamp - current_time > lookahead_time:
                break
            upcoming.append(event)
        
        return upcoming
    
    def get_progress(self) -> float:
        """Get completion percentage (0.0 to 1.0)"""
        if not self.beat_map:
            return 1.0
        return self.char_event_idx / len(self.beat_map)
    
    def is_finished(self) -> bool:
        """Check if song is complete"""
        return self.char_event_idx >= len(self.beat_map)
    
    # ==================== SCORING ====================
    
    def get_score(self) -> int:
        """
        Calculate score based on modern rhythm game scoring.
        Perfect hits are worth more, combo multiplier applies.
        Hold notes are worth 500/175 (perfect/good) — more than taps.
        """
        base_score = (
            self.perfect_hits * 300 +
            self.good_hits * 100 +
            self.hold_perfect_hits * 500 +
            self.hold_good_hits * 175
        )

        combo_multiplier = min(1.0 + (self.max_combo / 100), 2.0)

        return int(base_score * combo_multiplier)
    
    def get_accuracy(self) -> float:
        """Calculate accuracy percentage (0-100%)"""
        total_notes = len([e for e in self.beat_map if not e.is_rest])
        if total_notes == 0:
            return 100.0

        weighted_hits = (
            self.perfect_hits * 1.0 +
            self.good_hits * 0.7 +
            self.hold_perfect_hits * 1.0 +
            self.hold_good_hits * 0.7
        )

        return min(100.0, (weighted_hits / total_notes) * 100)
    
    def get_rank(self) -> str:
        """Get letter rank based on accuracy (like DDR/osu!)"""
        accuracy = self.get_accuracy()
        
        if accuracy >= 95:
            return 'S'
        elif accuracy >= 90:
            return 'A'
        elif accuracy >= 80:
            return 'B'
        elif accuracy >= 70:
            return 'C'
        else:
            return 'D'
    
    def get_stats(self) -> dict:
        """Get comprehensive gameplay statistics"""
        return {
            'score': self.get_score(),
            'accuracy': self.get_accuracy(),
            'rank': self.get_rank(),
            'combo': self.combo,
            'max_combo': self.max_combo,
            'perfect': self.perfect_hits,
            'good': self.good_hits,
            'misses': self.miss_count,
            'progress': self.get_progress()
        }