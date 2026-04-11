import os
os.environ['SDL_MOUSE_FOCUS_CLICKTHROUGH'] = '1'

import pygame
from game.engine import Game
from game.models import Level
from game.menu import MenuManager
from game.menu_utils import _load_scores, _save_scores
from game.music import MusicManager


# for some reason, everything takes longer to load now (end of level delay, opening up program delay, playing level delay) -> why?

# shouldnt be able to press on buttons through the canon/custom menu

# noki_bop slightly lagging in loop?

# when scrolling down, begin lerp cropping the bottom of canon / custom tab up by up to 10% (not moving it all, just taking 3% off the bottom and adjusting text as needed)
# and move the horizontal line in which song names and stuff begin disappearing after scrolling down to the new point (where the bottom of canon/custom tab is)
# when scrolling back up and it reaches near the top, it begins lerp stretching again to reverse

# loading animation shouldn't completely stop when reaching the top -> only reach a pretty slow speed

# moreover make the impulse 20% more colored so that the pink, blue, and yellow (new one) colored ones that alternate between are more noticeable.

# end animation + remove word at end of level when typed

# support for different time signatures?

# rainbow bubble themed particles / outline on balls during some time?

# dual mode -> speed up or notes shows up at the end on the left and teleports to the right because dual mode ends.

# make screen "hits" where camera beats every other beat

# recreate speedup/slowdown/bounce mode/dual mode art

#speed up + bounce mode causes the timeline to go in the opposite direction (like timeline is going left and particles are coming from right)

# when in bounce mode and going in reverse, extend the timeline all the way to the left so they can see dots earlier before it comes

#make the .mov bop file png loop for transparency

# pink/light blue/ bubble colorset
# bounce mode section not having notes at all during semi-quiet sections (unsure why)
# can't scroll down in canon level menu with scroll bar

# whenever the session slows down at the end of the level, make sure the zoom stops zooming out after a bit (so it doesnt look like the timeline is being crunched into the hitmarker)

# animated timeline 
# animated circles + spin explode animation when pressed
# red circle animation for wrong

# cat hurt animation (red outline)



# DOUBLE TIMELINE mode timeline splits into two. has 1 second animation of the timeline splitting into two vertically (where one goes up and one goes down) so their vertical center was where the (default mode timeline was). there should be no notes for one measure during entrance just like dual mode
# - first timeline supports left side of keyboard, second timeline right side
# - during double timeline mode, movement is distinct. like it's not just oh you can type normally but 
# have to look at two timelines:
# - VERS 1: double timeline where one timeline is harmony (holding letters in 1-2 letter words for long time 
# while other timeline (otherside of keyboard) types words with letters only on that side). this means that two separate word lists going on for both 
# should alternate between timeslines (like timeline 1 does holding then timeline 2 does holding with word list adjusted 
# as appropriate to only include letters on the "not holding" side for the words)
# - VERS 2: same idea as VERS 1 except no holding. full words show up on each timeline (so not split letters of the same word list)
# where each word only has letters corresponding to its respective side of the keyboard

# SPEAK MODE: 
# uses AI to say the word (girl voice) -> noki meow animation.
# # user has word_duration amount of time to type the entire word, no beats just type it in x time.
# SYMBOL: volume symbol on timeline
# this leads timeline to fade away and noki to lerp to center and camera to zoom in on noki (noki bop 2 animation).
# when it's time for word, ensure word is at least 3 letters long and noki does noki_meow animation. 
# WAIT REAL ANIMATION: they speak, and when it's typed correctly, noki meows and gets rid of red spots crawling towards him (shockwavve)
# this repeats. speak mode has a cooldown AND SHOULD ONLY WORK WITH PARTS OF THE SONG (what parts?) and should last at least 3-4 measures (until the audio appears to "change section") 

# ADD 2 MORE CATS, each with their own hitmarker skin: 
# base cat (current cat) -> red skin. THREE LIVES, normal points
# female cat (white, slender, green eyes) -> (green hitmarker). TWO LIVES, 1.25x points multiplier
# chunk cat (nods head every 2 beats). FIVE LIVES, 0.75x points multipler, slows the song down 

# cat selection mode in main title screen with button under the cat
# incorporate the two cats into beginning animation

SONG_PATH = "assets/audios/"
SONG_NAMES = [
    "Scorpion.mp3",
    "Playful Massacre.mp3", 
    "Decisive Battle.mp3", 
    "Takedown - Huntrix.mp3", 
    "Glitch in your Heart.mp3", 
    "Disturbing the Peace.mp3", 
    "Catch Catch.mp3", 
    "Toby Fox - Finale.mp3",
    "ICARIUS.mp3",
    "Fluffing A Duck.mp3",
    "Malo Kart.mp3",
    "tidalwave.mp3",
    "hustle.mp3",
    "what is love?.mp3"
]

WORD_BANK_1 = ["cat", "test", "me", "rhythm", "beat", "fish", "moon", "derp", "noki", "yeah"]
WORD_BANK_2 = ["cat", "here", "me", "chosen", "beat", "hope", "soul", "true", "love", "stay"]


def main():
    pygame.init()
    info = pygame.display.Info()
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.RESIZABLE)
    pygame.display.set_caption("Key Dash")
    clock = pygame.time.Clock()

    music = MusicManager()

    start_state = "title"
    while True:
        menu = MenuManager(screen, clock, SONG_NAMES, start_state=start_state, music=music)
        result = menu.run()

        if result is None:
            break

        selected, difficulty, word_bank = result

        level = Level(
            word_bank=word_bank,
            song_path=SONG_PATH + SONG_NAMES[selected],
            difficulty=difficulty,
        )

        # ==========================TO DO LIST

        # for the bounce mode mode -> reverse on arrows (bounces off of arrows and reverses) almost like going back in the timeline. the measure bars should also kinda accelerae backwards and reverse too. so not like a reverse, but almost like the hitmarker bounces off (so like momentum in the opposite direction with the measure and beat markers reflecting that)
        # don't move the hitmarker. 
        # make style
        # when skipping a word (like the word is gonna get cut off in the slot, add two "ghost words", blue circles (like sans's fake hits) where the player shouldn't press but complete the word)

        #save all the beatmaps manually of al the existing levels (so they don't have to load).
        # on pause screen, make the timeline and notes freeze not disappear
        # add restart button 

        #on simpler/calmer songs, don't just end words because the melody is slow/sparse, just drag it along for longer (ex. instead of givin "cat", "blob" "yeah" and cutting off half the words, just do "blob" and "cats"). if not many slots available.
        # for complex/faster/more pacey songs/sections, just add the blue stuff

        # on finish, add some finish thing for 2-3 seconds the open 'finish' menu
        
        # add some gradients in the background,
        # add PRESS note animation -> it fades into mist

        #make it to where, on wrong note, the next char isn't immediately deactivated.

        # some speed-ups seem to happen 

        # zoom in mode _> everything becomes bigger (including circles and timeline) -> what does this do? double timeline?

        #timeline rotate
        #EVENTUALLY
        # work on file system, saving files to cloud (so the files are there for that user every time, etc)
        #integrate font
        # doesn't understand climax sections well

        # ===== BUGS
        # doesn't wait until last char is finished in dual section before transitioning back
        # sometimes has ghost letters (skips on its own) (only bounce mode). 
        # sometimes doesn't have grace period when starting dual mode

        # Ariana Grande - Problem ft. Iggy Azalea 
        # words synced to song? is word detection from audio possible?

        music.pause_for_game()
        game = Game(level=level, screen=screen, clock=clock)
        game.run()
        music.resume_from_game()
        start_state = "level_select"

        # Persist top score for this song + difficulty
        song_key = SONG_NAMES[selected]
        scores   = _load_scores()
        prev     = scores.get(song_key, {}).get(difficulty, 0)
        if game.score > prev:
            scores.setdefault(song_key, {})[difficulty] = game.score
            _save_scores(scores)

    pygame.quit()


if __name__ == "__main__":
    main()
