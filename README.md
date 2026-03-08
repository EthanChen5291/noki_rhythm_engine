# 🐱 Noki (v1.0)
### *A High-Fidelity Rhythm-Typing Engine*

**Noki** is a procedural rhythm engine designed to bridge the gap between mechanical typing and the expressive "flow state" of modern rhythm games. By leveraging deterministic audio analysis and music theory, Noki transforms any audio file and word bank into a playable, musically-synced keyboard level.

![noki](assets/images/noki_thumbnail.png)

---

## 🎯 Mission Statement
Noki’s goal is to inject musicality and proven design patterns into **any** list of words and **any** sound. By mixing grid alignment with controlled humanization, we aim to imitate the impact of hand-crafted rhythm levels through a fully automated pipeline.

---

## ✨ Core Features
* **Dynamic Word Mapping:** An algorithm that maps word banks to BPM in an ergonomically satisfying way.
* **Customizability:** Total user control over level design (Custom `.txt` word banks and `.mp3/.wav` music).
* **Progression Tracking:**
    * ✅ **Journey:** Level completed.
    * ⭐ **Classic:** High-accuracy mastery.
    * 👑 **Master:** Flawless execution (Cat Crown).
* **FNF-Inspired Aesthetics:** Simplistic, constant-brush-thickness art style with high-energy animations.

---

## 🎹 Soundtrack & Level Progression
| Level | Track ID | BPM | Status |
| :--- | :--- | :--- | :--- |
| 0 | **tutorial** | 120 | 🏁 Ending |
| 1 | **heartme2** | 120 | 🏁 Ending |
| 2 | **moonlitforest** | 110 | 🏁 Ending |
| 3 | **goofuhdur** | 120 | 🏁 Ending |
| 4 | **thatstrange..** | 150 | 🔄 Ongoing |
| 5 | **RAMJAM** | 120 | 🏁 Ending |
| 6 | **BAMSAM** | 170 | 🏁 Ending |
| 7 | **finalmeow** | 180 | 🏁 Ending |

---

## 🚀 Technical Roadmap
### Phase 1: Algorithmic Expansion
* **Similarity Logic:** Add words to the bank by finding matches in `DIFFICULTY` and `CHARS_USED`.
* **Coverage Logic:** Add words that maintain `DIFFICULTY` but cover under-represented characters on the keyboard.

---
*Developed for the intersection of Music Composition and Computer Science.*
