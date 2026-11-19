# VERITAS: the 26 hardest judge questions

These are model answers for **Khais (K)** and **Prithvi (P)**. Each question names an **owner**, who answers
first. The partner adds at most one sentence. Every number here comes from `web/data/results.json`,
`server/` and the other files in `docs/`. If a number on the screen ever differs from this file, trust the screen
and fix this file.

## How to answer

1. **Answer in your first sentence.** Then give the reason.
2. **Give one real number.** Don't give five.
3. **Name the limit before they find it.** Judges trust a team that knows where its own work breaks.
4. **If you don't know, don't invent.** Say: "We didn't test that. Our best guess is X, because Y. Here's how we
   would test it." That is a good answer.
5. **Point at the screen.** Most answers have a place in the story or the lab that shows them. It's listed as
   **Show:**.

| Section | Questions | Mostly answered by |
|---|---|---|
| A · The science | 1–7 | K (1, 2, 3, 5, 7), P (4, 6) |
| B · The numbers | 8–13 | P |
| C · Limits and attacks | 14–18 | K (15, 16, 17), P (14, 18) |
| D · What we built | 19–21 | K (19, 20), P (21) |
| E · Ethics, privacy, the real world | 22–26 | P (22, 23, 26), K (24, 25) |

---

## A · The science

### 1. How does Error Level Analysis work? *(K)*
JPEG compression throws away fine detail in 8×8 blocks. If you save a JPEG again, the parts that were already
compressed barely change. So we re-save the photo at quality 90 and measure how much each pixel changed:
ELA = k·|I − JPEG(I)|. A region pasted in from somewhere else has a different compression history, so it can
glow. The catch is that edges and fine texture always glow. Our engine therefore compares each 16-pixel block
only with blocks of *similar texture*, and raises the score only when a compact cluster of blocks stands out
(we use a robust z-score). In our story demo, the palm we pasted in shows 2.5 times the error of the real palm
beside it.

**If they push ("does it catch AI images?"):** No. A fully generated image has no pasted region, so ELA has
nothing to find. Alone it scored AUC 0.50 on our held-out images, which is chance. That's why it carries only 6%
of the weight. It's a map for human eyes.
**Show:** story `[4]` → → → (the palm), or the ELA card of any lab report.

### 2. Why use the Fourier transform? *(K)*
The 2-D FFT rewrites an image as a sum of waves of different frequencies. A natural photo has lots of
low-frequency energy, and it fades smoothly towards fine detail. Many generators build an image by repeatedly
up-sampling small feature maps (transposed convolutions). That stamps a faint repeating pattern over the whole
picture. The pattern is invisible to the eye, but in the spectrum it becomes bright, evenly spaced peaks, like a
grid. The FFT is useful because a pattern spread thinly over a million pixels turns into a few sharp spikes that
are easy to measure. Our engine averages the spectrum in rings, compares it with the natural trend, and looks for
two things: periodic peaks, and missing fine detail.

**The limit:** modern diffusion models leave weaker grids, and re-compression blurs them. Alone, the FFT test
scored AUC 0.62. On our GAN-face exhibit it scored 78: "fine detail falls below the natural trend."
**Show:** story `[4]`, then click exhibit D (→ toggles the camera photo against the GAN-style image). Lab: the
GAN face's FFT card.

### 3. Your own chart says ELA, FFT and noise are close to chance. Why keep them? *(K)*
It's true. On whole AI images, each one alone scored AUC 0.50 to 0.65 (ELA 0.50, FFT 0.62, noise 0.65, JPEG
tables 0.65, metadata 0.50). We keep them, with small weights (about 28% together for photos), for three reasons.
- **They look for different things.** They are built to find edits and splices, which the AI network was never
  trained on.
- **They explain.** A network gives a number. An error map or a spectrum shows a person *where* to look.
- **They are independent.** A forger who beats the network still has to beat the physics.

A classic test only gets extra weight (up to 3×) for *specific* evidence: a localised splice, a periodic grid, an
AI-tool tag. It never gets extra weight for "too smooth", because webcams and phones also smooth images.

**Honest part:** we made a splice ourselves, pasting an AI region into a real phone photo. The ELA map showed the
square clearly to the eye, but no classic test's *score* caught it. Part of the JPEG-table signal is also a dataset
artefact, because our real faces were PNG originals.

### 4. How does the blink test work, and don't modern deepfakes blink? *(P)*
MediaPipe gives six points around each eye. The Eye Aspect Ratio is EAR = (‖p2−p6‖ + ‖p3−p5‖) / (2‖p1−p4‖),
which is the eye's height over its width. It sits near 0.3 when the eye is open and drops towards 0 during a blink.
We count a blink when EAR falls below 72% of that person's open-eye level for at most 0.6 s. People blink about
17 times a minute at rest. A Poisson model tells us how likely it is that a real person blinks this few times in
this many seconds.

Yes, modern deepfakes blink. The 2018 paper that found the missing blinks got the generators fixed. That's why
blink carries only 14% of the video weight. Our AI "talking photo" blinks 0 times in 12 s. The Poisson chance of
that is e^(−3.4) ≈ 3%, which is unusual but not damning, so the test only says "a little low" (44). It scores high
only when the chance falls below about 1 in 400. People reading a screen also blink less.
Our own honest result: on the 10 research videos the blink score sat at its floor (15) on **every** clip, real or
fake. It found nothing in any research deepfake, so a normal blink rate proves nothing. Landmark jitter was the
same (12 on all 10); only the flicker test fired, on the FaceForensics++ face-swap (88).
**Show:** Lab `2` (the live EAR graph), or story exhibit G.

### 5. The AI network is a black box. How does it decide, and how do you know what it's looking at? *(K)*
It's a Vision Transformer (ViT-Small, 87 MB) from the CVPR 2025 paper *Community Forensics* (Park & Owens),
trained on images from **4,803** different generators. A ViT cuts the image into small square patches, turns each
patch into a list of numbers, and uses *attention* to let every patch compare itself with every other patch. It
learned the statistical textures that generators leave behind. It didn't learn "faces look weird".

We can't read its mind, so we do three things.
1. We run it on the whole image **and** on a 3×3 grid of overlapping patches, which gives a map of *where* it sees
   synthesis.
2. We zoom it onto each face that YuNet finds.
3. We pass its raw output through a calibration curve fitted on our calibration images, so that 50 means "on the
   fence".

We chose it by experiment. We ran 12 candidate models on our calibration images, and this one won every column
while being the smallest and fastest. The popular "deepfake face" classifiers scored AUC 0.39–0.59, which is
coin-toss level.

### 6. How do you detect a cloned voice? *(P)*
We use a pretrained network with a probe on top that we trained ourselves. The network is wav2vec2, a speech
transformer pre-trained on 960 hours of English speech and then fine-tuned on the *In-the-Wild* deepfake
dataset. Its own yes/no answer was weak on our clips: the best of 7 candidate models reached AUC 0.73. So we used
**transfer learning**. We take its layer-4 features (768 numbers for each 4-second window, describing fine
acoustic texture) and trained a logistic-regression probe on our calibration clips. We picked layer 4 by 5-fold
cross-validation inside the calibration set: layer 4 scored 0.94, layer 8 scored 0.83 and layer 12 scored 0.77.
Early layers keep vocoder artefacts, while late layers specialise in the network's old training data.

A second test, **breaths and silence**, looks for digitally clean pauses and missing breaths. The pitch track and
the spectral cut-off are shown as pictures but carry no weight, because they scored at chance (AUC 0.52 and 0.42).
Clips with less than 1 second of clear speech get "not enough speech to judge" instead of a verdict.

### 7. How do fifteen tests become one score? *(K)*
Each test gives a score *s* from 0 to 100. We turn it into **log-odds**, ln(s / (100 − s)), take a weighted
average, apply two calibration constants, and turn it back with the sigmoid:
**S = 100·σ(z),  z = a·Σ wᵢ·ln(sᵢ / (100 − sᵢ)) + b.**

We use log-odds because that is how independent evidence adds up in probability: Bayes' rule in log form. A 95 is
19-to-1 odds and a 60 is only 1.5-to-1, so a confident test counts far more than a lukewarm one. The neural
networks carry about 70% of the weight. A test that can't run (no face, no speech) drops out, and the other
weights are rescaled. The **confidence** number is how much the tests agree, blended with how far the score is
from 50.

One exception: the **face-swap detector is one-sided**. It votes only when its score is 50 or more, and the final
score is the higher of "with it" and "without it". Its networks call fully AI-generated faces "real" (they were
trained on swaps), so it may raise an alarm but must never vouch for a video.

**Honest part:** we set the weights by hand. Only the calibration curves and the photo gain and bias were fitted,
and only on the calibration split. The face-swap test's weight (1.25) and thresholds were chosen on FaceForensics++
clips only.
**Show:** story `[5]`, then → five times. The gauge example (70, a Wav2Lip lip-sync that scored 14 before the
face-swap detector) is computed with the engine's real formula.

---

## B · The numbers

### 8. What is AUC, and why not just report accuracy? *(P)*
AUC is the area under the ROC curve. Slide the "fake" threshold from 100 down to 0. At each threshold, plot the
share of fakes caught against the share of real files wrongly flagged. The area under that curve equals the
**probability that a randomly chosen fake scores higher than a randomly chosen real file**. 0.5 is a coin toss and
1.0 is perfect. Ours is 0.971 on 104 held-out images.

Accuracy depends on one chosen threshold and on the mix of fakes and reals in the test. AUC measures how well the
scores *rank* the files, whatever the cut-off. Our voice spot check shows why this matters. It had **AUC 0.92 but
caught only 2 of 6 fakes** (all 4 real voices cleared): the fakes scored higher than the reals (21–63 against
3–23), but most fakes stayed under our cut-off of 50. The ranking was right, and the threshold was wrong for those
new generators. And with only 10 clips that AUC is shaky: its 95% range is roughly 0.73 to 1.0.
**Show:** story `[6]` (the ROC curve and the per-test AUC bars).

### 9. What's your dataset, and how do you know you didn't test on what you tuned on? *(P)*
- **Images: 171 in total.** 78 are real: FFHQ faces, COCO scenes, and 10 smartphone photos with camera EXIF.
  93 are fake: 36 StyleGAN2 faces, 44 diffusion images (DALL-E 3, FLUX, Midjourney, Stable Diffusion) and 13
  face-swaps we made.
- **Voice: 206 clips**, 100 real and 106 fake. They come from LibriSpeech, FLEURS, ASVspoof 2019, a voice-clone
  dataset, and text-to-speech we generated.
- **Video: 16 clips.** 6 were used for tuning and 10 are outside research clips.

We split the files into about **40% calibration and 60% held-out test**. The split is *group-aware*: one speaker,
one text prompt, or one face-swap together with its source photos never appears on both sides. Every choice
(which model, which layer, the calibration curves) used only the 40%. The held-out 104 images (49 real, 55 fake)
were used once, at the end. We also *laundered* them: every file was re-saved as JPEG quality 90 with the
metadata stripped, so the detector can't cheat by reading the file format or the EXIF.
To be fully honest: no number was ever fitted on the held-out files, but we did look at earlier test runs while
improving the calibration (an early run flagged all 12 real video stills, and we redesigned the calibration). So
treat our numbers as slightly optimistic.

### 10. Would 91.3% hold up in the real world? *(P)*
No, and we say so on the screen. There are three reasons.
- **Small sample.** With 104 images, one image moves accuracy by about 1 point. The exact 95% confidence range for
  91.3% is 84% to 96%, and for the false-alarm rate (0 of 49) it is 0% to 7%.
- **Familiar images.** The network's authors list FFHQ and COCO among its training datasets, and 42 of our 49
  real test photos come from them. So "0 false alarms" is optimistic. Our 7 phone photos (0 flagged) are the
  fairest real-photo test.
- **Messier real life.** When we fed in stills of *real* people from compressed research videos, 5 of 12 were
  flagged.

That's why we don't give one headline number. We give three: 91% on photos, 2 of 6 outside voice fakes caught,
and for video face-swaps on 30 clips from datasets neither network was trained on, 12 of 15 fakes called
synthetic, with 5 of 15 real clips called "suspicious" (none synthetic, but with 15 clips that is thin evidence).

### 11. Aren't your demo samples cherry-picked? *(P)*
Yes, the evidence locker is chosen on purpose, and the lab says so under the locker. Each exhibit shows one test
clearly, like a textbook example. The real NASA video comes from our tuning set, and the AI "talking photo" was
made the same way as our tuning clips. The face-swap is one of only 2 of 9 swaps it caught. That's why the last
exhibit, **"A fake VERITAS misses"**, is a HiFi-GAN vocoder voice it calls Authentic (34).
That's a **demonstration, not a result**. The results are in chapter 06, on files that were never used for
tuning, failures included. And you don't have to trust our samples: give us a photo from your phone (by USB
cable), or stand in front of the camera, and we'll analyse it in front of you.

### 12. What happens when it calls a real person fake? *(P)*
That's the error we worry about most, because it can hurt someone. On held-out photos, it flagged **0 of 49**
real images, so its **precision is 100%**: all 46 files it flagged really were fake. The price is **recall
83.6%**: it missed 9 of 55 fakes, 7 of them face-swaps. We chose that trade-off on purpose.

Stress tests on copies of the held-out real photos:
- after a webcam-style pipeline: 1 of 49 flagged
- after a phone "beauty" filter: 4 of 49
- after WhatsApp-style compression: 0 of 49

The weak spots are stills from compressed real videos (5 of 12 flagged), everyday-microphone voices (75%
flagged when that dataset was left out of tuning) and, since the face-swap detector, grainy real **videos**: of 39
real clips degraded like a cheap webcam, 11 came out "suspicious" and 1 "synthetic" (before: 1 and 0). On its own,
the face-swap test fires on 7 of 15 real Celeb-DF/DFD clips and 21 of those 39 webcam-quality real clips. Its
threshold was set on FaceForensics++, the dataset GenD was trained on, where it is overconfident about real faces.
The fusion turns most of these alarms into "suspicious", not "synthetic". That is why the face-swap detector is
one-sided and not used on photos or Live Cam frames. So:
- scores from 35 to 65 are shown as "suspicious", not "fake";
- every report lists which tests fired;
- our rule is that **a score is evidence, never a verdict**. A human decides.

### 13. Why is the voice result so much worse? *(P)*
Voice detectors learn shortcuts. On speakers it had not heard, but from the *same* datasets, it scored 75.7%
(AUC 0.81). Then we ran a harder test: leave one whole dataset out of tuning and test on it.

| Dataset left out | Result |
|---|---|
| ASVspoof | AUC 0.85 |
| LibriSpeech vs our own text-to-speech | AUC 0.60 |
| UniData clone set | AUC 0.50 (chance) |
| FLEURS everyday speech | 75% of real voices flagged |

So the probe partly learned *which dataset* a clip came from (its microphone and room), not what makes a voice
synthetic. We found and fixed one shortcut ourselves. Twelve clips from a single narrator had taught it "this
voice = real", so we added 24 different speakers, plus 24 copies of the same clips re-made by a vocoder, where
only the vocoder differs.

On 10 outside clips (generators never used for tuning: F5-TTS, Chatterbox, WaveGlow, ASVspoof A10) all 4 real
voices passed, but only **2 of 6 fakes** scored above 50, and none got a "synthetic" verdict. Not fully unseen:
LibriSpeech speaker 260 (4 of the clips) and the HiFi-GAN vocoder type were in our tuning set.
**Show:** story `[6]` →. The 06·2 slide has all three panels.

---

## C · Limits and attacks

### 14. Your video test used to miss face-swaps. What changed, and does it work now? *(P)*
**What was wrong.** Our first video face test reused the *general AI-image* detector. It catches faces generated
whole, but a face-swap keeps real skin and real motion, and that network never saw a swap. On 30 research clips
from datasets neither face-swap network was trained on (Celeb-DF and Google DFD) the engine's score was close to a
coin toss: AUC 0.60, and 0 of 15 fakes got a "synthetic" verdict.

**What we did.** We benchmarked six published face-swap detectors on 75 leak-free research clips and added a pair
of them as one more test: GenD (a CLIP vision transformer, WACV 2026) together with the Deepfake Detection
Challenge winner (an EfficientNet-B7). Our pre-registered rule picked the challenge winner alone; we added GenD
after seeing the results because it also catches reenactment (Face2Face, NeuralTextures). It is one-sided, and its
thresholds were chosen on FaceForensics++ only.

**Result, on the same 30 clips:** AUC **0.998**, fakes called synthetic **0 → 12 of 15** (the other 3
"suspicious"), real clips called synthetic 0 → 0. With so few clips the plausible range of the AUC is about
**0.87 to 1.00**; 12 of 15 has an exact range of 52–96 %, and 0 of 15 reals still allows up to 22 %.

**Limits, said first:**
- More real clips now read "suspicious": **5 of 15**, up from 2. Worse on grainy video: 39 real clips degraded like
  a cheap webcam went from 1 suspicious and 0 synthetic to **11 suspicious and 1 synthetic**.
- These 30 clips are not a clean test. Our rule ranked the six candidates by their score on them, and we chose
  the pair *after* seeing them; on them the pair is statistically tied with the challenge winner alone (+0.03 AUC,
  CI 0.00–0.09). And GenD's authors chose their checkpoint using Celeb-DF++ validation videos, so Celeb-DF is unseen
  in training but not in model selection. Only Google DFD (5 real + 5 fake, AUC 1.00) is fully unseen.
- "No real clip called synthetic" is fragile: we picked 8 frames for speed, and with 4 or 16 frames our benchmark
  simulation called one real clip synthetic.
- On its own, the face-swap test fires on 7 of 15 of these real clips; the fusion keeps them at "suspicious".
- Only 2019–2020 methods were tested. FaceShifter, a method neither network saw, was caught 1 time out of 5.
  Modern swap apps were not tested.
- Our booth clips FF++ #069 are in GenD's training data, so they prove nothing, and the Celeb-DF booth pair comes
  from Celeb-DF's training portion. The Google DFD face-swap stays "suspicious" (41). Only our Wav2Lip lip-sync is a
  fully unseen catch, and we looked at it when we chose the pair.

**"Then why not use it on photos too?"** We tested that. On single still images it flagged real faces (after
webcam-style and video-style compression), so it scores videos only. The locker's face-swap *photo* (97) is caught
because the pasted face is itself GAN-generated; real-face photo swaps mostly get through (2 of 9).
**Show:** story `[6]` → → (06·3).

### 15. Can it detect generators it has never seen? *(K)*
Partly, and we can't prove it for tools that don't exist yet. Our image network was trained on 4,803 generators,
so it learned general "made by a generator" textures rather than one model's quirks. That's why we picked it: the
popular classifiers trained on a single dataset scored 0.39–0.59 on modern AI faces. But detectors learn the
fingerprints they were shown, and a new architecture can leave different ones. That's Limit 01 in chapter 07.

Our clearest evidence is voice. On generators never used for tuning, it still ranked the fakes above the reals
(AUC 0.92, from only 10 clips), but it missed 4 of 6 at our threshold. So VERITAS needs regular retraining, like antivirus signatures,
and detection needs back-up from provenance and watermarks.

### 16. What if the fake is sent through WhatsApp, or screenshotted? *(K)*
Every re-share blurs and re-compresses the image, and the faint traces fade. Chapter 07 shows the FFT peaks
disappearing live. We measured this on all 104 held-out images:

| Copy | Fakes still caught | Real images flagged | AUC |
|---|---|---|---|
| WhatsApp-style (1600 px, JPEG quality 75) | 43 of 55 | 0 of 49 | 0.97 |
| Small web copy | 42 of 55 | 1 of 49 | 0.96 |
| Webcam-style pipeline | 38 of 55 | 1 of 49 | 0.95 |
| H.264 video still | 39 of 55 | 2 of 49 | 0.92 |

The neural network survives compression quite well. The classic tests suffer most. A screenshot also strips the
metadata, which is why missing metadata only nudges our score and never proves anything. We have not tested
screenshots as their own condition.
**Show:** story `[7]`, then drag the "Re-compress / resize" slider in Limit 02.

### 17. Couldn't someone just attack your detector? *(K)*
Yes. A neural network can be fooled by *adversarial noise*: x′ = x + ε·sign(∇ₓL). You nudge every pixel slightly
in the direction that increases the network's error the most. To us the picture looks the same, but the answer
flips. **We have not run this attack on VERITAS ourselves**, so we can't give you a number. The "94 → 11" on our
Limit 03 slide is an illustration, not a measurement.

Three things make the attack harder:
- The attacker needs our model and its gradients.
- An attack aimed at the network does not automatically fool the physics tests, though a determined attacker
  could target those too.
- Fusion means beating one test isn't enough.

Real protection would come from adversarial training, keeping models private, and above all **provenance**, which
signs genuine content instead of guessing about fakes.

### 18. Couldn't a real-time deepfake pass your liveness check? *(P)*
Yes. Our check asks for blinks and head turns in a **random order that changes every run**. A turn counts when
the head moves 20° from that person's own resting pose, and each step has 15 seconds. That beats a printed photo,
which can't blink, and a pre-recorded video, which can't know this run's order. It does **not** beat a real-time
face-swap, where the attacker does the moves and software swaps the face live. That's why the lab says
"Challenge passed", not "Live human". (In the Arup case the police said the fake colleagues were pre-recorded and
did not interact, so a challenge like ours would have exposed them.) Banks counter it with extra signals: depth or infrared cameras, detecting screen glare and moiré patterns,
and checking that the camera feed isn't being injected by software.

In our engine, a webcam capture is scored only by the two AI detectors. The other five tests are skipped,
because a webcam smooths and re-encodes every frame.
**Show:** Lab `2`, `L`.

---

## D · What we built

### 19. What did *you* build, and what was pretrained? *(K)*
**Pretrained, downloaded and not trained by us:** eight networks.
- The CommunityForensics image network (photos and face crops)
- The wav2vec2 voice network
- GenD (CLIP ViT-L/14) and the DFDC-winning EfficientNet-B7: the face-swap detector
- YuNet, SCRFD and MTCNN, which find faces
- MediaPipe FaceLandmarker (478 points)

**Ours:**
- **The experiment.** We compared 12 image models and 7 voice models on our calibration split. We built the
  group-aware split, the laundering, five stress tests (webcam, beauty filter, video still, small copy, WhatsApp),
  the leave-one-dataset-out test, and the outside checks on 10 voice clips and 10 videos.
- **The face-swap benchmark.** A leak-free test set of 75 research clips (FaceForensics++ and Celeb-DF from their
  official test splits, checked against the published split files, plus Google DFD clips no candidate trained on),
  six published detectors, each run with its own face detector and crop, checked against the official code (B7
  crops pixel-identical; GenD's alignment differs by 0.00003 px, which does not change the fp32 model's
  decisions), the choice, an independent re-check that changed our pick from int8 to the exact fp32 weights, the
  conversion to ONNX (checked to match the originals), and the integration as a one-sided test.
- **The voice probe.** Transfer learning on wav2vec2 layer-4 features, with the layer chosen by
  cross-validation.
- **The physics tests.** ELA with texture matching, sensor noise, FFT, JPEG tables, metadata (including AI-tool
  tags and C2PA), blink with the Poisson model, landmark jitter, skin flicker, breaths and silence, and the
  speech gate.
- **Small fitted models.** The noise and FFT logistic models (2 and 3 numbers) and the calibration curves.
- **The fusion rule** and the verdict bands.
- **Test fakes.** A face-swap generator (landmarks, Delaunay triangles, Poisson blending) and animated
  "talking photo" videos.
- **The interface.** The lab, including in-browser face tracking and the liveness check, and the story site,
  whose FFT, JPEG and diffusion demos are computed live in the browser.
- **The offline package** for a Windows laptop.

> **Coach's note: be exact about who did what.** Know which parts each of you personally wrote, designed or
> tested. If you used AI coding assistants, tutorials or open-source code, say so plainly. Then explain what
> *you* decided and how you checked it (the evaluation is how you checked it). Judges forgive help. They do not
> forgive over-claiming.

### 20. Why didn't you train your own deepfake detector? *(K)*
Because on 171 images it would only memorise our dataset. A strong image detector needs millions of images from
thousands of generators and a lot of GPU time. The model we use was trained exactly that way by a university
research group. So we did the parts a small team can do properly:
1. a fair selection experiment;
2. transfer learning where the ready-made model was weak (our voice probe);
3. small models fitted only on calibration data;
4. an honest evaluation, including failures.

Our biggest lesson was that **diversity of training data beat model size**. The winning image model was the
smallest one we tried, and the large popular ones were near coin-toss level.

### 21. Did you train the face-swap detector yourselves? *(P)*
**No, and we say so on screen.** We benchmarked six published detectors on a leak-free test set we built, chose
two of them and integrated the pair. GenD was trained by researchers at the Czech Technical University and CISPA on
FaceForensics++, and the B7 won Meta's Deepfake Detection Challenge on more than 100,000 clips of paid actors. Training
something comparable needs that data and weeks of GPU time.

What we did ourselves:
- **Built the test set.** 75 clips: FaceForensics++ and Celeb-DF from their official *test* splits, and Google
  DFD clips that no candidate trained on. We checked this against the published split files and removed whole
  identities that appear in our demo clips.
- **Ran every detector the way its authors did.** Each one used its own face detector and crop. Feeding them our
  own crops changed scores by up to 0.22.
- **Chose thresholds and the weight on FaceForensics++ only,** then tested on Celeb-DF and Google DFD. Honest
  exception: the candidates were ranked on those clips, and we picked the pair (rather than B7 alone) after seeing
  those results.
- **Had the result checked independently.** The re-check found that the smaller int8 version flipped 5 of 91
  decisions under a 0.00003-pixel change, so we switched to the exact published weights.
- **Integrated it** as a one-sided test, and measured speed and memory on our laptop and on a slow-laptop
  stand-in.

**Honest part:** we picked the pair after seeing the cross-dataset numbers. Our own pre-registered rule would have
picked the challenge winner alone, and on those clips the two are statistically tied. GenD itself was trained on
FaceForensics++, and its authors chose their checkpoint using Celeb-DF++ videos.
**Show:** story `[4]` → exhibit J, then `[6]` → → (06·3); `docs/MODEL_SELECTION.md`.

---

## E · Ethics, privacy and the real world

### 22. Did you make deepfakes? Of whom? *(P)*
Yes, but only test fakes, and our rule was **no one famous and no one we know**.
- **Fake faces:** StyleGAN faces of people who do not exist.
- **Face-swaps:** those non-existent faces pasted onto public research photos (FFHQ, COCO). We deleted three
  composites whose photo looked like a public figure, and the game leaves out children and political scenes.
- **Voices:** stock text-to-speech voices. We also cloned two public-domain audiobook readers from research
  datasets (LJSpeech, LibriSpeech) with open-source tools, only to test the detector. They were never shipped and
  never posted.
- **Video:** one Wav2Lip lip-sync of a paid, consenting actor from Google's deepfake research dataset.

The research deepfakes we tested (FaceForensics++, Celeb-DF) appear only as numbers. We never show those clips or
their file names, and we follow their non-commercial licences. Every fake is labelled and exists only as a test
exhibit.

### 23. Where does my photo or face go? *(P)*
Nowhere. Nothing leaves this laptop.
- The engine runs at 127.0.0.1, which is the laptop talking to itself, and the Wi-Fi is off.
- It reads a file into memory, analyses it and keeps no copy. (The web framework may put a large upload into a
  temporary file, which is deleted automatically.)
- In Live Cam, the face tracking runs inside the browser. Only when you press *Capture* does one frame go to the
  engine on this same laptop.
- We found that the face-tracking library we downloaded contained a hidden usage logger that would send data to
  a Google server, and we disabled it.
- The only thing stored is the name you choose to type on the game scoreboard, in this browser.

Each report shows the file's SHA-256 fingerprint, so an investigator can prove which file was checked without
keeping a copy.

### 24. Who would actually use this? Should a score be used as proof? *(K)*
As a **triage tool** for people who check media: fact-checkers, newsroom desks, school cyber-safety clubs, police
cyber cells and bank fraud teams. It says "look closer, and here's why". It is **not proof**. Scores from 35 to 65
are labelled "suspicious", and every report shows which tests fired.

Detection is also only one layer. **C2PA Content Credentials** sign a file's history from the camera to the
screen. **Watermarks** like Google's SynthID mark AI output. But most content online carries neither, and
screenshots and re-uploads strip them, so detection covers everything else. For ordinary people the best defence
is a habit: if a call asks for money, hang up and call back on a number you already know.

### 25. What does it cost, and why offline? *(K)*
- **Software cost: zero.** Everything is open-source: Python, FastAPI, PyTorch, ONNX Runtime, MediaPipe and
  OpenCV. The networks are MIT- or Apache-licensed; the face-swap detector's face finder (SCRFD) and its training
  data are for non-commercial research only, which a school exhibit is. A product would need other licences.
- **Hardware:** an ordinary 8 GB laptop with no graphics card. A photo takes about 0.9 s on our development
  laptop and about 3–5 s on a slow one. *(Fill in the booth laptop's time from Friday.)*
- **Setup:** one download of about 3.5 GB (libraries 1.4 GB + models 2.1 GB, of which the face-swap detector is
  1.5 GB), then it never needs the internet again. The engine uses about 3.6–3.7 GB of RAM while it analyses a
  video, and a video takes about 5–6 s on our development Mac and 33–43 s on a slow 4-core stand-in.

We made it offline for three reasons:
- **privacy:** faces and voices never leave the laptop;
- **reliability:** venues and villages have weak internet;
- **honesty:** no cloud service is secretly doing the work.

Cloud detection services usually charge per scan. Ours costs electricity.

### 26. What would you do with six more months? *(P)*
In order of impact:
1. **Modern face-swaps and lip-sync.** Our face-swap detector was tested only on 2019–2020 methods. We would test
   today's swap apps, add an audio-visual check of whether lip shapes match the sounds, and add real Indian video
   to cut the "suspicious" verdicts on grainy real clips (5 of 15 Celeb-DF/DFD real clips).
2. **Indian voices.** Real speech in Malayalam, Hindi and Indian English, recorded on phones and through
   WhatsApp, so it stops flagging everyday microphones.
3. **Verify Content Credentials** cryptographically, instead of only reading them.
4. **Attack ourselves.** Run adversarial and re-compression attacks, then train against them.
5. **A bigger, independent test** with thousands of files collected by someone else, and a study of whether our
   explanations actually help people decide.
6. **Pulse detection.** Real skin shows a faint colour change with every heartbeat (remote photoplethysmography),
   and generated faces usually don't.

---

## Lightning round (one or two sentences each)

- **How does this fit "Intelligence Beyond Humans"?** AI now makes faces that humans can't tell apart (48.2% in
  one 2022 study on GAN faces).
  VERITAS uses machine intelligence to see what eyes can't, like frequency grids, sensor grain and blink
  statistics. Our results show machines fail too, so the final call stays human.
- **Why does the story say 468 points and the lab 478?** The classic MediaPipe face mesh has 468 points. The newer
  Face Landmarker adds 10 iris points, 5 per eye.
- **Why the bands 35 and 65?** So the tool can say "not sure". For the accuracy numbers we use one cut-off at 50.
  On the held-out photos, 5 of 104 landed in the "suspicious" band.
- **What does "confidence" mean?** It measures how much the tests agree, blended with how far the score is from 50.
  It is *not* the probability of being right.
- **How long does an analysis take?** On the development laptop, a photo takes about 0.9 s, a voice clip 0.3–1.6 s
  and a video 4–6 s. On a slow 4-core stand-in, roughly 3–5 s, 2–4 s and 23–32 s (the face-swap detector adds
  13–19 s of that).
- **What is the SHA-256 for?** It's a fingerprint of the exact bytes. Change one bit and it changes completely.
  It proves which file was checked.
- **What does YuNet do?** It's a tiny face-finding network (228 KB). We only score faces it is at least 85% sure
  of, and that fill at least 8% of the picture's short side.
- **How is this different from commercial tools?** They are trained on far more data and are better at
  face-swaps. Ours differs in three ways: it works offline, it explains every test, and it publishes its failures.
  We don't claim to beat them.
- **Why "VERITAS"?** It's Latin for "truth".
- **A GAN in one sentence?** Two networks in a contest. One forges images and one judges them, until the judge
  can only guess.
- **Diffusion in one sentence?** A network learns to remove noise step by step. Start it from pure static and it
  "removes noise" until a brand-new image appears.
- **What surprised you most?** Our first voice results looked great until we left a whole dataset out of tuning.
  Then accuracy fell to chance. It had learned the microphone, not the voice.

## Words to avoid

"100% accurate" · "detects all deepfakes" · "can't be fooled" · "proof" · "we trained the AI" (say *which* small
model you trained) · "our face-swap model" (say "the published detectors we benchmarked and chose") ·
"0.998 means it's perfect" (say "on 30 clips from datasets it wasn't trained on; the plausible range is 0.87 to
1.00, and 5 real clips came out suspicious") · "unseen datasets" (GenD's checkpoint was picked on Celeb-DF++ videos:
say "datasets neither network was trained on") · "real-world accuracy"
(say "on our held-out test").
