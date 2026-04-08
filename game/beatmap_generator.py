"""
Public API for beatmap generation.
Slot-building, word assignment, and intensity helpers live in slot_builder.py.
"""
from typing import Optional
from analysis.audio_analysis import analyze_song_intensity, get_sb_info, detect_hold_regions
from . import constants as C
from . import models as M
from .slot_builder import (
    build_rhythm_slots,
    filter_slots_for_playability,
    group_slots_by_measure,
    get_words_with_rhythm_info,
    assign_words_to_slots,
    adjust_slots_by_intensity,
)


def generate_beatmap(
    word_list: list[str],
    song: M.Song,
    dual_side_sections: Optional[list[M.DualSideSection]] = None,
    difficulty: str = "classic",
) -> list[M.CharEvent]:
    """Generate an engaging, playable beatmap using slot-based rhythm generation."""
    profile = C.DIFFICULTY_PROFILES[difficulty]
    beat_duration = 60 / song.bpm

    sb_info = get_sb_info(song, subdivisions=4)
    slots = build_rhythm_slots(sb_info, song)
    slots = filter_slots_for_playability(slots, min_spacing=profile.min_char_spacing)

    measures = group_slots_by_measure(slots, beat_duration)

    intensity_profile = None
    if song.file_path:
        path = C._to_abs_path(song.file_path)
        if path:
            intensity_profile = analyze_song_intensity(path, song.bpm)

    # adjust slots based on intensity
    measures = adjust_slots_by_intensity(measures, intensity_profile, beat_duration, target_cps=profile.target_cps)

    for i, measure in enumerate(measures):
        if len(measure) > C.MAX_SLOTS_PER_MEASURE:
            measure_sorted = sorted(measure, key=lambda s: (-s.priority, s.time))
            measures[i] = sorted(measure_sorted[:C.MAX_SLOTS_PER_MEASURE], key=lambda s: s.time)

    # Detect hold regions from audio
    hold_regions: list[tuple[float, float]] = []
    if song.file_path:
        path = C._to_abs_path(song.file_path)
        if path:
            hold_regions = detect_hold_regions(path, song.beat_times, song.bpm)

    word_bank = get_words_with_rhythm_info(word_list, beat_duration, target_cps=profile.target_cps)
    events = assign_words_to_slots(
        measures, word_bank, beat_duration, intensity_profile, dual_side_sections,
        hold_regions=hold_regions,
        target_cps=profile.target_cps, cps_tolerance=profile.cps_tolerance,
    )
    #events = add_rhythm_variations(events, song)

    events = deduplicate_events(events, beat_duration, min_spacing=profile.min_char_spacing)

    # Post-process: cap every hold duration so its tail never reaches the next note.
    # Uses a 200ms visual gap so bars never visually touch.
    _HOLD_VISUAL_GAP = 0.20
    char_events = [e for e in events if not e.is_rest and e.char]
    for i, ev in enumerate(char_events):
        if ev.hold_duration <= 0:
            continue
        if i + 1 < len(char_events):
            next_t = char_events[i + 1].timestamp
            max_allowed = max(0.0, next_t - ev.timestamp - _HOLD_VISUAL_GAP)
            if ev.hold_duration > max_allowed:
                ev.hold_duration = max_allowed

    # ensure beatmap doesn't extend past song duration
    # and pad with a blank measure of rest at the end so the last word
    # has time to scroll off before the level ends
    song_end = song.duration
    measure_duration = beat_duration * C.BEATS_PER_MEASURE

    if events:
        cutoff = song_end - measure_duration
        events = [e for e in events if e.timestamp <= cutoff]

    if events:
        last_event_time = max(e.timestamp for e in events)
        pad_time = last_event_time + measure_duration
        if pad_time <= song_end + measure_duration:
            events.append(M.CharEvent(
                char="",
                timestamp=pad_time,
                word_text="",
                char_idx=-1,
                beat_position=0.0,
                section=0,
                is_rest=True
            ))

    return events


def deduplicate_events(
    events: list[M.CharEvent],
    beat_duration: float,
    min_spacing: float = 0.1
) -> list[M.CharEvent]:
    """
    Remove events that are too close together and cap events per measure.
    This catches any duplicates created during processing.
    """
    if not events:
        return events

    events = sorted(events, key=lambda e: e.timestamp)

    filtered: list[M.CharEvent] = []
    for event in events:
        if event.is_rest:
            filtered.append(event)
            continue

        last_char_event = None
        for e in reversed(filtered):
            if not e.is_rest:
                last_char_event = e
                break

        if last_char_event is None or (event.timestamp - last_char_event.timestamp) >= min_spacing:
            filtered.append(event)

    measure_duration = beat_duration * C.BEATS_PER_MEASURE
    measure_events: dict[int, list[M.CharEvent]] = {}

    for event in filtered:
        if event.is_rest:
            continue
        measure_idx = int(event.timestamp / measure_duration)
        if measure_idx not in measure_events:
            measure_events[measure_idx] = []
        measure_events[measure_idx].append(event)

    events_to_remove: set[float] = set()
    for measure_idx, m_events in measure_events.items():
        if len(m_events) > C.MAX_SLOTS_PER_MEASURE:
            excess = m_events[C.MAX_SLOTS_PER_MEASURE:]
            for e in excess:
                events_to_remove.add(e.timestamp)

    return [e for e in filtered if e.is_rest or e.timestamp not in events_to_remove]
