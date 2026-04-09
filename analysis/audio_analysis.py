from __future__ import annotations

import numpy as np
import librosa
import game.constants as C
import game.models as M
from typing import Optional

def get_bpm(audio_path: str, expected_bpm: Optional[int] = None) -> float:
    """Returns the tempo in BPM. Not fully reliable yet."""
    y, sr = librosa.load(audio_path, sr=None)

    tempo, beat_frames = librosa.beat.beat_track(
        y=y,
        sr=sr,
        start_bpm=expected_bpm if expected_bpm else 120,
        tightness=200
    )

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    if len(beat_times) > 1:
        intervals = np.diff(beat_times)
        median_interval = np.median(intervals)
        bpm = float(60 / median_interval)
    else:
        bpm = float(tempo[0] if isinstance(tempo, np.ndarray) else tempo)

    print(f"Raw BPM (beat_times): {bpm:.3f}")
    
    return bpm

def normalize_bpm(bpm: float) -> int:
    """
    Normalizes bpm to a playable-rhythm BPM. Found through testing.
    
    Librosa typically interprets BPM in a triplet ambiguity. This detects against that
    and provides the appropriate correction.
    """
    if bpm <= 0:
        raise ValueError("Invalid BPM")

    candidates = [
        bpm,
        bpm * 2,
        bpm / 2,
        bpm * 3/2,
        bpm * 2/3,
    ]

    playable = [c for c in candidates if 90 <= c <= 220]

    if playable:
        best = min(playable, key=lambda x: abs(x - 150))
    else:
        best = min(candidates, key=lambda x: abs(x - bpm))

    rounded = int(round(best))

    print(f"Final BPM: {rounded}")
    return rounded

def get_duration(audio_path: str) -> int:
    """Returns the song duration in seconds"""
    y, sr = librosa.load(audio_path, sr=None)
    duration = librosa.get_duration(y=y, sr=sr)
    return int(duration)

def find_downbeat_offset(beat_times: np.ndarray, onset_env: np.ndarray, onset_times: np.ndarray) -> int:
    """
    Find which beat position (0-3) is consistently the downbeat across multiple measures.
    Uses statistical analysis over multiple measures for more reliable detection.
    Returns the offset (0-3) to align beats to measures.
    """
    if len(beat_times) < 8:
        return 0

    num_measures = min(8, len(beat_times) // 4)

    position_intensities = [[] for _ in range(4)]

    for measure_idx in range(num_measures):
        for beat_pos in range(4):
            beat_idx = measure_idx * 4 + beat_pos
            if beat_idx >= len(beat_times):
                break

            bt = beat_times[beat_idx]
            mask = (onset_times >= bt - 0.05) & (onset_times <= bt + 0.05)
            if np.any(mask):
                intensity = float(np.max(onset_env[mask]))
            else:
                intensity = 0.0
            position_intensities[beat_pos].append(intensity)

    # Calculate mean intensity for each beat position
    mean_intensities = []
    for pos in range(4):
        if position_intensities[pos]:
            mean_intensities.append(np.mean(position_intensities[pos]))
        else:
            mean_intensities.append(0.0)

    downbeat_pos = int(np.argmax(mean_intensities))

    return downbeat_pos


def get_song_info(audio_path: str, expected_bpm: Optional[int], *, normalize: Optional[bool] =True) -> M.Song:
    """Gets the song at 'audio_path's duration and tempo (BPM).

    Can normalize bpm (check for triplet ambiguities) if doing raw BPM detection (no expected_bpm) with 'normalize'.
    Also extracts actual beat timestamps from librosa for drift-free rendering.
    Aligns beats to measures by finding the downbeat."""
    if expected_bpm:
        bpm = get_bpm(audio_path, expected_bpm)
    else:
        bpm = get_bpm(audio_path)
        if normalize:
            bpm = normalize_bpm(bpm)

    y, sr = librosa.load(audio_path, sr=None)
    duration = librosa.get_duration(y=y, sr=sr)

    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=bpm, tightness=200)
    beat_times_raw = librosa.frames_to_time(beat_frames, sr=sr)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)
    downbeat_offset = find_downbeat_offset(beat_times_raw, onset_env, onset_times)

    aligned_beat_times = beat_times_raw[downbeat_offset:].tolist()

    return M.Song(bpm, int(duration), audio_path, aligned_beat_times)

def get_beat_intensities(beat_times: np.ndarray, onset_times: np.ndarray, onset_env: np.ndarray) -> list[float]:
    beat_intensities = []
    for i in range(len(beat_times) - 1):
        start_t, end_t = beat_times[i], beat_times[i+1]
        mask = (onset_times >= start_t) & (onset_times < end_t)
        avg_strength = onset_env[mask].mean() if np.any(mask) else 0.0
        beat_intensities.append(avg_strength)
    
    return beat_intensities

def get_section_intensities(beat_intensities : list[float], beats_per_section: int = 16) -> list[float]:
    section_intensities: list[float] = []
    num_sections = len(beat_intensities) // beats_per_section

    for sec_idx in range(num_sections):
        a = sec_idx * beats_per_section
        b = a + beats_per_section
        sec_vals = beat_intensities[a:b]
        section_intensities.append(float(np.mean(sec_vals)) if sec_vals else 0.0)
    
    return section_intensities
    
def analyze_song_intensity(audio_path: str, bpm: float, beats_per_section: int = 16) -> M.IntensityProfile:
    """Given a song's file path, returns the intensity at each beat and
    average intensity per section (defined by "beats_per_section")"""
    y, sr = librosa.load(audio_path, sr=None)

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=bpm)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_intensities = get_beat_intensities(beat_times, onset_times, onset_env)

    #group intensities to sections
    section_intensities: list[float] = get_section_intensities(beat_intensities, beats_per_section)

    return M.IntensityProfile(
        beat_intensities=beat_intensities,
        section_intensities=section_intensities
    )

def get_measure_intensities(beats: list[float], beats_per_measure: int) -> list[float]:
    """Calculates the average measure intensity (defined by 'beats_per_measure')."""
    return [
        sum(beats[i:i + beats_per_measure]) / len(beats[i:i + beats_per_measure])
        for i in range(0, len(beats), beats_per_measure)
    ]

def detect_drops(
    beat_times: list[float],
    audio_path: str,
    bpm: float,
    beats_per_section: int = 8
) -> list[M.DropEvent]:
    """
    Detect multiple drops/climaxes using accurate beat-frame-based section intensities.
    Returns all drops that exceed a dynamic threshold based on the song's intensity profile.
    """
    if len(beat_times) < beats_per_section * 2:
        return []

    y, sr = librosa.load(audio_path, sr=None)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_intensities = get_aggro_beat_intensities(
        np.array(beat_times), onset_times, onset_env
    )

    num_sections = len(beat_intensities) // beats_per_section
    section_intensities: list[float] = []
    section_start_times: list[float] = []

    for sec_idx in range(num_sections):
        beat_start = sec_idx * beats_per_section
        beat_end = beat_start + beats_per_section

        sec_beats = beat_intensities[beat_start:beat_end]
        section_intensities.append(float(np.max(sec_beats)) if sec_beats else 0.0)

        if beat_start < len(beat_times):
            section_start_times.append(beat_times[beat_start])

    if len(section_intensities) < 2:
        return []

    avg_intensity = float(np.mean(section_intensities))
    max_intensity = float(np.max(section_intensities))
    intensity_range = max_intensity - avg_intensity

    if avg_intensity <= 1e-6 or intensity_range <= 1e-6:
        return []

    drop_threshold = avg_intensity + (intensity_range * 0.25)

    drops: list[M.DropEvent] = []
    cooldown_sections = 2
    last_drop_idx = -cooldown_sections

    for i in range(1, len(section_intensities)):
        current = section_intensities[i]
        previous = section_intensities[i - 1]

        jump = current - previous
        jump_ratio = jump / (avg_intensity + 1e-6)

        if (jump_ratio > 0.15 and
            current > drop_threshold and
            i - last_drop_idx >= cooldown_sections):

            intensity_ratio = current / (avg_intensity + 1e-6)

            drops.append(M.DropEvent(
                timestamp=section_start_times[i] if i < len(section_start_times) else 0.0,
                intensity=current,
                intensity_ratio=intensity_ratio,
                section_idx=i
            ))

            last_drop_idx = i

    return drops


def detect_loudest_drop(audio_path: str, bpm: float, subdivisions: int = 4) -> Optional[M.DropEvent]:
    """
    Legacy function - detects single loudest drop.
    Use detect_drops() for multiple drops.
    """
    y, sr = librosa.load(audio_path, sr=None)

    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=bpm)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    drops = detect_drops(beat_times, audio_path, bpm)
    return drops[0] if drops else None

def get_sb_times(beat_times : np.ndarray, n : int = 4) -> list[float]:
    """
    Returns a list of times of beats which each beat cut into 'n' subdivisions. 
    
    If subdivisions == 4, a list with four values per beat for each beat in beat_times
    would be given.
    """
    #separates onset_times into sixteenth note intervals 
    if not beat_times.any():
        return []

    sb_times = []
    
    for i in range(len(beat_times) - 1):
        t0, t1 = beat_times[i], beat_times[i + 1]
        for k in range(n):
            sub_t = t0 + (k / n) * (t1 - t0)
            sb_times.append(sub_t)
    
    return sb_times
    
def beat_intensity_at_time(t, onset_env, onset_times, window=0.05):
    """Fetches the beat intensity around interval 'window' of time 't'"""
    mask = (onset_times >= t - window) & (onset_times <= t + window)
    return float(onset_env[mask].mean()) if np.any(mask) else 0.0
    
def convert_to_measure_intensities(beat_intensities: list[float]) -> list[float]:
    """
    Returns average measure intensities for all measures (BEATS_PER_MEASURE) 
    in beat_intensities. Discards remainder.
    """
    if not beat_intensities:
        return []
    
    measure_intensities : list[float] = []
    current_measure_intensity = 0

    for i, intensity in enumerate(beat_intensities):
        if i % C.BEATS_PER_MEASURE == 0:
            measure_intensities.append(current_measure_intensity / C.BEATS_PER_MEASURE)
            current_measure_intensity = 0
        
        current_measure_intensity += intensity

    return measure_intensities

    # what if there is an incomplete measure

def get_sb_intensities(sb_times, onset_env, onset_times, window : float = 0.05) -> list[float]:
    """
    Returns the all sub_beat_intensities around 'window' of each sub-beat. 
    A sub-beat has each beat in 'beat_times' cut into 'n' subdivisions
    """
    sb_intensities : list[float] = []

    if not sb_times:
        return []
    
    for t in sb_times:
        intensity = beat_intensity_at_time(t, onset_env, onset_times, window)
        sb_intensities.append(intensity)
    
    return sb_intensities

def group_sb_intensities(beat_intensities: list[float], n: int) -> list[list[float]]:
    """Groups subbeats into groups of size n. Discards remainder, if any."""
    if not beat_intensities:
        return []
    
    group_intensities: list[list[float]] = []
    current_group_intensity: list[float] = []

    for i, intensity in enumerate(beat_intensities):
        if i % n == 0 and i != 0:
            group_intensities.append(current_group_intensity)
            current_group_intensity: list[float] = []
        
        current_group_intensity.append(intensity)

    return group_intensities

def first_greater_than_percentile(lst: list[float], p: float) -> float:
    """Returns minimum value in 'lst' >= the 'p'th percentile.
    Does not preserve order."""
    if not lst:
        raise ValueError("Cannot compute percentile of an empty list")
    
    sorted_lst = sorted(lst)
    
    idx = int(len(lst) * (p/100))
    idx = min(idx, len(lst) - 1)

    return sorted_lst[idx]

def normalize_sb_intensities(
        beat_times: np.ndarray, 
        beat_intensities: list[float], 
        onset_env: np.ndarray, 
        onset_times: np.ndarray,
        n: int = 4 # sixteen notes
    ) -> list[M.SubBeatInfo]:
    """
    Splits each beat_times into n slices (sub-beats). 
    
    Returns a list for all sub-beats, each with:
    - sub-beat timestamp
    - raw intensity
    - normalized level (e.g WEAK, MEDIUM, STRONG)
    """
    if not beat_intensities:
        return []
    
    sb_times = get_sb_times(beat_times, n)
    sb_intensities = get_sb_intensities(sb_times, onset_env, onset_times)
    group_intensities = group_sb_intensities(sb_intensities, C.BEATS_PER_MEASURE * n) # group into measures

    all_sb_info: list[M.SubBeatInfo] = []
    sb_index = 0

    for i, group in enumerate(group_intensities):
        if not group:
            continue
        
        strong_threshold = first_greater_than_percentile(group, C.STRONG_INTENSITY_THRESHOLD)
        medium_threshold = first_greater_than_percentile(group, C.MEDIUM_INTENSITY_THRESHOLD)

        for intensity in group:
            curr_measure_subbeats = group_intensities[i]

            if intensity >= strong_threshold:
                level = M.SubBeatIntensity.STRONG
            elif intensity >= medium_threshold:
                level = M.SubBeatIntensity.MEDIUM
            else:
                level = M.SubBeatIntensity.WEAK # add empty for silence?
            
            time = sb_times[sb_index]
            sb_index += 1

            sb_info = M.SubBeatInfo(time, intensity, level)
            all_sb_info.append(sb_info)
    
    return all_sb_info

def get_sb_info(song: M.Song, subdivisions: int) -> list[M.SubBeatInfo]:
    """Returns (timestamp, raw_intensity, level) for each sub_beat in 'song'.
    Each sub-beat is 1/subdivisions of a beat."""
    y, sr = librosa.load(song.file_path, sr=None)

    if song.beat_times and len(song.beat_times) > 1:
        beat_times = np.array(song.beat_times)
    else:
        _, beat_frames = librosa.beat.beat_track(
            y=y,
            sr=sr,
            start_bpm=song.bpm if song.bpm else 120,
            tightness=200
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_intensities = get_beat_intensities(beat_times, onset_times, onset_env)

    return normalize_sb_intensities(beat_times, beat_intensities, onset_env, onset_times, subdivisions)

def group_info_by_section(sb_info: list[M.SubBeatInfo], subdivisions: int = 4, beats_per_section: int = 16) -> list[list[M.SubBeatInfo]]:
    """Groups sb_info by sections (defined by beats_per_section), given 'subdivisions' per beat.
    Defaults to sixteen notes (4 subdivisions per beat) and 4/4 time signature (16 beats per section)"""
    if not sb_info: 
        return []
    
    total_per_section = subdivisions * beats_per_section

    sections_sb_info: list[list[M.SubBeatInfo]] = []
    current_section: list[M.SubBeatInfo] = []
    current_idx = 0

    for sb in sb_info:
        if current_idx >= total_per_section:
            sections_sb_info.append(current_section)
            current_idx = 0
            current_section = []
        
        current_section.append(sb)
        current_idx += 1
    
    if current_section:
        sections_sb_info.append(current_section)

    return sections_sb_info

def filter_sb_info(sb_info: list[M.SubBeatInfo], level: M.SubBeatIntensity) -> list[M.SubBeatInfo]:
    """Returns all intensities in sb_info that matches level"""
    return [i for i in sb_info if i.level == level]

def num_of_level(sb_info: list[M.SubBeatInfo], level: M.SubBeatIntensity) -> int:
    """Returns the number of sub-beats in sb_info that match 'level'"""
    return len(filter_sb_info(sb_info, level))

def classify_pace(audio_path: str, bpm: float) -> M.PaceProfile:
    """
    Analyze audio features to classify song pace and compute scroll multiplier.

    Uses:
    - BPM
    - onset density (rhythmic activity)
    - intensity (loudness)
    - intensity variance (dynamic range)

    Returns PaceProfile with pace_score in [0, 1]
    """
    y, sr = librosa.load(audio_path, sr=None)
    duration = librosa.get_duration(y=y, sr=sr)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    onset_density = len(onset_times) / duration if duration > 0 else 0.0

    avg_intensity = float(np.mean(onset_env)) if len(onset_env) > 0 else 0.0
    intensity_variance = float(np.var(onset_env)) if len(onset_env) > 0 else 0.0

    bpm_score = np.clip((bpm - 70) / 150, 0, 1)
    density_score = np.clip((onset_density - 1.2) / 6.0, 0, 1)
    intensity_score = np.clip(avg_intensity / 40.0, 0, 1)
    variance_score = np.clip(intensity_variance / 300.0, 0, 1)

    pace_score = float(
        bpm_score * 0.25 +
        density_score * 0.45 +
        intensity_score * 0.15 +
        variance_score * 0.15
    )

    scroll_multiplier = 0.75 + (pace_score * 0.75)

    return M.PaceProfile(
        bpm=bpm,
        onset_density=onset_density,
        avg_intensity=avg_intensity,
        intensity_variance=intensity_variance,
        pace_score=pace_score,
        scroll_multiplier=scroll_multiplier
    )

def get_aggro_beat_intensities(beat_times, onset_times, onset_env):
    intensities = []

    for i in range(len(beat_times) - 1):
        start_t, end_t = beat_times[i], beat_times[i + 1]
        mask = (onset_times >= start_t) & (onset_times < end_t)

        if np.any(mask):
            val = float(np.max(onset_env[mask]))
        else:
            val = 0.0

        intensities.append(val)

    return intensities

def calculate_scroll_tiers(
    audio_path: str,
    bpm: float,
    pace_score: float,
    aligned_beat_times: list[float],
    beats_per_section: int = 8,
) -> list[tuple[float, float, float]]:
    """
    Break the song into sections and assign each a base scroll multiplier
    based on its intensity tier (low/med/high/peak).

    Returns list of (start_time, end_time, scroll_multiplier).
    """
    if len(aligned_beat_times) < beats_per_section * 2:
        return []

    y, sr = librosa.load(audio_path, sr=None)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_times = np.array(aligned_beat_times)
    beat_intensities = get_aggro_beat_intensities(beat_times, onset_times, onset_env)

    num_sections = len(beat_intensities) // beats_per_section
    if num_sections < 2:
        return []

    section_intensities = []
    section_times = []
    for sec_idx in range(num_sections):
        beat_start = sec_idx * beats_per_section
        beat_end = beat_start + beats_per_section
        sec_beats = beat_intensities[beat_start:beat_end]
        section_intensities.append(float(np.mean(sec_beats)) if sec_beats else 0.0)
        start_t = float(beat_times[beat_start])
        end_t = float(beat_times[min(beat_end, len(beat_times) - 1)])
        section_times.append((start_t, end_t))

    sorted_vals = sorted(section_intensities)
    n = len(sorted_vals)
    p25 = sorted_vals[int(n * 0.25)]
    p50 = sorted_vals[int(n * 0.50)]
    p80 = sorted_vals[int(n * 0.80)]

    # map each section's intensity to a scroll multiplier proportional to where it falls in the intensity range
    min_intensity = sorted_vals[0]
    max_intensity = sorted_vals[-1]
    intensity_range = max_intensity - min_intensity
    if intensity_range < 1e-6:
        intensity_range = 1.0

    spread = 0.15 + pace_score * 0.15
    tiers = []
    for i, intensity in enumerate(section_intensities):
        normalized = (intensity - min_intensity) / intensity_range
        mult = (1.0 - spread * 0.6) + normalized * (spread * 1.6)

        tiers.append((section_times[i][0], section_times[i][1], mult))

    return tiers


def calculate_energy_shifts(
    audio_path: str,
    bpm: float,
    pace_score: float,
    aligned_beat_times: list[float],
) -> list[M.SectionEnergyShift]:
    """
    Measure-level (4 beats) energy shift detection.
    Core rule: 2+ consecutive measures each louder than the previous → speed-up.
    A measure that drops below the previous → ends the run (and may trigger slowdown).
    """
    beats_per_measure = 4

    if len(aligned_beat_times) < beats_per_measure * 4:
        return []

    y, sr = librosa.load(audio_path, sr=None)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_times = np.array(aligned_beat_times)
    beat_intensities = get_aggro_beat_intensities(beat_times, onset_times, onset_env)

    num_measures = len(beat_intensities) // beats_per_measure
    measure_intensities: list[float] = []
    measure_times: list[tuple[float, float]] = []

    for m in range(num_measures):
        bs = m * beats_per_measure
        be = bs + beats_per_measure
        beats = beat_intensities[bs:be]
        measure_intensities.append(float(np.mean(beats)) if beats else 0.0)
        start_t = float(beat_times[bs])
        end_t = float(beat_times[min(be, len(beat_times) - 1)])
        measure_times.append((start_t, end_t))

    if len(measure_intensities) < 3:
        return []

    avg_intensity = float(np.mean(measure_intensities))
    if avg_intensity <= 1e-6:
        return []

    measure_duration = (60.0 / bpm) * beats_per_measure

    shifts: list[M.SectionEnergyShift] = []

    # --- Pass 1: rising-run detection (2+ measures each louder than previous)
    run_start = -1
    run_length = 0

    def _emit_speedup(start_idx: int, end_idx: int):
        """Emit a speed-up shift from start_idx to end_idx (inclusive)."""
        run_len = end_idx - start_idx + 1
        if run_len < 2:
            return
        # Magnitude proportional to total intensity rise across the run
        total_rise = measure_intensities[end_idx] - measure_intensities[start_idx]
        rise_ratio = total_rise / (avg_intensity + 1e-6)
        peak_ratio = measure_intensities[end_idx] / (avg_intensity + 1e-6)
        magnitude = max(rise_ratio, peak_ratio - 1.0, 0.05)
        # Longer runs get a bonus
        run_bonus = 1.0 + (run_len - 2) * 0.1
        magnitude *= run_bonus
        magnitude = magnitude ** (0.9 + 0.3 * pace_score)

        modifier = 1.0 + magnitude * (1.0 + 1.2 * pace_score)
        modifier = float(np.clip(modifier, 1.1, 2.2))

        shifts.append(M.SectionEnergyShift(
            section_idx=start_idx,
            start_time=measure_times[start_idx][0],
            end_time=measure_times[end_idx][1],
            energy_delta=float(rise_ratio),
            scroll_modifier=modifier,
        ))

    # ("no noticeable change" = drop less than 5% of average intensity)
    dip_tolerance = avg_intensity * 0.05
    consecutive_dips = 0
    max_consecutive_dips = 1  # 1 dip before end

    for i in range(1, len(measure_intensities)):
        drop = measure_intensities[i - 1] - measure_intensities[i]
        if drop <= dip_tolerance:
            if run_start < 0:
                run_start = i - 1
                consecutive_dips = 0
            run_length = i - run_start + 1
            consecutive_dips = 0
        else:
            if run_start >= 0:
                consecutive_dips += 1
                if consecutive_dips <= max_consecutive_dips:
                    run_length = i - run_start + 1
                else:
                    end_idx = i - consecutive_dips - 1
                    if end_idx >= run_start and (end_idx - run_start + 1) >= 2:
                        _emit_speedup(run_start, end_idx)
                    run_start = -1
                    run_length = 0
                    consecutive_dips = 0
            else:
                consecutive_dips = 0

    if run_length >= 2 and run_start >= 0:
        end_idx = len(measure_intensities) - 1 - consecutive_dips
        if end_idx >= run_start and (end_idx - run_start + 1) >= 2:
            _emit_speedup(run_start, end_idx)

    # STANDALONE SLOWDONWS
    slow_threshold = 0.10 - pace_score * 0.04
    slow_threshold = max(0.04, slow_threshold)

    for i in range(1, len(measure_intensities)):
        delta = (measure_intensities[i] - measure_intensities[i - 1]) / avg_intensity
        if delta < -slow_threshold:
            slow_mag = abs(delta) ** 1.2
            slow_mod = 1.0 - slow_mag * (0.6 + 0.6 * pace_score)
            slow_mod = float(np.clip(slow_mod, 0.4, 0.92))
            shifts.append(M.SectionEnergyShift(
                section_idx=i,
                start_time=measure_times[i][0],
                end_time=measure_times[i][1],
                energy_delta=float(delta),
                scroll_modifier=slow_mod,
            ))

    # climax detection
    sorted_m = sorted(measure_intensities)
    p75 = sorted_m[int(len(sorted_m) * 0.75)]

    covered_ranges = [(s.start_time, s.end_time) for s in shifts if s.energy_delta > 0]

    climax_indices = [
        i for i in range(len(measure_intensities))
        if measure_intensities[i] >= p75
    ]
    climax_groups: list[list[int]] = []
    cg: list[int] = []
    for idx in climax_indices:
        if cg and idx > cg[-1] + 1:
            climax_groups.append(cg)
            cg = [idx]
        else:
            cg.append(idx)
    if cg:
        climax_groups.append(cg)

    for group in climax_groups:
        if len(group) < 2:
            continue
        g_start = measure_times[group[0]][0]
        g_end = measure_times[group[-1]][1]
        if any(cs <= g_start and ce >= g_end for cs, ce in covered_ranges):
            continue
        group_avg = float(np.mean([measure_intensities[i] for i in group]))
        ratio = group_avg / (avg_intensity + 1e-6)
        mod = 1.0 + (ratio - 1.0) * (1.0 + 1.0 * pace_score)
        mod = float(np.clip(mod, 1.15, 2.0))
        shifts.append(M.SectionEnergyShift(
            section_idx=group[0],
            start_time=g_start,
            end_time=g_end,
            energy_delta=float(ratio - 1.0),
            scroll_modifier=mod,
        ))

    shifts.sort(key=lambda s: s.start_time)
    min_gap = measure_duration * (1.5 - pace_score * 0.5)
    if len(shifts) > 1:
        filtered = [shifts[0]]
        for s in shifts[1:]:
            if s.start_time - filtered[-1].end_time >= min_gap:
                filtered.append(s)
            elif s.energy_delta > 0 and (filtered[-1].energy_delta <= 0 or s.scroll_modifier > filtered[-1].scroll_modifier):
                filtered[-1] = s
            elif s.energy_delta <= 0 and filtered[-1].energy_delta <= 0 and abs(s.energy_delta) > abs(filtered[-1].energy_delta):
                filtered[-1] = s
        shifts = filtered

    return shifts


def detect_dual_side_sections(
    audio_path: str,
    bpm: float,
    pace_score: float,
    aligned_beat_times: list[float],
    beats_per_section: int = 8
) -> list[M.DualSideSection]:
    """
    Detect sustained high-intensity sections where dual-side mode (plane mode) should activate.
    These are the most intense multi-section periods in the song.
    Returns sections lasting at least 2 sections where intensity is consistently high.
    """
    if len(aligned_beat_times) < beats_per_section * 4:
        return []

    y, sr = librosa.load(audio_path, sr=None)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_times = np.array(aligned_beat_times)
    beat_intensities = get_aggro_beat_intensities(beat_times, onset_times, onset_env)

    num_sections = len(beat_intensities) // beats_per_section
    section_intensities: list[float] = []
    section_times: list[tuple[float, float]] = []

    for sec_idx in range(num_sections):
        beat_start = sec_idx * beats_per_section
        beat_end = beat_start + beats_per_section

        sec_beats = beat_intensities[beat_start:beat_end]
        section_intensities.append(float(np.mean(sec_beats)) if sec_beats else 0.0)

        start_t = float(beat_times[beat_start]) if beat_start < len(beat_times) else 0.0
        end_t = float(beat_times[min(beat_end, len(beat_times) - 1)])
        section_times.append((start_t, end_t))

    if len(section_intensities) < 4:
        return []

    avg_intensity = float(np.mean(section_intensities))
    max_intensity = float(np.max(section_intensities))

    if avg_intensity <= 1e-6:
        return []

    # only dual-side mode if section significantly above average
    # LOWER THRESHOLD for high-pace songs
    intensity_threshold = avg_intensity + (max_intensity - avg_intensity) * (0.55 - 0.15 * pace_score)

    dual_sections: list[M.DualSideSection] = []

    in_intense = False
    intense_start_idx = -1

    min_duration_sections = 2
    cooldown_sections = max(2, int(4 - pace_score * 2))
    last_end_idx = -cooldown_sections

    for i, intensity in enumerate(section_intensities):
        above_threshold = intensity >= intensity_threshold

        if not in_intense:
            if above_threshold and (i - last_end_idx) >= cooldown_sections:
                in_intense = True
                intense_start_idx = i
        else:
            if intensity < intensity_threshold * 0.85:
                duration = i - intense_start_idx
                if duration >= min_duration_sections:
                    start_time = section_times[intense_start_idx][0]
                    end_time = section_times[i - 1][1]

                    period_intensities = section_intensities[intense_start_idx:i]
                    avg_period = float(np.mean(period_intensities))
                    intensity_ratio = avg_period / (avg_intensity + 1e-6)

                    dual_sections.append(M.DualSideSection(
                        start_time=start_time,
                        end_time=end_time,
                        intensity_ratio=intensity_ratio
                    ))

                    last_end_idx = i

                in_intense = False

    if in_intense and intense_start_idx >= 0:
        duration = len(section_intensities) - intense_start_idx
        if duration >= min_duration_sections:
            start_time = section_times[intense_start_idx][0]
            end_time = section_times[-1][1]

            period_intensities = section_intensities[intense_start_idx:]
            avg_period = float(np.mean(period_intensities))
            intensity_ratio = avg_period / (avg_intensity + 1e-6)

            dual_sections.append(M.DualSideSection(
                start_time=start_time,
                end_time=end_time,
                intensity_ratio=intensity_ratio
            ))

    return dual_sections




def detect_hold_regions(
    audio_path: str,
    beat_times: list[float],
    bpm: float,
    min_hold_secs: float = 0.30,
    max_hold_secs: float = 2.0,
) -> list[tuple[float, float]]:
    """
    Detect regions where a note is sustained (flat amplitude after an onset).

    Algorithm:
    1. Compute RMS energy in 50ms frames (25ms hop).
    2. At each detected onset, check if RMS stays within ±12% of its peak
       for at least min_hold_secs (amplitude flatness).
    3. End the hold when RMS drops to ≤ 60% of peak (≈ -4.5 dB decay).
    4. Snap hold duration to the nearest 0.5 beats.

    Returns list of (onset_time, snapped_hold_duration) tuples.
    """
    if not beat_times or bpm <= 0:
        return []

    y, sr = librosa.load(audio_path, sr=None)

    # RMS energy frames (50ms frames, 25ms hop)
    hop_length = max(1, int(sr * 0.025))
    frame_length = hop_length * 2
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

    # Onset detection
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env, backtrack=True)
    onset_times_arr = librosa.frames_to_time(onset_frames, sr=sr)

    beat_duration = 60.0 / bpm
    hold_regions: list[tuple[float, float]] = []
    min_gap_between_holds = beat_duration  # holds must be at least 1 beat apart

    last_hold_end = -float('inf')

    for onset_t in onset_times_arr:
        if onset_t < last_hold_end + min_gap_between_holds:
            continue

        # Start index: first RMS frame at or after the onset
        start_idx = int(np.searchsorted(rms_times, onset_t))
        if start_idx >= len(rms) - 4:
            continue

        # Reference amplitude: max RMS in first ~75ms after onset
        ref_window = max(1, int(0.075 / 0.025))  # 3 frames = 75ms
        ref_amp = float(np.max(rms[start_idx: start_idx + ref_window]))
        if ref_amp < 1e-5:
            continue

        # Amplitude thresholds
        end_threshold = ref_amp * 0.60   # -4.5 dB decay = end of hold
        variance_threshold = 0.25        # std / ref_amp must stay below this

        # Find how long amplitude stays sustained
        max_end_idx = int(np.searchsorted(rms_times, onset_t + max_hold_secs))
        max_end_idx = min(max_end_idx, len(rms) - 1)

        sustained_end_idx = start_idx
        for j in range(start_idx + 1, max_end_idx + 1):
            if rms[j] < end_threshold:
                break
            # rolling std check over last ~75ms (3 frames)
            window_slice = rms[max(start_idx, j - 2): j + 1]
            if len(window_slice) >= 2:
                std_ratio = float(np.std(window_slice)) / (ref_amp + 1e-8)
                if std_ratio > variance_threshold:
                    break
            sustained_end_idx = j

        raw_duration = rms_times[sustained_end_idx] - onset_t
        if raw_duration < min_hold_secs:
            continue

        # Snap hold duration to nearest 0.5 beat, minimum 0.5 beat
        beats = raw_duration / beat_duration
        snapped_beats = max(0.5, round(beats * 2) / 2)
        snapped_dur = snapped_beats * beat_duration

        hold_regions.append((float(onset_t), float(snapped_dur)))
        last_hold_end = onset_t + snapped_dur

    return hold_regions


def get_beat_onset_strengths(
    audio_path: str,
    aligned_beat_times: list[float],
) -> list[float]:
    """
    Return normalised (0-1) low-frequency onset strength at each beat time, then tries
    to isolate drums/base through mel spectrogram by keeping only bins below 200 hz.

    Finds percussive strengths throughout the song.

    """
    if len(aligned_beat_times) < 2:
        return []

    y, sr = librosa.load(audio_path, sr=None)

    # mel spectrogram
    n_mels = 128
    S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=n_mels)

    mel_freqs = librosa.mel_frequencies(n_mels=n_mels, fmax=sr / 2)
    low_cutoff = 200
    low_bins = int(np.searchsorted(mel_freqs, low_cutoff))
    low_bins = max(low_bins, 1)  # at least one bin

    S_low = S.copy()
    S_low[low_bins:, :] = 0

    onset_env = librosa.onset.onset_strength(S=librosa.power_to_db(S_low), sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    strengths: list[float] = []
    window = 0.04
    for bt in aligned_beat_times:
        mask = (onset_times >= bt - window) & (onset_times <= bt + window)
        if np.any(mask):
            strengths.append(float(np.max(onset_env[mask])))
        else:
            strengths.append(0.0)

    max_s = max(strengths) if strengths else 1.0
    if max_s <= 1e-6:
        return [0.0] * len(strengths)

    return [s / max_s for s in strengths]


def detect_shake_sections( #idk if im gonna use this
    audio_path: str,
    bpm: float,
    aligned_beat_times: list[float],
    beats_per_section: int = 8,
    threshold_factor: float = 0.3,
) -> list[tuple[float, float, float]]:
    """
    Detect sustained high-intensity sections that should trigger screen shake. 

    Returns list of (start_time, end_time, normalised_strength 0-1).
    Returns empty list if fewer than 2 sections qualify (not intense enough).
    """
    if len(aligned_beat_times) < beats_per_section * 2:
        return []

    y, sr = librosa.load(audio_path, sr=None)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_times = np.array(aligned_beat_times)
    beat_intensities = get_aggro_beat_intensities(beat_times, onset_times, onset_env)

    num_sections = len(beat_intensities) // beats_per_section
    if num_sections < 2:
        return []

    section_intensities: list[float] = []
    section_times: list[tuple[float, float]] = []
    for sec_idx in range(num_sections):
        bs = sec_idx * beats_per_section
        be = bs + beats_per_section
        sec_beats = beat_intensities[bs:be]
        section_intensities.append(float(np.mean(sec_beats)) if sec_beats else 0.0)
        start_t = float(beat_times[bs]) if bs < len(beat_times) else 0.0
        end_t = float(beat_times[min(be, len(beat_times) - 1)])
        section_times.append((start_t, end_t))

    avg_intensity = float(np.mean(section_intensities))
    max_intensity = float(np.max(section_intensities))
    if avg_intensity <= 1e-6 or max_intensity - avg_intensity <= 1e-6:
        return []

    threshold = avg_intensity + (max_intensity - avg_intensity) * threshold_factor

    ranges: list[tuple[float, float, float]] = []
    in_range = False
    range_start = 0.0
    range_strength = 0.0
    range_count = 0

    for i, intensity in enumerate(section_intensities):
        if intensity >= threshold:
            if not in_range:
                in_range = True
                range_start = section_times[i][0]
                range_strength = 0.0
                range_count = 0
            range_strength += intensity
            range_count += 1
        else:
            if in_range:
                avg_str = range_strength / range_count
                norm = min(1.0, avg_str / max_intensity)
                ranges.append((range_start, section_times[i - 1][1], norm))
                in_range = False

    if in_range:
        avg_str = range_strength / range_count
        norm = min(1.0, avg_str / max_intensity)
        ranges.append((range_start, section_times[-1][1], norm))

    if sum(1 for i in section_intensities if i >= threshold) < 2:
        return []

    return ranges


# THEN, DO FREQUENCY CHECK ON THE NORMALIZED SB INTENSITIES. maybe split into categories based off wavelength ranges?
    

    


    
# check if difference between last exceeds THRESHOLD. how to calculate threshold?
# check average measure beat intensity through beat_intensities. 

# def get_peaks() -> finds onset peaks at every sixteenth note that exceed a certain threshold 
# (threshold should be calculated based off avg onset difference i think)

# def get_frequencies(raw_sound: , ) ->
# finds audio frequencies and lists the frequencies in terms of sixteenth notes
# how to normalize frequency ? do we normalize or just categorize (low, medium, high) by raw values?

# i aim to figure out the time slots where words CAN go in the regular beatmap_generator math stuff,
# then use this stuff to kinda map out WHERE in those time slots i can put chars
# this constrains the chars to recommended CPS while ensuring musical feel


def detect_climax_shake_beats(
    pace_score: float,
    aligned_beat_times: list[float],
    scroll_tiers: list[tuple[float, float, float]],
) -> list[tuple[float, float]]:
    """
    Return (beat_time, intensity_0_to_1) pairs for beats that should trigger
    a screen shake. Only used for energetic songs (pace_score >= 0.42).

    Uses the already-computed scroll_tiers so no audio re-load is needed.
    Shakes fire every 2 beats for very energetic songs (pace_score >= 0.62),
    every 4 beats for moderately energetic ones.

    intensity_0_to_1 encodes how loud the section is relative to the loudest
    climax section — drives shake magnitude in the renderer.
    """
    if pace_score < 0.42 or not aligned_beat_times or not scroll_tiers:
        return []

    mults = [m for _, _, m in scroll_tiers]
    if not mults:
        return []

    min_mult = float(min(mults))
    max_mult = float(max(mults))
    mult_range = max_mult - min_mult
    if mult_range < 1e-6:
        return []

    # Threshold: sections above the 60th-percentile multiplier get shakes.
    sorted_mults = sorted(mults)
    p60 = sorted_mults[max(0, int(len(sorted_mults) * 0.60) - 1)]

    stride = 2 if pace_score >= 0.62 else 4   # beats between shake triggers

    result: list[tuple[float, float]] = []
    i = 0
    while i < len(aligned_beat_times):
        bt = aligned_beat_times[i]
        for t_start, t_end, mult in scroll_tiers:
            if t_start <= bt < t_end:
                if mult >= p60:
                    intensity = (mult - min_mult) / mult_range   # 0–1
                    result.append((bt, float(intensity)))
                break
        i += stride

    return result

# get silence