"""
Slot-based rhythm generation helpers.
Handles slot building, filtering, grouping, word assignment, and intensity adjustment.
Public API (generate_beatmap, deduplicate_events) lives in beatmap_generator.py.
"""
import random
from typing import Optional
from analysis.audio_analysis import analyze_song_intensity, get_sb_info, detect_hold_regions
from . import constants as C
from . import models as M


# ==================== SLOT-BASED RHYTHM GENERATION ====================

def build_rhythm_slots(sb_info: list[M.SubBeatInfo], song: M.Song) -> list[M.RhythmSlot]:
    """
    Build rhythm slots from audio analysis.
    A slot is a potential character placement based on musical features.
    """
    slots: list[M.RhythmSlot] = []
    beat_duration = 60 / song.bpm

    for i, sb in enumerate(sb_info):
        is_note_slot = False
        priority = 0

        if sb.level == M.SubBeatIntensity.STRONG:
            is_note_slot = True
            priority = 3  # high priority
        elif sb.level == M.SubBeatIntensity.MEDIUM:
            # only include medium beats when there's a meaningful gap since the last slot
            if not slots or (sb.time - slots[-1].time) > 0.6:
                is_note_slot = True
                priority = 2  # medium priority
        # weak beats: skip entirely — too many fill the map and dilute strong beats

        if is_note_slot:
            slots.append(M.RhythmSlot(
                time=sb.time,
                intensity=sb.raw_intensity,
                priority=priority,
                is_filled=False,
                beat_position=sb.time / beat_duration
            ))

    return slots


def filter_slots_for_playability(slots: list[M.RhythmSlot], min_spacing: float = 0.12) -> list[M.RhythmSlot]:
    """
    Remove slots that are too close together for comfortable typing.
    Modern rhythm games maintain ~120-150ms minimum spacing.
    """
    if not slots:
        return []

    filtered = [slots[0]]

    for slot in slots[1:]:
        if slot.time - filtered[-1].time >= min_spacing:
            filtered.append(slot)

    return filtered


def group_slots_by_measure(slots: list[M.RhythmSlot], beat_duration: float) -> list[list[M.RhythmSlot]]:
    """Group rhythm slots into measures (4 beats each)"""
    if not slots:
        return []

    measure_duration = beat_duration * C.BEATS_PER_MEASURE

    first_measure = int(slots[0].time / measure_duration)
    last_measure = int(slots[-1].time / measure_duration)

    num_measures = last_measure - first_measure + 1
    measures: list[list[M.RhythmSlot]] = [[] for _ in range(num_measures)]

    for slot in slots:
        measure_idx = int(slot.time / measure_duration) - first_measure
        if 0 <= measure_idx < num_measures:
            measures[measure_idx].append(slot)

    # measures = [m for m in measures if m]  #uncomment to remove empty measures

    return measures


# ==================== WORD MANAGEMENT ====================

def get_words_with_rhythm_info(words: list[str], beat_duration: float, target_cps: float = C.TARGET_CPS) -> list[M.Word]:
    """Enhanced word creation with better rhythm properties"""
    return [
        M.Word(
            text=word,
            rest_type=None,
            ideal_beats=(ideal := len(word) / target_cps / beat_duration),
            snapped_beats=(snapped := snap_to_grid(ideal, C.SNAP_GRID)),
            snapped_cps=len(word) / (snapped * beat_duration)
        )
        for word in words
    ]


def select_word_for_measure(
    available_slots: int,
    remaining_words: list[M.Word],
    word_bank: list[M.Word],
    intensity_ratio: float = 1.0,
    target_cps: float = C.TARGET_CPS,
    cps_tolerance: float = C.CPS_TOLERANCE,
) -> Optional[M.Word]:
    """
    Select the best word for a measure based on:
    - Number of available rhythm slots
    - Intensity ratio (loud = more chars, quiet = fewer)
    - Word variety
    """
    if not remaining_words:
        return None

    # adjust target based on intensity
    if intensity_ratio > 1.2:
        target_chars = min(available_slots, int(available_slots * 0.9))
    elif intensity_ratio > 1.0:
        target_chars = min(available_slots, int(available_slots * 0.8))
    elif intensity_ratio < 0.8:
        target_chars = max(2, int(available_slots * 0.5))
    elif intensity_ratio < 1.0:
        target_chars = max(2, int(available_slots * 0.7))
    else:
        target_chars = max(2, int(available_slots * 0.75))

    tolerance = 2 if abs(intensity_ratio - 1.0) > 0.3 else 1
    candidates = [
        w for w in remaining_words
        if abs(len(w.text) - target_chars) <= tolerance and len(w.text) <= available_slots
    ]

    if not candidates:
        candidates = [w for w in remaining_words if len(w.text) <= available_slots]

    if not candidates:
        candidates = [min(remaining_words, key=lambda w: len(w.text))]

    effective_cps = target_cps * intensity_ratio
    viable = [w for w in candidates if abs(w.snapped_cps - effective_cps) <= cps_tolerance * 1.5]

    return random.choice(viable if viable else candidates)


# ==================== SLOT ASSIGNMENT ====================

def find_next_measure_time(measures, start_idx, fallback_time):
    for j in range(start_idx + 1, len(measures)):
        if measures[j]:  # non-empty measure
            return measures[j][0].time
    return fallback_time


def assign_words_to_slots(
    measures: list[list[M.RhythmSlot]],
    word_bank: list[M.Word],
    beat_duration: float,
    intensity_profile: Optional[M.IntensityProfile] = None,
    dual_side_sections: Optional[list[M.DualSideSection]] = None,
    hold_regions: Optional[list[tuple[float, float]]] = None,
    target_cps: float = C.TARGET_CPS,
    cps_tolerance: float = C.CPS_TOLERANCE,
) -> list[M.CharEvent]:
    """
    Assign characters to rhythm slots measure-by-measure.
    This creates a natural, musical rhythm flow.
    """
    events: list[M.CharEvent] = []
    remaining_words = word_bank.copy()
    section_idx = 0
    last_word_end_time = -float('inf')
    last_word_text = ""
    dual_note_count = 0   # counts notes placed inside dual sections for alternation

    # one measure grace period when starting dual sections
    grace_beats = 4
    grace_duration = grace_beats * beat_duration

    for measure_idx, measure_slots in enumerate(measures):
        if not measure_slots or not remaining_words:
            continue

        section_idx = measure_idx // 4

        first_slot_time = measure_slots[0].time
        if first_slot_time < last_word_end_time + C.MIN_WORD_GAP:
            continue

        in_grace_period = False
        if dual_side_sections:
            for dual_sec in dual_side_sections:
                pre_start_begin = dual_sec.start_time - grace_duration
                if pre_start_begin <= first_slot_time < dual_sec.start_time:
                    in_grace_period = True
                    break
                start_grace_end = dual_sec.start_time + grace_duration
                if dual_sec.start_time <= first_slot_time < start_grace_end:
                    in_grace_period = True
                    break
                end_grace_end = dual_sec.end_time + grace_duration
                if dual_sec.end_time <= first_slot_time < end_grace_end:
                    in_grace_period = True
                    break

        if in_grace_period:
            continue

        intensity_ratio = 1.0
        if intensity_profile and section_idx < len(intensity_profile.section_intensities):
            avg_intensity = sum(intensity_profile.section_intensities) / len(intensity_profile.section_intensities)
            intensity_ratio = intensity_profile.section_intensities[section_idx] / (avg_intensity + 1e-6)

        if intensity_profile and section_idx < len(intensity_profile.section_intensities):
            intensity = intensity_profile.section_intensities[section_idx]
            avg = sum(intensity_profile.section_intensities) / len(intensity_profile.section_intensities)

            if intensity < avg * 0.7 and random.random() < 0.65:
                continue

        candidates = [w for w in remaining_words if w.text != last_word_text]
        if not candidates:
            candidates = remaining_words

        word = select_word_for_measure(
            len(measure_slots),
            candidates,
            word_bank,
            intensity_ratio,
            target_cps=target_cps,
            cps_tolerance=cps_tolerance,
        )

        if not word or not word.text:
            continue

        if word in remaining_words:
            remaining_words.remove(word)

        chars_to_place = min(len(word.text), len(measure_slots), C.MAX_SLOTS_PER_MEASURE)

        sorted_slots = sorted(measure_slots, key=lambda s: s.priority, reverse=True)
        selected_slots = sorted_slots[:chars_to_place]

        selected_slots.sort(key=lambda s: s.time)

        if not selected_slots:
            continue

        for char_idx in range(chars_to_place):
            char = word.text[char_idx]
            slot = selected_slots[char_idx]

            from_left = False
            if dual_side_sections:
                for dual_sec in dual_side_sections:
                    if dual_sec.start_time <= slot.time < dual_sec.end_time:
                        from_left = (dual_note_count % 2 == 1)
                        dual_note_count += 1
                        break

            # Check if this slot falls within a detected hold region
            hold_dur = 0.0
            if hold_regions:
                next_slot_time = (
                    selected_slots[char_idx + 1].time
                    if char_idx + 1 < chars_to_place
                    else float('inf')
                )
                for hr_start, hr_dur in hold_regions:
                    if abs(slot.time - hr_start) <= beat_duration * 0.5:
                        # Cap hold so it doesn't bleed into next char (leave 150ms gap)
                        max_dur = max(0.0, next_slot_time - slot.time - 0.15)
                        hold_dur = min(hr_dur, max_dur)
                        break

            events.append(M.CharEvent(
                char=char,
                timestamp=slot.time,
                word_text=word.text,
                char_idx=char_idx,
                beat_position=slot.beat_position,
                section=section_idx,
                is_rest=False,
                from_left=from_left,
                hold_duration=hold_dur,
            ))
            slot.is_filled = True

        last_word_end_time = selected_slots[chars_to_place - 1].time
        last_word_text = word.text

        if measure_idx < len(measures) - 1:
            rest_time = selected_slots[-1].time + 0.1

            events.append(M.CharEvent(
                char="",
                timestamp=rest_time,
                word_text="",
                char_idx=-1,
                beat_position=selected_slots[-1].beat_position,
                section=section_idx,
                is_rest=True
            ))

        # recycle words if running low
        if len(remaining_words) < len(word_bank) * 0.3:
            for w in word_bank:
                if w not in remaining_words:
                    remaining_words.append(w)

    return events


# ==================== RHYTHM VARIATIONS ====================

def add_rhythm_variations(events: list[M.CharEvent], song: M.Song) -> list[M.CharEvent]:
    """
    Add modern rhythm game elements:
    - Occasional bursts (fast typing sections)
    - Syncopation (off-beat emphasis)
    - Call-and-response patterns
    """
    if not events:
        return events

    sections = group_events_by_section(events)
    enhanced: list[M.CharEvent] = []

    for section in sections:
        if random.random() < 0.2:
            for e in section:
                if not e.is_rest:
                    e_copy = M.CharEvent(
                        char=e.char,
                        timestamp=e.timestamp * 0.95,
                        word_text=e.word_text,
                        char_idx=e.char_idx,
                        beat_position=e.beat_position,
                        section=e.section,
                        is_rest=e.is_rest
                    )
                    enhanced.append(e_copy)
                else:
                    enhanced.append(e)
        else:
            enhanced.extend(section)

    return enhanced


# ==================== UTILITY FUNCTIONS ====================

def snap_to_grid(beats: float, grid: float = 0.5) -> float:
    """Snap beats to nearest musical grid interval"""
    return round(beats / grid) * grid


def group_events_by_section(events: list[M.CharEvent]) -> list[list[M.CharEvent]]:
    """Groups CharEvents by section"""
    if not events:
        return []

    sections: list[list[M.CharEvent]] = []
    current = [events[0]]

    for e in events[1:]:
        if e.section != current[-1].section:
            sections.append(current)
            current = []
        current.append(e)

    if current:
        sections.append(current)

    return sections


def adjust_slots_by_intensity(
    measures: list[list[M.RhythmSlot]],
    intensity_profile: Optional[M.IntensityProfile],
    beat_duration: float,
    target_cps: float = C.TARGET_CPS,
) -> list[list[M.RhythmSlot]]:
    """
    Adjust slot density based on song intensity.
    Loud sections = more slots (higher CPS)
    Quiet sections = fewer slots (lower CPS)
    """
    if not intensity_profile or not measures:
        return measures

    adjusted_measures = []

    for measure_idx, measure_slots in enumerate(measures):
        if not measure_slots:
            adjusted_measures.append([])
            continue

        section_idx = measure_idx // 4

        if section_idx >= len(intensity_profile.section_intensities):
            adjusted_measures.append(measure_slots)
            continue

        section_intensity = intensity_profile.section_intensities[section_idx]
        avg_intensity = sum(intensity_profile.section_intensities) / len(intensity_profile.section_intensities)
        intensity_ratio = section_intensity / (avg_intensity + 1e-6)

        # ADJUST SLOT DENSITY BASED ON INTENSITY
        if intensity_ratio > 1.3:  # very loud — allow medium + strong
            keep_slots = [s for s in measure_slots if s.priority >= 2]
        elif intensity_ratio > 1.0:  # moderately loud — strong only
            keep_slots = [s for s in measure_slots if s.priority >= 3]
        elif intensity_ratio < 0.6:  # very quiet — top strong slot only
            strong = [s for s in measure_slots if s.priority >= 3]
            keep_slots = strong[:1] if strong else []
        elif intensity_ratio < 0.85:  # quiet — strong only, cap at 1
            strong = [s for s in measure_slots if s.priority >= 3]
            keep_slots = strong[:1] if strong else []
        else:  # normal — strong only
            keep_slots = [s for s in measure_slots if s.priority >= 3]

        if len(keep_slots) > 1:
            keep_slots.sort(key=lambda s: s.time)
            filtered = [keep_slots[0]]

            for slot in keep_slots[1:]:
                if slot.time - filtered[-1].time >= 0.12:
                    filtered.append(slot)

            adjusted_measures.append(filtered)
        else:
            adjusted_measures.append(keep_slots)

    return adjusted_measures
