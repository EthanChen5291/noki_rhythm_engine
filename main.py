import pygame
from game.engine import Game
from game.models import Level
from game.menu import MenuManager
from game.music import MusicManager

# concerns

# add ... screen before animation plays. song should wait until animation starts to begin playing. this is so it gives players time to load and get on the window quickly

# add a menu UI -> whenever players click on a level, they see a menu with the difficulty and top score and play button. 
# in the actual levels screen (with all the levels), don't show the difficulty (that'll be toggles in the individual level menus) and just show the rank of the player's best score

# ensure that the main title cat + main title + play button play at 125 bpm after play button is pressed and the player goes back to main title screen

# -- underscore for words not showing up on some words
# -- ghost letters (letters progressing without any input/circles) in ping pong mode
# -- HARD mode causes letter skips 

# animated timeline 
# animated circles + spin explode animation when pressed
# red circle animation for wrong

# cat hurt animation (red outline)
# upload file should not open separate menu -> should just grab file, and when file is grabbed, user can rename on the level screen
# levels menu split between ("Canon") and ("Custom") at the top (where the SONGS text is) -> Canon is the default level list, Custom is uploaded

# HOLD NOTES -> allow some notes to be held. should be snapped to music grid, 
# not interfere with the next note, has a cooldown of 0.2 sec before next. 
# can be at any letter of a sentence for any duration as long as it doesn't interfere

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
    "Glitch in your Heart.mp3", 
    "Disturbing the Peace.mp3", 
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
        
        #make it to where, on wrong note, the next char isn't immediately deactivated.

        # some speed-ups seem to happen 

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

    pygame.quit()


if __name__ == "__main__":
    main()
