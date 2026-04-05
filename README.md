<img src="assets/images/noki_logo.png" alt="Noki Preview" width="400">

## What is this?

**noki** is a rhythm game engine that generates playable typing levels from:
- any audio file
- any list of words

Instead of hand-designing levels, the system analyzes the music and constructs a beatmap automatically.

---

### Prerequisites
Before running noki, ensure you have the following installed:

- Python 3.8+
- pip (Python package manager)
- FFmpeg (Required for certain audio processing libraries like librosa or pydub)

Setup Steps:

1. Clone the repository

```bash
git clone https://github.com/EthanChen5291/noki_rhythm_engine.git
cd noki_rhythm_engine
```

2. Create a Virtual Environment (Recommended)

```bash
python -m venv venv
```


### Activate it:


macOS / Linux

```bash
source venv/bin/activate`
```

Windows

```bash
venv\Scripts\activate
```


3. Install Dependencies

```bash
pip install -r requirements.txt
```


4. Run the Game

```bash
python main.py
```


## Running locally

Clone the repo:
`git clone https://github.com/EthanChen5291/noki_rhythm_engine.git`

Enter the project:
`cd noki_rhythm_engine`

Install dependencies:
`pip install -r requirements.txt`

Run the game:
`python main.py`

---

## Why I built this

Most rhythm games rely on handcrafted maps. This leads to limitations in the variety of songs that can be played.

I wanted to explore:
> how close you can get to that “handmade feel” using deterministic systems + audio analysis

The focus is on:
- timing that matches the music
- input patterns that feel natural
- controlled randomness so levels don’t feel robotic

---

## What it does

- analyzes audio to estimate BPM, intensity, and structure
- generates note timing aligned to beats and sub-beats
- maps words into input sequences that are playable and ergonomic
- adjusts scroll speed and density based on musical intensity

You can drop in your own:
- audio file
- word bank

and get a fully playable level.

---

## Key systems

**Audio analysis**
- BPM detection + normalization
- sub-beat intensity calculation
- section-based intensity tracking

**Beatmap generation**
- deterministic timing with controlled variation
- intensity-driven note density
- pattern shaping based on rhythm structure

**Gameplay**
- typing-based input mapped to rhythm
- dynamic scroll speed
- real-time feedback and animations

---

## Tech

- Python  
- Pygame  
- NumPy / audio processing tools  

---

## Limitations

- generated maps are not always as polished as handcrafted ones  
- audio analysis can struggle with complex or messy tracks  

---

## Future work

- better word selection (difficulty + keyboard coverage)  
- improved phrase/melody alignment  
- smarter difficulty scaling  
