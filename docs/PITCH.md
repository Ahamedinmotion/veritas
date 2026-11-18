# VERITAS: pitch and live-demo script

For **Khais Mohammed (K)** and **Prithvi (P)**. INFINIA 2026, Saturday 21 November.

There are three scripts in this file:

1. **The 3-minute story pitch.** Use this by default when judges arrive.
2. **The 60-second pitch.** Use this when a judge says "we only have a minute".
3. **The 5-minute live demo of the lab.** Go straight into it after either pitch.

After the scripts you will find what to do when something breaks, the numbers to know by heart, and a map of
all 49 story steps for a longer tour. Hard questions and model answers are in `docs/JUDGE_QA.md`.

Every number here comes from `web/data/results.json` (run of 18–19 Nov) and `web/samples/*/manifest.json`.
If anyone re-runs `scripts/evaluate.py`, check chapter 06 again and update this file.

---

## Roles

| | Khais (K) | Prithvi (P) |
|---|---|---|
| Story pitch | 00 Opening, 01 Threat, 04 Forensics, 05 System | 02 How fakes are made, 03 Can you tell?, 06 Results, the hand-over |
| Live demo | Photos (real, GAN face, face-swap), the person in the liveness check, Spot the Fake | Video, voice, Live Cam explanation, closing line |
| Judge questions you own | Photo forensics, the AI-image network, fusion, attacks, what we built, cost | Video, voice, liveness, the numbers, ethics, privacy, future work |

**Where to stand.** The speaker stands next to the TV holding the USB clicker. The partner stands at the
laptop, presses number keys and does any mouse clicks. Pass the clicker at every hand-over.

**How the cues are written.** `→` means the speaker presses the clicker (or the → key). `[4]` means the partner
presses that number key. *(07 · …)* in italics tells you which step you land on (the counter at the bottom right
shows `07 / 49`).

**One rule for both of you.** While your partner is talking, look at the screen or at the judge, not at your notes.

---

## Before the judges arrive

- [ ] Charger plugged in. Wi-Fi **off**. `scripts\start_windows.bat` is running, with the black window minimised.
- [ ] Tab 1: the story at `http://127.0.0.1:8000/`. Tab 2: the lab at `http://127.0.0.1:8000/lab.html#analyze`,
      with the engine light green ("Online · CPU").
- [ ] Morning warm-up: in the story, press → through all 49 steps once so every image and demo is loaded, then
      press **Home**. Press **F** for fullscreen. The counter should read `01 / 49`.
- [ ] Lab warm-up: analyse one exhibit from the locker so the models are in memory (the first analysis is the
      slowest), then press **N**.
- [ ] Live Cam: open it once (key **2**), allow the camera, check the mesh appears, then press **1**. This way the
      browser never asks for camera permission in front of a judge.
- [ ] Print `web/samples/lab/gan-face.jpg` at about postcard size on matte paper. It shows a person who does not
      exist, and you need it for the liveness trick. Backup: the same file on a phone at full brightness.
- [ ] Saturday morning, after your own test games: on the Spot the Fake screen press **Shift+R** twice. This
      resets the booth scoreboard so it counts only visitors.
- [ ] `[School Name]` is replaced in `web/index.html`, and you say the school name in the opening line below.

### Keys you need

| Story | | Lab | |
|---|---|---|---|
| `→` `Space` `PageDown` | next step | `1` `2` `3` | Analyze / Live cam / Spot the fake |
| `←` | previous step | `N` | new case (back to the locker) |
| `0`–`8` | jump to a chapter | `Esc` | cancel a scan / close a test card |
| `Home` | first step | `←` `→` | previous / next test inside an open test card |
| `F` | fullscreen | `L` `C` `M` | Live cam: liveness check / capture & analyze / mesh on-off |
| `?` | show the keys | `←` real · `→` AI · `Enter` | Spot the fake |

---

## Part 1: the 3-minute story pitch

Aim for 3:00: about 450 spoken words at a calm pace of roughly 150 words a minute. Lines in *(italic brackets)*
are optional, so drop them if you are behind. Rehearse with a stopwatch on Friday.
Start with the story on step 01 ("Seeing is no longer believing.").

| Time | Chapter | Speaker | Keys |
|---|---|---|---|
| 0:00–0:20 | 00 Opening | K | → → → |
| 0:20–0:45 | 01 The Threat | K | → → |
| 0:45–1:05 | 02 How fakes are made | P | `[2]` → → |
| 1:05–1:25 | 03 Can you tell? | P | `[3]` → → → |
| 1:25–1:55 | 04 The forensics | K | `[4]` → → → |
| 1:55–2:15 | 05 The system | K | `[5]` → → → → → |
| 2:15–2:45 | 06 Results | P | `[6]` → |
| 2:45–3:00 | 08 Enter the lab | P | `[8]`, then click LAB 01 |

### 00 · Opening (K, 0:00–0:20)
*(01 · "Seeing is no longer believing.")*

**K:** "Good morning. We're Khais and Prithvi from [School Name]. AI can now forge a face, a voice, even a whole
video call. VERITAS is the lab we built to catch it."

→ *(02 · the face mesh with labels)* **K:** "This is how a machine sees your face: 468 points. Just coordinates."

→ *(03 · the mesh breaks apart)* **K:** "And anything that is data can be rewritten."

→ *(04 · the scan sweeps down)* **K:** "So we built a machine that checks."

### 01 · The threat (K, 0:20–0:45)
→ *(05 · Arup case file)* **K:** "January 2024, Hong Kong. An employee of the engineering firm Arup joined a video
call with his finance chief and colleagues, and sent two hundred million Hong Kong dollars. Every face on that
call was fake."

→ *(06 · cloned voices)* **K:** "Voices are easier still. In McAfee's tests, three seconds of audio gave an
85 percent match. And 47 percent of Indian adults surveyed had faced an AI voice scam, or knew someone who had."

*K passes the clicker to P.*

### 02 · How fakes are made (P, 0:45–1:05)
`[2]` *(08 · "To catch a forger, first learn to forge.")* **P:** "To catch a forger, you first learn to forge."

→ *(09 · GAN diagram)* **P:** "A GAN is two networks in a duel. The generator makes faces, and the discriminator
judges them."

→ *(10 · training runs, the meter climbs to 0.5)* **P:** "They train against each other until the judge can only
guess, fifty-fifty. *(Diffusion models work differently. They learn to remove noise step by step, until a new
image appears out of static.)*"

### 03 · Can you tell? (P, 1:05–1:25)
`[3]` *(17 · three sealed cards)* **P:** "Your turn. Which of these three are real?" Pause for three seconds and look
at the judges.

→ → → *(18–20 · each card turns over. A is fake, B is real, C is fake.)* **P:** "A: fake, made by a GAN. B: real. C: fake,
made from a text prompt. In a 2022 study, people sorting real faces from GAN faces were right 48.2 percent of
the time. A coin toss. So instead of trusting our eyes, we measure."

*P passes the clicker to K.*

### 04 · The forensics (K, 1:25–1:55)
`[4]` *(21 · "Every fake leaves a fingerprint.")* **K:** "Every fake leaves a fingerprint."

→ *(22 · ELA, the photo)* **K:** "Error Level Analysis. JPEG throws away detail in eight-by-eight blocks. Re-save
the photo, and measure how much each pixel changes."

→ *(23 · the error map slides in)* **K:** "We pasted one palm tree into this photo."

→ *(24 · the box appears)* **K:** "It shows two and a half times the error of the real palm beside it. We run
seven more tests like this, from sensor noise and frequency grids to blink rate and the voice spectrum."

### 05 · The system (K, 1:55–2:15)
`[5]` *(38 · "Fourteen tests. Three pipelines. One verdict.")* **K:** "Fourteen tests, three pipelines: photo,
video and voice."

→ → *(39–40 · evidence in, preprocess)* **K:** "Each file is fingerprinted with SHA-256, faces are found, frames
are sampled."

→ *(41 · detectors)* **K:** "Pretrained neural networks carry about seventy percent of the weight. We didn't train
them: we picked them by experiment, and they're credited right here. The physics tests add evidence a person can
actually see. These are the real scores for a research face-swap: the AI-face model and the flicker test caught it;
blink and jitter found nothing."

→ → *(42–43 · fusion, then the gauge swings)* **K:** "We combine them in log-odds, so a confident 95 counts far
more than a lukewarm 60. The result is one score from 0 to 100, with a confidence."

*K passes the clicker to P.*

### 06 · Results (P, 2:15–2:45)
`[6]` *(44 · image results)* **P:** "We tested it on 104 images it never saw during tuning: 91.3 percent accuracy,
an AUC of 0.971, and not one real photo wrongly flagged. That last one is optimistic: the network was trained on
the same photo collections most of our real photos come from."

→ *(45 · "Beyond photos, and where it fails")* **P:** "Now the hard part. Ten outside voice clips: every real voice
cleared, but only 2 of 6 fakes caught. Ten research deepfake videos: the same, 2 of 6. It catches faces that AI
generated whole, but misses most face-swaps, lip-syncs and voice clones. We show our failures, because you shouldn't trust a detector you can't
question."

### 08 · Close and hand-over (P, 2:45–3:00)
`[8]` *(48 · "Your turn, detective.")* **P:** "Every detector is temporary. So VERITAS is one layer, next to signed
content, watermarks and a human who decides. That's intelligence beyond humans, kept honest by humans.
Let's show you."

The partner clicks **LAB 01 · Analyze**. If that fails, press **Ctrl+Tab** to switch to the lab tab. Go straight
to Part 3.

> **With extra time:** after 06, press `[7]` to show the three limits (new generators, compression, adversarial
> attacks), then → for "Layers of trust" and the ethics rules, then `[8]`. Say: "The adversarial numbers on this
> slide are an illustration, not a measurement on our engine."

---

## Part 2: the 60-second pitch

Start on step 01. About 150 words.

**K:** "We're Khais and Prithvi from [School Name]. Seeing is no longer believing."

`[1]` *(05 · Arup)* **K:** "In 2024 a company in Hong Kong lost two hundred million Hong Kong dollars on a video
call where every face was fake. And people can't spot AI faces: in one study they were right 48 percent of the
time."

`[4]` → → *(22–23 · ELA map)* **K:** "So we measure. VERITAS runs fourteen tests. This one finds a palm tree we
pasted in. Two neural networks do the rest, and everything is fused into one score, completely offline on this
laptop."

`[6]` *(44)* **P:** "On 104 images it never saw during tuning, it scored 91.3 percent, and no real photo was wrongly
flagged."

→ *(45)* **P:** "But on voice clones and video face-swaps it had never seen, it misses four fakes out of six, and we
show you exactly where."

`[8]` **P:** "Want to try it? Give it a photo, or see if you can beat it at spotting fakes."
Click **LAB 01** to analyse something, or **LAB 03** to play the game.

---

## Part 3: the 5-minute live demo (lab)

You start on the Analyze tab with the Evidence locker visible. Each locker exhibit has a sealed answer, which the
report reveals as **Ground truth** after the verdict.

| Time | What | Who | Expected result |
|---|---|---|---|
| 0:00–0:15 | Intro | K | engine light green |
| 0:15–0:45 | Smartphone photo | K | **Authentic, 1** |
| 0:45–1:30 | GAN face | K | **Synthetic, 100** |
| 1:30–2:00 | Face-swap *(skip if behind)* | K | **Synthetic, 97** |
| 2:00–2:45 | AI "talking photo" video | P | **Synthetic, 91** |
| 2:45–3:15 | AI voice | P | **Synthetic, 82** |
| 3:15–4:20 | Live Cam: liveness and the photo trick | P talks, K is the subject | "Challenge passed", then "Not verified" |
| 4:20–5:00 | Spot the Fake: Humans vs AI scoreboard | K, then P closes | judge plays |

Analysis times on the booth laptop (CPU only): a photo takes about 3–5 s and a voice clip about 2–4 s. A video can
take 15–25 s. Fill in the real times on Friday. **Never sit in silence during a scan.** Every exhibit below has a
line to say while it runs.

### 0:00–0:15 · Intro (K)
**K:** "This is the product. The engine is Python, running on this laptop's processor. That green light means
it's online, with no internet at all. Every exhibit in this locker has a sealed answer that only opens after the
verdict."

### 0:15–0:45 · Exhibit 1: smartphone photo (K)
Click **Smartphone photo**. While it scans:
**K:** "We always start with a real photo. A detector that cries wolf is useless."

On the report, point at the verdict, then at the **Metadata & Provenance** card:
**K:** "Authentic, 1 out of 100. Full camera EXIF: make, model, exposure, capture time. And the ground truth says
real."

Press **N**.

### 0:45–1:30 · Exhibit 2: GAN face (K)
Click **GAN face**. While it scans:
**K:** "This person does not exist. A GAN made this face."

On the report:
**K:** "Synthetic, 100. The face box shows the face model at 100, and the AI-image detector found generator
fingerprints in all nine patches of the picture."

Click the **Frequency Spectrum (FFT)** card. The detail panel opens with the spectrum.
**K:** "Here's the physics. Real photos lose fine detail along a smooth curve. This one falls below it, which is
too smooth for a camera."

Press **Esc** and point at the **Error Level Analysis** card, which reads 10.
**K:** "But ELA says 10. ELA hunts for pasted regions, and a face generated from scratch has none. That's why no
single test decides."

Press **N**.

### 1:30–2:00 · Exhibit 3: face-swap (K, skip if behind)
Click **Face-swap: AI face pasted into a real photo**.
**K:** "We made this one with our own face-swap code. It finds the face landmarks, warps the new face triangle by
triangle, and blends it in. You can see the ghost eyebrows."

On the report:
**K:** "Caught: 97. But to be fair, it's caught because the face we pasted is itself AI-generated. When the pasted
face belongs to a real person, our engine mostly misses. In our test it caught only 2 of 9."

Press **N**. *K hands over to P.*

### 2:00–2:45 · Exhibit 4: AI "talking photo" video (P)
Click **AI 'talking photo'**. This is the slowest scan, so talk through it:
**P:** "For video, the engine samples up to 48 frames and runs the face model on each one. It also tracks
478 face landmarks about twelve times a second, to count blinks and measure how steady the face is."

On the report, point at the timeline, then at the **Blink** and **Landmark Jitter** cards:
**P:** "Synthetic, 91. This line is the face model frame by frame, and these four keyframes are the most
suspicious frames. Blink rate: zero blinks in twelve seconds. Landmark jitter: the face geometry is frozen. It's
a photograph being moved, which is how scam 'talking photos' are made."

The honest line (always say it):
**P:** "We made this clip the same way as the clips we used to set the video thresholds, so it's a
demonstration, not proof. On real research deepfakes, blink and jitter found nothing: modern fakes blink. The
proof is on our results slide: only 2 of 6 research video fakes caught."

Press **N**.

### 2:45–3:15 · Exhibit 5: AI voice (P)
Click **AI voice**. When the report opens, click ▶ to play it. It lasts 5 seconds.
**P:** "We generated this voice with text-to-speech. It imitates no one."

**P:** "The AI voice detector scores it 86 in both windows. Breaths and silence: the pauses are digitally clean,
with no breaths. And the spectrogram is a picture of the sound: frequency going up, time going across."

The honest line:
**P:** "Voice is our weakest area. Clones from new tools mostly get past it."

*(If you are ahead of time: press N, then **Real human voice**, which comes out Authentic, 16. Or, best for an
honest judge, the last exhibit **A fake VERITAS misses**: a HiFi-GAN vocoder voice that comes out Authentic, 34,
and the ground truth says Fake. "No detector is perfect, and here's the proof.")*

### 3:15–4:20 · Live Cam: liveness and the photo trick (P talks, K is the subject)
Press **2**. K steps in front of the camera.

**P:** "Everything on this screen runs inside the browser: 478 face points, tracked live." Read the FPS number on
screen. "K, blink." Point at the eye-aspect-ratio graph. "The eye's height over its width drops, and that's
counted as a blink."

Press **L** for the liveness check. The screen shows three steps in a random order: blink two or three times,
turn left, turn right. K follows them, and the screen shows **"Challenge passed."**

**P:** "The order changes every time. A printed photo or a pre-recorded video can't follow it. A real-time
face-swap driven by a live person could, so banks combine checks like this with others."

**The trick.** K holds the printed GAN face in front of K's own face, keeping it still.
**P:** "Now watch. The tracker still finds a face. To a machine, a photo *is* a face." The mesh locks onto the
print. Press **L**. "Blink, please." Wait. After 15 seconds the screen shows **"Not verified."**
**P:** "It can't follow the order. That's the trick: don't ask 'is there a face?', ask 'can it respond?'"

*(Optional, and only if it worked in the Friday test on this laptop: K lowers the print and P presses **C**. One
frame goes to the engine, and for webcam frames only the two AI networks are scored. Expect "Authentic". If a
real face ever comes out Suspicious, use the line in Part 4.)*

### 4:20–5:00 · Spot the Fake: Humans vs AI (K, then P closes)
Press **3**. The intro screen shows the **Booth scoreboard: Humans vs AI · VERITAS**.

**K:** "Last one: Humans versus AI. Ten pictures. Is each one a real photo, or AI? Everyone who plays today adds
to this board. Right now humans are at [read the %] and VERITAS is at [read the %]." *If the board is empty, say:
"You'd be the first."*

**K:** "On the thirty pictures in this game, VERITAS gets 27 right. In that study, humans managed 48 percent.
Would you like to try to beat it? Left arrow for real, right arrow for AI."

Let the judge take the keyboard. **Enter** starts the game. After each answer the screen shows what VERITAS said,
and **Enter** moves to the next picture. At the end, read out their score against VERITAS's and offer: "Put your
name on the board."

**P (closing):** "That's VERITAS: fourteen tests, one verdict that shows its reasons, and nothing ever leaves this
laptop. Thank you. We'd love your questions."

> **If you only have 3 minutes for the demo:** GAN face, then the video (or the voice clip if the laptop is slow),
> then the liveness check with the photo trick, then the scoreboard.

---

## Part 4: when something goes wrong

| Problem | Say | Do |
|---|---|---|
| Red **Engine offline** banner | "The engine is restarting. The camera part still works." | Double-click `scripts\start_windows.bat`, wait about 30 s, click **Check again**. Do the Live Cam in the meantime. |
| A video scan is slow | Use the "while it scans" line, then explain the timeline you're about to see. | Don't cancel before 40 s. After that, press **Esc** and do the voice clip instead. |
| A real person (you or a judge) comes out Suspicious or Synthetic in Live Cam | "That's our known weak spot. Webcam frames are smoothed and compressed, and to the AI detector they can look too clean. On stills of real people from research videos, 5 of 12 were flagged. That's why our score is evidence, not a verdict." | Don't argue with the result. Show story `[6]` → (06·2) if they want the numbers. |
| A judge's own file is judged wrong | "Thank you. That's exactly the kind of case we want to learn from." | Write it down in the booth notebook (file type, source, score). |
| Camera does not start | "The browser needs permission. One moment." | Close other camera apps, then click the lock icon → Camera → Allow, and reload. Check Windows Settings → Privacy & security → Camera (both switches on) and the laptop's camera shutter. If it still fails, skip Live Cam and show the blink demo in the story (`[4]`, then click exhibit G). |
| Live Cam says "Camera paused" | "It rests when nobody is in front of it." | Click **Wake**. |
| Liveness fails for a real person | "It needs the whole face, lit from the front." | Move toward the light and try once more, then move on. |
| The printed photo isn't tracked | "Glare. Let me tilt it." | Tilt the print away from the ceiling lights, or use the phone backup. |
| Judge interrupts the pitch | Answer in one or two sentences, then "Let me show you the evidence." | Jump with a number key. Don't restart from the beginning. |
| The story stutters on the TV | | Press **F** twice to leave and re-enter fullscreen. If it keeps stuttering, skip to `[6]`. |
| The game is still running when the next judge arrives | | **Esc** goes back to the intro and its scoreboard. |

---

## Part 5: numbers to know by heart

**Photos (held-out test: 104 images, 49 real and 55 fake, no number fitted on them, re-saved as JPEG with metadata stripped)**
- Accuracy **91.3%**. AUC **0.971**. Precision **100%** (0 of 49 real photos flagged). Recall **83.6%** (46 of 55 fakes
  caught). The 9 it missed were 7 face-swaps and 2 diffusion images.
- By type: GAN faces **22/22** caught, diffusion images **22/24**, our face-swaps **2/9**.
- Each test alone (AUC): AI-image network **0.98**, AI-face **0.93**, noise **0.65**, JPEG tables **0.65**,
  FFT **0.62**, ELA **0.50**, metadata **0.50**.
- After WhatsApp-style compression: **43/55** fakes still caught, **0/49** real flagged. After a webcam-style
  pipeline: **38/55** caught, **1/49** real flagged.
- Weak spot: stills of **real** people taken from compressed research videos were flagged **5 of 12** times.
- Small sample: one image moves accuracy by about 1 point. Exact 95% ranges: accuracy **84–96%**, false-alarm rate
  **0–7%**.
- Optimistic: the AI-image network's authors trained it on FFHQ and COCO, the source of **42 of our 49** real test
  photos. The 7 phone photos (0 flagged) are the fairest real test.

**Voice (206 clips)**
- 10 outside clips (generators never used for tuning): fakes caught **2/6**, real voices cleared **4/4**. AUC
  **0.92**, but from only 10 clips. None of the 6 fakes gets a "synthetic" verdict in the lab. Not fully unseen:
  LibriSpeech speaker 260 (4 clips) and the HiFi-GAN vocoder type were in tuning.
- Same datasets, new speakers: **75.7%**, AUC **0.81**. This is the optimistic number.
- When a whole dataset was left out of tuning, **75%** of real everyday-microphone voices (FLEURS) were flagged.

**Video**
- 10 research clips: fakes caught **2/6**, real cleared **4/4** (all under 50). Only the FF++ face-swap gets a
  "synthetic" verdict in the lab. Blink and jitter sat at their floors on every clip. The
  Google DFD face-swap scored **5** and the Wav2Lip lip-sync **14**. About **2.2 s** per clip on the development
  laptop.

**Game and humans**
- On the 30 game pictures, VERITAS gets **27** right. People in the 2022 study managed **48.2%**.

**The system**
- 14 tests, 3 pipelines. Verdicts: below 35 authentic, 35–65 suspicious, above 65 synthetic.
- AI-image network: CommunityForensics ViT-Small, 87 MB, trained on images from **4,803** generators (CVPR 2025).
- Voice: wav2vec2 layer-4 features (768 numbers per 4-second window) plus our own logistic-regression probe.
- Faces: YuNet finds them, and MediaPipe gives **478** landmarks (468 face points plus 10 iris points).
- Data: **171** images, **206** voice clips, **16** videos (6 for tuning, 10 outside research clips).
- Speed: a photo takes about **0.9 s** on the development laptop and 3–5 s on a slow one. No internet. About 1.7 GB
  to download once.

### Say this, never that

| Never say | Say instead |
|---|---|
| "It's 91% accurate." | "On our held-out test it was 91.3%. Real life will be lower." |
| "It can detect any deepfake." | "It catches AI-generated faces and images well. It misses most face-swaps and new voice clones." |
| "This proves it's fake." | "This is evidence. A human makes the decision." |
| "We trained an AI." | "We chose a pretrained network by experiment, and trained a small probe on top of it." |
| "Our dataset is huge." | "It's a school-scale experiment: 171 images, 206 voice clips, 16 videos." |
| "Nobody can fool it." | "Anyone with enough skill could. Here's how, and here's what would stop them." |

---

## Appendix: all 49 story steps

Use this map for a longer tour, or to find your place after a question. "Step" is the counter at the bottom right.

| Step | Ch | On screen | One line to say |
|---|---|---|---|
| 01 | 00 | "Seeing is no longer believing." | AI can forge a face, a voice, a whole call. |
| 02 | 00 | Face mesh, 468 points | To a machine, a face is just coordinates. |
| 03 | 00 | The mesh breaks apart | Anything that is data can be rewritten. |
| 04 | 00 | Scan plane, swapped region in red | So we built a machine that checks. (This is an illustration.) |
| 05 | 01 | Arup case: HK$200 million | 15 transfers on a call where every face was fake. |
| 06 | 01·2 | Cloned voices | New Hampshire robocalls; 3 s gave an 85% match; 47% of Indian adults surveyed had faced a voice scam or knew someone who had. |
| 07 | 01·3 | The scale (vendor data) | 10× rise in a year; an attempt every 5 minutes; $40B projected by 2027. |
| 08 | 02 | "To catch a forger, first learn to forge." | Four ways fakes are made. |
| 09–10 | 02 A | GAN, then the training runs | The generator against the discriminator, until D = ½. |
| 11–12 | 02 B | Autoencoder face-swap | One shared encoder, two decoders: encode A, decode with B. |
| 13–14 | 02 C | Diffusion: noise, then the rewind | Training adds noise. Generating removes it, step by step. |
| 15–16 | 02 D | Voice cloning pipeline | A voice-print, a mel-spectrogram, then a vocoder. |
| 17 | 03 | Three sealed cards, 48.2% | Which are real? |
| 18–20 | 03 | Each card turns over | A fake, B real, C fake, each with the VERITAS score. |
| 21 | 04 | "Every fake leaves a fingerprint." | Eight physics tests. No single test is proof. |
| 22–24 | 04 B | ELA: photo, map, box | Re-save and compare. The pasted palm shows 2.5× the error. |
| 25–26 | 04 C | Noise lens: sky, then palm | Every sensor has a grain. The pasted patch is quieter. |
| 27–28 | 04 D | FFT: camera, then GAN-style | Up-sampling stamps a grid that shows up as peaks. |
| 29–30 | 04 E | JPEG: saved once, saved twice | Double rounding leaves periodic gaps. |
| 31–32 | 04 F | C2PA chain: valid, then mismatch | Change one pixel and the signature breaks. |
| 33–34 | 04 G | Blink EAR: real, then early deepfake | About 17 blinks a minute. Early fakes forgot; modern ones blink, and in our test it never fired. |
| 35 | 04 H | Landmark jitter | Remove head motion, measure the shake. Honest result: only flicker fired on research clips. |
| 36–37 | 04 I | Spectrogram: real mic, then clone | Some clones stop at 8 kHz, but so do phone calls: shown, not scored. |
| 38 | 05 | "Fourteen tests. Three pipelines. One verdict." | |
| 39–43 | 05 | Evidence → preprocess → detectors → fusion → gauge | Log-odds fusion. Real engine output for an FF++ face-swap: 76, confidence 0.63. Pretrained models credited. |
| 44 | 06 | Image results | 91.3%, AUC 0.971, 0 false alarms out of 49. |
| 45 | 06·2 | Voice, video, the hard cases | Fakes caught 2/6 (voice) and 2/6 (video); all reals cleared. Where it fails. |
| 46 | 07 | Three limits | New generators, compression, adversarial noise (an illustration). |
| 47 | 07·2 | Layers of trust and our ethics rules | Provenance, watermarks, detection, literacy and law. |
| 48 | 08 | "Your turn, detective." Three doors into the lab | Hand over to the demo. |
| 49 | 08 | Credits and the 22 sources | |
