"""
NoteRenderer — draws beat markers, hold tails, and spawns hold particles.
Instantiated and owned by Game; accesses game state via self.game.
"""
import pygame
import time
from . import constants as C


class NoteRenderer:

    def __init__(self, game) -> None:
        self.game = game

    def render(
        self,
        current_time: float,
        timeline_y: int,
        timeline_start_x: int,
        timeline_end_x: int,
        hit_marker_x: float,
    ) -> None:
        g = self.game
        lead_in = g.rhythm.lead_in

        song_time = current_time - lead_in
        dual_exit_grace = g.beat_duration * 2
        in_dual_exit_grace = (not g.dual_side_active
                              and song_time - g._last_dual_end_time < dual_exit_grace)

        for note_idx, event in enumerate(g.rhythm.beat_map):
            time_until_hit = event.timestamp - current_time

            # Active hold: render unconditionally outside visibility window
            is_active_hold = (g.rhythm._active_hold is event)
            if is_active_hold and event.hold_duration > 0:
                note_from_left = event.from_left
                if g.bounce_active and not g.dual_side_active:
                    note_reversed = False
                    for bevt in g.bounce_events:
                        if bevt.time <= event.timestamp - g.rhythm.lead_in:
                            note_reversed = not note_reversed
                        else:
                            break
                    note_from_left = note_reversed

                hold_end_time = event.timestamp + event.hold_duration
                remaining_dur = max(0.0, hold_end_time - current_time)
                remaining_px = int(remaining_dur * g.scroll_speed)
                radius = 14
                if remaining_px > 0:
                    tail_surf = pygame.Surface((remaining_px, radius * 2), pygame.SRCALPHA)
                    pygame.draw.rect(tail_surf, (255, 220, 60, 200),
                                     (0, 0, remaining_px, radius * 2),
                                     border_radius=radius)
                    if note_from_left:
                        g.screen.blit(tail_surf, (int(hit_marker_x) - remaining_px, timeline_y - radius))
                    else:
                        g.screen.blit(tail_surf, (int(hit_marker_x), timeline_y - radius))

                # Spawn hold particles at the hitmarker
                if int(time.perf_counter() * 30) % 2 == 0:
                    import random as _rnd
                    for _ in range(2):
                        g._hold_particles.append({
                            'x': float(hit_marker_x) + _rnd.uniform(-12, 12),
                            'y': float(timeline_y) + _rnd.uniform(-14, 14),
                            'vx': _rnd.uniform(-130, 130),
                            'vy': _rnd.uniform(-160, 40),
                            'alpha': 220.0,
                            'radius': _rnd.uniform(3.75, 7.5),
                            'color': (255, 210, 60),
                        })
                    for _ in range(3):
                        g._hold_particles.append({
                            'x': float(hit_marker_x) + _rnd.uniform(-10, 10),
                            'y': float(timeline_y) + _rnd.uniform(-12, 12),
                            'vx': _rnd.uniform(-220, 220),
                            'vy': _rnd.uniform(-260, 60),
                            'alpha': 190.0,
                            'radius': _rnd.uniform(1.5, 3.3),
                            'color': (240, 240, 255),
                        })
                continue

            if -0.75 < time_until_hit < 5.0:
                if in_dual_exit_grace and not event.hit and time_until_hit < 0:
                    continue

                note_from_left = event.from_left

                if g.bounce_active and not g.dual_side_active:
                    if time_until_hit < 0 and not event.hit:
                        continue
                    note_reversed = False
                    for bevt in g.bounce_events:
                        if bevt.time <= event.timestamp - g.rhythm.lead_in:
                            note_reversed = not note_reversed
                        else:
                            break
                    note_from_left = note_reversed

                if note_from_left:
                    marker_x = hit_marker_x - (time_until_hit * g.scroll_speed)
                else:
                    marker_x = hit_marker_x + (time_until_hit * g.scroll_speed)

                if timeline_start_x <= marker_x <= timeline_end_x:
                    if event.char != "" and not event.hit:
                        is_missed = time_until_hit < 0
                        radius = 14

                        if g.dual_side_active and is_missed:
                            if note_idx not in g.missed_note_shockwaves:
                                g.trigger_miss_shockwave(int(marker_x), timeline_y)
                                g.missed_note_shockwaves.add(note_idx)
                            continue

                        color = C.MISSED_COLOR if is_missed else C.COLOR

                        if event.hold_duration > 0:
                            hold_px = int(event.hold_duration * g.scroll_speed)
                            hold_rect_h = radius * 2

                            if note_from_left:
                                hold_rect_x = int(marker_x) - hold_px
                                hold_rect_w = hold_px
                                if hold_rect_x < timeline_start_x:
                                    clip = timeline_start_x - hold_rect_x
                                    hold_rect_x = timeline_start_x
                                    hold_rect_w -= clip
                            else:
                                hold_rect_x = int(marker_x)
                                hold_rect_w = hold_px
                                if hold_rect_x + hold_rect_w > timeline_end_x:
                                    hold_rect_w = timeline_end_x - hold_rect_x

                            if hold_rect_w > 0:
                                hold_surf = pygame.Surface((hold_rect_w, hold_rect_h), pygame.SRCALPHA)
                                hold_color = (255, 80, 80, 160) if is_missed else (255, 200, 40, 140)
                                pygame.draw.rect(hold_surf, hold_color,
                                                 (0, 0, hold_rect_w, hold_rect_h),
                                                 border_radius=radius)
                                g.screen.blit(hold_surf, (hold_rect_x, timeline_y - radius))

                        pygame.draw.circle(
                            g.screen,
                            color,
                            (int(marker_x), timeline_y),
                            radius,
                        )
