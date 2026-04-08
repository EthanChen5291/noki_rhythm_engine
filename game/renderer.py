"""
RendererMixin — all draw/render methods for the Game class.
Mixed into Game via multiple inheritance; all methods use `self` freely.
"""
import pygame
import math
import time
from . import constants as C
from .menu_utils import _FONT


class RendererMixin:

    def draw_dual_side_marker(self, x: int, timeline_y: int):
        """Draw a dual-side mode activation marker (two arrows pointing inward)."""
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
        """Draw a speed change arrow spanning the full measure line."""
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

    def get_next_word(self) -> str | None:
        """Get the next word that will be typed after current word completes."""
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
        position: str,
        transition_progress: float,
        is_current: bool,
        fading_out: bool = False,
        adjacent_word_width: int = 0,
        y_offset: float = 0
    ):
        """Draw a word with 3D carousel rotation animation."""
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

        radius = 350
        center_offset = base_char_spacing / 2
        center_x = self.screen.get_width() // 2 + center_offset
        center_y = 180 + y_offset

        base_spacing = 100

        if position == 'center':
            target_angle = 0
            target_scale = 1.0
            target_alpha = 255
            target_color = (255, 255, 255)
            target_char_spacing = base_char_spacing
        elif position == 'right':
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
        """Draw the current word as a large, faded background element during dual-side mode."""
        if not word:
            return

        font_size = 180
        bg_font = pygame.font.Font(_FONT, font_size)
        bg_color = (60, 60, 60)

        char_spacing = 120
        total_width = len(word) * char_spacing
        start_x = (self.screen.get_width() - total_width) // 2
        center_y = self.screen.get_height() // 2 - 50

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

        transition_duration = 0.3
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

        # --- draw timeline
        timeline_y = 380
        if self._timeline_shake_offset > 0.3:
            timeline_y += int(self._timeline_shake_offset)
            self._timeline_shake_offset *= -0.5
        else:
            self._timeline_shake_offset = 0.0

        timeline_start_x = int(self.timeline_current_start)
        timeline_end_x = int(self.timeline_current_end)
        hit_marker_x = self.hit_marker_current_x

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

        _hm_rect = self.hitmarker_img.get_rect(center=(int(hit_marker_x), timeline_y))
        self.screen.blit(self.hitmarker_img, _hm_rect)

        # --- beat grid lines
        beat_times = self.song.beat_times
        lead_in = self.rhythm.lead_in

        for i, beat_time in enumerate(beat_times):
            t = beat_time + lead_in
            time_until = t - current_time
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

        # --- dual-side mode indicators
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

        # --- dual-side section start markers
        for dual_sec in self.dual_side_sections:
            section_time = dual_sec.start_time + self.rhythm.lead_in
            time_until = section_time - current_time

            if -0.5 < time_until < 5.0:
                marker_x = hit_marker_x + time_until * self.scroll_speed

                if timeline_start_x <= marker_x <= timeline_end_x:
                    self.draw_dual_side_marker(int(marker_x), timeline_y)

        # --- speed change arrows
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

        # --- bounce obstacles
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

        # --- beat markers / notes
        song_time = current_time - lead_in
        dual_exit_grace = self.beat_duration * 2
        in_dual_exit_grace = (not self.dual_side_active
                              and song_time - self._last_dual_end_time < dual_exit_grace)

        for note_idx, event in enumerate(self.rhythm.beat_map):
            time_until_hit = event.timestamp - current_time

            # Active hold: render unconditionally outside visibility window
            is_active_hold = (self.rhythm._active_hold is event)
            if is_active_hold and event.hold_duration > 0:
                note_from_left = False
                if self.dual_side_active and event.char_idx >= 0:
                    note_from_left = (event.char_idx % 2 == 1)
                if self.bounce_active and not self.dual_side_active:
                    note_reversed = False
                    for bevt in self.bounce_events:
                        if bevt.time <= event.timestamp - self.rhythm.lead_in:
                            note_reversed = not note_reversed
                        else:
                            break
                    note_from_left = note_reversed

                hold_end_time = event.timestamp + event.hold_duration
                remaining_dur = max(0.0, hold_end_time - current_time)
                remaining_px  = int(remaining_dur * self.scroll_speed)
                radius = 14
                if remaining_px > 0:
                    tail_surf = pygame.Surface((remaining_px, radius * 2), pygame.SRCALPHA)
                    pygame.draw.rect(tail_surf, (255, 220, 60, 200),
                                     (0, 0, remaining_px, radius * 2),
                                     border_radius=radius)
                    if note_from_left:
                        self.screen.blit(tail_surf, (int(hit_marker_x) - remaining_px, timeline_y - radius))
                    else:
                        self.screen.blit(tail_surf, (int(hit_marker_x), timeline_y - radius))
                # Spawn hold particles at the hitmarker
                if int(time.perf_counter() * 30) % 2 == 0:
                    import random as _rnd
                    for _ in range(2):
                        self._hold_particles.append({
                            'x': float(hit_marker_x) + _rnd.uniform(-12, 12),
                            'y': float(timeline_y) + _rnd.uniform(-14, 14),
                            'vx': _rnd.uniform(-130, 130),
                            'vy': _rnd.uniform(-160, 40),
                            'alpha': 220.0,
                            'radius': _rnd.uniform(3.75, 7.5),
                            'color': (255, 210, 60),
                        })
                    for _ in range(3):
                        self._hold_particles.append({
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

                note_from_left = False
                if self.dual_side_active and event.char_idx >= 0:
                    note_from_left = (event.char_idx % 2 == 1)

                if self.bounce_active and not self.dual_side_active:
                    if time_until_hit < 0 and not event.hit:
                        continue
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

                        if event.hold_duration > 0:
                            hold_px = int(event.hold_duration * self.scroll_speed)
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
                                self.screen.blit(hold_surf, (hold_rect_x, timeline_y - radius))

                        pygame.draw.circle(
                            self.screen,
                            color,
                            (int(marker_x), timeline_y),
                            radius
                        )

        # --- progress bar
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
