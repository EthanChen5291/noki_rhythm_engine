"""
TimelineRenderer — draws the timeline bar, beat grid, mode indicators,
speed arrows, bounce obstacles, and progress bar.
Instantiated and owned by Game; accesses game state via self.game.
"""
import pygame


class TimelineRenderer:

    def __init__(self, game) -> None:
        self.game = game

    # ------------------------------------------------------------------
    # Marker helpers
    # ------------------------------------------------------------------

    def draw_dual_side_marker(self, x: int, timeline_y: int) -> None:
        """Draw a dual-side mode activation marker (two arrows pointing inward)."""
        g = self.game
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
        pygame.draw.polygon(g.screen, left_color, left_points)
        pygame.draw.polygon(g.screen, (255, 255, 255), left_points, 2)

        right_x = x + 15
        right_points = [
            (right_x - arrow_width, center_y),
            (right_x, top_y),
            (right_x, bottom_y),
        ]
        pygame.draw.polygon(g.screen, right_color, right_points)
        pygame.draw.polygon(g.screen, (255, 255, 255), right_points, 2)

    def draw_speed_arrow(self, x: int, timeline_y: int, timeline_height: int, speed_up: bool) -> None:
        """Draw a speed change arrow spanning the full measure line."""
        g = self.game
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
                pygame.draw.polygon(g.screen, arrow_color, points)
                pygame.draw.polygon(g.screen, (255, 255, 255), points, 2)
        else:
            for offset in [-8, 8]:
                points = [
                    (x + arrow_width // 2 + offset, top_y),
                    (x - arrow_width // 2 + offset, center_y),
                    (x + arrow_width // 2 + offset, bottom_y),
                ]
                pygame.draw.polygon(g.screen, arrow_color, points)
                pygame.draw.polygon(g.screen, (200, 220, 255), points, 2)

    def draw_bounce_obstacle(self, x: int, timeline_y: int) -> None:
        """Draw a diamond-shaped bounce obstacle."""
        g = self.game
        size = 12
        points = [
            (x, timeline_y - size),
            (x + size, timeline_y),
            (x, timeline_y + size),
            (x - size, timeline_y),
        ]
        pygame.draw.polygon(g.screen, (255, 80, 200), points)
        pygame.draw.polygon(g.screen, (255, 255, 255), points, 2)

    # ------------------------------------------------------------------
    # Main render call
    # ------------------------------------------------------------------

    def render(
        self,
        current_time: float,
        timeline_y: int,
        timeline_start_x: int,
        timeline_end_x: int,
        hit_marker_x: float,
    ) -> None:
        g = self.game

        # --- timeline bar
        if g._timeline_flash > 0.01:
            r = int(255)
            gr = int(255 * (1.0 - g._timeline_flash))
            b = int(255 * (1.0 - g._timeline_flash))
            timeline_color = (r, gr, b)
            g._timeline_flash *= 0.85
        else:
            timeline_color = (255, 255, 255)
            g._timeline_flash = 0.0

        pygame.draw.line(
            g.screen, timeline_color,
            (timeline_start_x, timeline_y),
            (timeline_end_x, timeline_y), 6,
        )

        _hm_rect = g.hitmarker_img.get_rect(center=(int(hit_marker_x), timeline_y))
        g.screen.blit(g.hitmarker_img, _hm_rect)

        # --- beat grid lines
        beat_times = g.song.beat_times
        lead_in = g.rhythm.lead_in

        for i, beat_time in enumerate(beat_times):
            t = beat_time + lead_in
            time_until = t - current_time
            if g.bounce_active and not g.dual_side_active and g.bounce_reversed:
                x = hit_marker_x - time_until * g.scroll_speed
            else:
                x = hit_marker_x + time_until * g.scroll_speed

            if timeline_start_x <= x <= timeline_end_x:
                if i % 4 == 0:
                    g.screen.blit(g._measureline_img,
                                  g._measureline_img.get_rect(center=(int(x), timeline_y)))
                else:
                    g.screen.blit(g._beatline_img,
                                  g._beatline_img.get_rect(center=(int(x), timeline_y)))

        # --- dual-side mode indicators
        if g.dual_side_visuals_active:
            arrow_size = 15
            arrow_y = timeline_y

            left_arrow_x = timeline_start_x + 30
            pygame.draw.polygon(
                g.screen,
                (100, 200, 255),
                [
                    (left_arrow_x, arrow_y),
                    (left_arrow_x - arrow_size, arrow_y - arrow_size // 2),
                    (left_arrow_x - arrow_size, arrow_y + arrow_size // 2),
                ],
            )

            right_arrow_x = timeline_end_x - 30
            pygame.draw.polygon(
                g.screen,
                (255, 200, 100),
                [
                    (right_arrow_x, arrow_y),
                    (right_arrow_x + arrow_size, arrow_y - arrow_size // 2),
                    (right_arrow_x + arrow_size, arrow_y + arrow_size // 2),
                ],
            )

        # --- dual-side section start markers
        for dual_sec in g.dual_side_sections:
            section_time = dual_sec.start_time + g.rhythm.lead_in
            time_until = section_time - current_time

            if -0.5 < time_until < 5.0:
                marker_x = hit_marker_x + time_until * g.scroll_speed
                if timeline_start_x <= marker_x <= timeline_end_x:
                    self.draw_dual_side_marker(int(marker_x), timeline_y)

        # --- speed change arrows
        timeline_height = 100

        for i, shift in enumerate(g.energy_shifts):
            shift_time = shift.start_time + lead_in
            time_until = shift_time - current_time

            if -0.5 < time_until < 5.0:
                if g.dual_side_active:
                    arrow_from_left = (i % 2 == 1)
                    if arrow_from_left:
                        arrow_x = hit_marker_x - (time_until * g.scroll_speed)
                    else:
                        arrow_x = hit_marker_x + (time_until * g.scroll_speed)
                elif g.bounce_active and g.bounce_reversed:
                    arrow_x = hit_marker_x - time_until * g.scroll_speed
                else:
                    arrow_x = hit_marker_x + time_until * g.scroll_speed

                if timeline_start_x <= arrow_x <= timeline_end_x:
                    speed_up = shift.energy_delta > 0
                    self.draw_speed_arrow(int(arrow_x), timeline_y, timeline_height, speed_up)

        # --- bounce obstacles
        for evt in g.bounce_events:
            evt_time = evt.time + lead_in
            time_until = evt_time - current_time
            if -0.5 < time_until < 5.0:
                if g.bounce_active and g.bounce_reversed:
                    obs_x = hit_marker_x - time_until * g.scroll_speed
                else:
                    obs_x = hit_marker_x + time_until * g.scroll_speed
                if timeline_start_x <= obs_x <= timeline_end_x:
                    self.draw_bounce_obstacle(int(obs_x), timeline_y)

        # --- progress bar
        progress_bar_x = timeline_start_x - 30
        progress_bar_height = 200
        progress_bar_width = 8
        progress_bar_top = timeline_y - progress_bar_height // 2
        progress_bar_bottom = timeline_y + progress_bar_height // 2

        total_notes = len(g.rhythm.beat_map)
        level_progress = min(1.0, g.rhythm.char_event_idx / total_notes) if total_notes > 0 else 0.0

        pygame.draw.rect(
            g.screen,
            (40, 40, 40),
            (progress_bar_x - progress_bar_width // 2, progress_bar_top,
             progress_bar_width, progress_bar_height),
            border_radius=4,
        )

        filled_height = int(progress_bar_height * level_progress)
        if filled_height > 0:
            pygame.draw.rect(
                g.screen,
                (100, 200, 255),
                (progress_bar_x - progress_bar_width // 2,
                 progress_bar_bottom - filled_height,
                 progress_bar_width, filled_height),
                border_radius=4,
            )
