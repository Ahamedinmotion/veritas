# VERITAS story site: sources, verification notes and asset credits

Every number on `web/index.html` is listed here with its source. Each one was checked by web search on 18 Nov 2026.
The numbered `[n]` tags on the page match the reference list at the bottom of the page (chapter 08) and the list below.
The page shows plain-text citations only, with no external links, because the booth runs fully offline.

## Chapter 01 · The Threat

| On page | Claim | Source | Notes |
|---|---|---|---|
| [1] | Jan 2024, Hong Kong: an Arup employee joined a deepfaked video call (the CFO and colleagues), made **15 transfers to 5 bank accounts**, total **HK$200 million ≈ US$25.6 million**. Police quote: "everyone [he saw] was fake". Arup confirmed it in May 2024. | SCMP, 17 May 2024, "UK multinational Arup confirmed as victim of HK$200 million deepfake scam…" (scmp.com/news/hong-kong/law-and-crime/article/3263151); CNN, 4 Feb 2024; Building.co.uk / Construction Briefing coverage | Outlets convert HK$200M at different rates: some say US$25M, some US$25.6M, some ~US$26M. We use ≈US$25.6M. The police quote comes from the Feb 2024 HK Police briefing as reported by CNN and SCMP. |
| [2] | Jan 2024 New Hampshire primary robocalls used an AI clone of the U.S. President's voice and told voters not to vote. On **8 Feb 2024** the FCC ruled that AI voices are "artificial" under the TCPA (Declaratory Ruling FCC 24-17). The FCC proposed a **US$6 million** fine against the consultant (May 2024). | FCC DOC-402762A1 / FCC 24-17; NPR, 23 May 2024; AP coverage | Separately, Lingo Telecom settled for US$1M. The page gives the timeline as: ruling in February, fine proposed in May, finalised September 2024. |
| [3] | **3 seconds** of audio produced an **85% voice match** in McAfee researchers' tests. **47%** of Indian adults surveyed had experienced, or knew someone who had experienced, an AI voice scam, against a **25%** global average. | McAfee, "Beware the Artificial Impostor" (May 2023), mcafee.com/blogs/privacy-identity-protection/artificial-imposters-cybercriminals-turn-to-ai-voice-cloning-for-a-new-breed-of-scam/; Business Today (2 May 2023); Digital Terminal | The 3 s / 85% figure is McAfee's own benchmark, not a peer-reviewed result, and the page wording says so ("in McAfee researchers' tests"). Sources give the sample as 7,054 adults in 7 countries; a few say 9. |
| [4] | **10×** rise in deepfake incidents detected worldwide, 2022 → 2023 | Sumsub Identity Fraud Report 2023, press release 28 Nov 2023 (sumsub.com/newsroom/sumsub-research-global-deepfake-incidents-surge-tenfold-from-2022-to-2023/) | This is vendor data. The page labels it "vendor data" and describes it as incidents "caught by one global identity-verification company". |
| [5] | A deepfake attempt **every five minutes** (on average) in 2024 | Entrust Cybersecurity Institute / Onfido, 2025 Identity Fraud Report, press release Nov 2024 (entrust.com/company/newsroom/deepfake-attacks-strike-every-five-minutes-amid-244-surge-in-digital-document-forgeries) | Covers Sept 2023 to Aug 2024. Also vendor data. |
| [6] | Gen-AI-enabled fraud losses in the U.S. could reach **US$40 billion by 2027**, up from **US$12.3 billion in 2023** (32% CAGR) | Deloitte Center for Financial Services, "Generative AI is expected to magnify the risk of deepfakes and other fraud in banking", May 2024 | US$40B is Deloitte's *aggressive-adoption* scenario. The page words it as "could reach". |

## Chapter 03 · Can you tell?

| [7] | People judging real faces against StyleGAN2 faces were **48.2%** accurate, close to chance (the page says "no better than flipping a coin"). AI faces were rated **more trustworthy** (4.82 vs 4.48 on a 1–7 scale, ≈7.7%). | Nightingale & Farid, "AI-synthesized faces are indistinguishable from real faces and more trustworthy", PNAS 119(8) e2120481119, 2022 (pmc.ncbi.nlm.nih.gov/articles/PMC8872790) | Experiment 1 had 315 participants. With training (Exp. 2) accuracy only rose to 59.0%. |
|---|---|---|---|

## Chapter 02 / 04 · Science references

- [8] Goodfellow et al., "Generative Adversarial Nets", NeurIPS 2014 (GAN minimax objective).
- [9] Ho, Jain & Abbeel, "Denoising Diffusion Probabilistic Models", NeurIPS 2020. The forward process is x_t = √ᾱ_t·x₀ + √(1−ᾱ_t)·ε with a linear β schedule from 1e-4 to 0.02 over T = 1000 steps; the demo uses these exact values.
- [10] N. Krawetz, "A Picture's Worth: Digital Image Analysis and Forensics", Black Hat 2007 (Error Level Analysis).
- [11] Odena, Dumoulin & Olah, "Deconvolution and Checkerboard Artifacts", Distill 2016. Frank et al., "Leveraging Frequency Analysis for Deep Fake Image Recognition", ICML 2020.
- [12] Soukupová & Čech, "Real-Time Eye Blink Detection using Facial Landmarks", CVWW 2016 (the EAR formula). Li, Chang & Lyu, "In Ictu Oculi", IEEE WIFS 2018 / arXiv:1806.02877. The paper states: "The mean resting blinking rate is 17 blinks/min", a blink lasts 0.1–0.4 s, and AI faces lacked blinking because "most training datasets do not contain faces with eyes closed".
- [13] Kartynnik et al., "Real-time Facial Surface Geometry from Monocular Video on Mobile GPUs", 2019 (MediaPipe Face Mesh, 468 landmarks).
- [21] Rössler et al., "FaceForensics++", ICCV 2019 (the autoencoder "DeepFakes" face-swap method).
- [22] Wang et al., "Neural Codec Language Models are Zero-Shot Text to Speech Synthesizers" (VALL-E), 2023. The abstract states synthesis "with only a 3-second enrolled recording of an unseen speaker". Kong et al., "HiFi-GAN", NeurIPS 2020 (neural vocoder).
- [18] Goodfellow, Shlens & Szegedy, "Explaining and Harnessing Adversarial Examples", ICLR 2015 (FGSM, x′ = x + ε·sign(∇ₓL)).
- [19] Ojha, Li & Lee, "Towards Universal Fake Image Detectors that Generalize Across Generative Models", CVPR 2023 (detectors fail to generalise to unseen generators).

## Chapter 07 · Provenance, watermarks, law

| [14] | C2PA was formed on **22 Feb 2021** by Adobe, Arm, BBC, Intel, Microsoft and Truepic. Its signed manifest includes a SHA-256 hash of the content. | Microsoft News, 22 Feb 2021; Adobe blog, 22 Feb 2021; C2PA Technical Specification | Spec v1.0 was published in Jan 2022. |
|---|---|---|---|
| [15] | **Over 10 billion** pieces of content had been watermarked with SynthID (as of the 20 May 2025 announcement) | Google, "SynthID Detector — a new portal to help identify AI-generated content", blog.google, 20 May 2025 | This was the figure on the announcement date, and the page says "by May 2025". |
| [16] | India: IT (Intermediary Guidelines and Digital Media Ethics Code) Amendment Rules, 2026 were **notified 10 Feb 2026** and came **in force 20 Feb 2026**. They require labelling of "synthetically generated information". | Business Today (10 Feb 2026), Khaitan & Co, Mondaq, Bar & Bench | Summaries differ on the details of the verification duties. The page states only that labels are required. |
| [17] | EU AI Act Article 50 deepfake-disclosure obligations apply from **2 Aug 2026** | Regulation (EU) 2024/1689; Travers Smith, CSA research note (Jul 2026) | For generative systems already on the market, the deadline for machine-readable marking is 2 Dec 2026. The page does not mention this. |

## Things on the page that are illustrations (labelled as such on screen)

- **GAN training canvas.** The training is simulated. The face points come from the MediaPipe mesh. D(G(z)) follows a smooth curve towards ½ and is not measured.
- **Autoencoder swap faces.** These are abstract meshes, warped versions of the MediaPipe canonical face, not real people.
- **Voice pipeline.** Waveforms and the mel-spectrogram are procedural, not a real voice.
- **Spectrogram (Exhibit I).** The harmonics are synthesised. The "clone" has a hard 8 kHz ceiling, flatter F0 and no breaths.
- **Blink / EAR.** An animated eye with a scheduled blink pattern. The EAR value really is computed from the six animated points.
- **Landmark jitter.** The MediaPipe mesh with simulated head motion and jitter. J is computed from that simulation.
- **Pipeline (chapter 05).** The six detector scores are the **real engine output** for the FaceForensics++ "Deepfakes" face-swap clip 069 (`results.json` `video.clips`: AI-face 89, AI-image 92, blink 15, jitter 12, flicker 88, metadata 40), labelled REAL ENGINE OUTPUT. The six tests and base weights are the video pipeline's (`server/config.py` `DEFAULT_WEIGHTS["video"]`), and the fused score **76** and confidence **0.63** are computed by `web/js/story/system.js`, a line-for-line port of `server/fusion.py` (log-odds weighted mean, specific classic-test anomalies amplified up to 3×, calibrated sigmoid; video uses gain 1, bias 0). The engine itself reported 76 for this clip. The formula on the slide, S = 100·σ(z), z = a·Σ wᵢ·ln(sᵢ/(100−sᵢ)) + b, is the engine's; wᵢ are normalised to sum to 1, and for photos a = 1.67, b = 0.5 (fitted 1.71, capped at ±0.5). "Confidence" is an agreement index (0.45·agreement + 0.55·distance from 50), not a probability. The pretrained networks are credited on the slide and as refs [23]–[25].
- **Limits.** The "seen vs unseen" bars and the adversarial verdict flip (94 → 11) are illustrations, and both are labelled ILLUSTRATION. No adversarial attack was run on VERITAS.

## Things on the page that are real computations

- **ELA (Exhibit B)** is real ELA on a forgery the team made, produced by `web/assets/story/tools/make_ela.py`. Steps: the CC0 photo is downscaled; sensor-like noise (σ≈3.2) is added and the image is saved at JPEG q80. A palm tree is copied from the high-res original, shrunk to 30% and pasted, and the result is saved at q92. ELA is the difference after re-saving at q80. In the pasted leaves the measured error is **2.49×** that of the real palm's leaves (`forensics/ela-meta.json`).
- **Noise residual (Exhibit C)** uses r = I − median3×3(I) and a local RMS over 15×15 px. The pasted patch's sky has **2.43×** less noise than the surrounding sky. The live readout inverts the colour map, ignores textured pixels (map level > 0.55: leaves, edges), and compares the median of the remaining flat pixels inside the dashed probe circle with the median noise of the sky. In the quiet gap under the pasted palm's fronds it reads ≈0.44× SKY ("TOO QUIET — INCONSISTENT"); in open sky ≈0.9–1.0×; over trees it says it can't judge.
- **FFT (Exhibit D)** runs a radix-2 2-D FFT live in the browser on a 256×256 tile of the photo. The "GAN-style" tile multiplies the photo by the imprint of two stride-2 transposed-convolution layers with an uneven kernel [0.47, 1, 0.47]. The peak ratio is measured live at the four diagonal N/4 frequencies.
- **JPEG double quantisation (Exhibit E)** computes the DCT coefficient (0,1) live for 6,144 8×8 blocks of the photo, quantised with q=3 versus q₁=5 → q₂=3. The quantisation tables are the standard JPEG luminance table (Annex K) scaled to quality 85 and 78.
- **Diffusion (2C)** is the real DDPM forward process on the photo, using a fixed Gaussian ε. The "Rewind the noise" button runs the same formula with t decreasing, which only works because x₀ and ε are known; the caption says a real model must predict ε at every step and ends at a new image.
- **Metadata (Exhibit F, card F-1)** shows the real EXIF of the CC0 photo: Canon EOS Digital Rebel XT, 55 mm, 1/250 s, f/11, ISO 400, 2010-05-12 20:26:13, 3456×2304.
- **Hero "SWAPPED REGION % OF SCANNED"** is computed from the point cloud: the share of scanned points that fall in the simulated swapped inner-face region. It is labelled ILLUSTRATION on screen.

## Results (chapter 06)

The chapter renders only `web/data/results.json`, which `scripts/evaluate.py` writes. If that file is missing, the page shows "Results pending" and no numbers.

- **Frame 06 (images).** Headline tiles, confusion matrix, ROC and per-test AUC come from the top-level `metrics`, `confusion`, `roc`, `per_test` (the held-out image test only). The scope line derives n and the real/fake split from the confusion matrix (tn+fp real, tp+fn fake), not from `dataset.real/fake` (those are the whole pool, calibration included). "Re-saved as JPEG qNN · metadata stripped" is shown when `image_details.condition` is `laundered`, with NN parsed from `dataset.split`. The "fakes flagged / real photos wrongly flagged" chips come from `image_details.by_group` (count = n × flagged_pct). The source list (`dataset.sources`) is never printed on the page; it lives in results.json and docs/DATA_SOURCES.md.
- **Frame 06 caveats.** Under the tiles: the PRECISION subtitle reads "0 of 49 false alarms"; the method line adds exact (Clopper-Pearson) 95% ranges computed in the page from the confusion matrix (accuracy 84–96%, false-alarm rate 0–7%) and says the pretrained AI-image network was trained on FFHQ and COCO, the source of 42 of the 49 real test photos. An extra chip "Real video stills* 5/12" comes from `image_details.external_video_stills.real_as_photo`. The AI-model bars are labelled "(pretrained)".
- **Frame 06·2 (voices and the hard cases).** Left: the 10 outside voice clips (`audio.external.clips`), one row per clip, headed by two numbers, FAKES CAUGHT 2/6 and REAL CLEARED 4/4 (score > 50 = flagged); the AUC 0.92 is in the note with "from only 4 real and 6 fake clips", and the note says speaker 260 and the HiFi-GAN vocoder type were in tuning. Middle: the leave-one-dataset-out stress test (`audio.generalisation`) under the in-distribution reference bar (75.7%), plus the red FLEURS false-alarm box. (Without a `video.benchmark` block, a third panel shows the 10 research videos as a spot check, as before.) Clip file names are never shown, only labels such as "Face-swap · FF++".
- **Frame 06·3 (video: face-swaps, before and after; added 19 Nov, wording corrected after review).** Reads `video.benchmark` (written by `scripts/evaluate_video.py`, the full engine on 75 leak-free research clips). Left: Celeb-DF + Google DFD (`parts.cross`, 15 real + 15 fake), headed "NOT IN TRAINING" (not "unseen": GenD's authors chose their checkpoint using Celeb-DF++ videos, and our pre-registered rule ranked the candidates on these clips): AUC of the verdict score before → after with **Newcombe Wilson-type 95% intervals** (`auc_ci95_newcombe`: 0.87–1.00 after; the stratified bootstrap's 0.987–1.000 is too narrow at the ceiling) and the paired-bootstrap gain (`cross_gain`), fakes called synthetic and reals **not** called authentic before → after, and the verdict split as stacked bars; the note gives the cost (reals called suspicious, webcam-degraded reals). Middle: AUC by dataset and by FF++ method (`parts.*`, `per_method`, 2 decimals), with the clip counts and the Celeb-DF++ caveat in the note. Right: the 10 booth clips (`video.clips`, `score` and `before`), the tick = the score before the face-swap detector, ✓ = right side of 50; † marks the FF++ #069 clips in GenD's training data, ‡ (`celebdf_train_portion`) the Celeb-DF id2 pair from Celeb-DF's training portion; only the Wav2Lip clip is a fully unseen catch. The footer credits the pretrained networks [27][28] (two of the 6 benchmarked), says the pre-registered rule picked B7 alone, that GenD was added after seeing the results and that the two tie. No latency on the slide (dev-Mac speed would mislead; see PITCH). "Before" = the same reports fused without the face-swap test.
- **Exhibit J (chapter 04, face-swap detector).** Text facts: CLIP pretraining on 400 million image–text pairs (Radford et al. 2021); GenD re-tunes only LayerNorm parameters, 0.03% of the weights (Yermakov et al. 2026); DFDC: more than 100,000 clips of 3,426 paid actors (Dolhansky et al. 2020). The schematic is an ILLUSTRATION. Chapter 05's detector list and gauge use the engine's real output for the Wav2Lip clip (70, confidence 0.49; 14 without the face-swap test), checked against `server/fusion.py`.

`web/data/results.example.json` is for layout testing only. It is loaded only with `?results=example`, and the page then shows a large "EXAMPLE DATA · NOT OUR RESULTS" watermark.

## Chapter 03 card choice

The three inline cards are picked from `web/samples/game/manifest.json` (`ai_score` is the engine's fused 0–100 score): the highest-scoring GAN face (fake), the lowest-scoring real face photo, and the highest-scoring other AI image, so the reveal shows decisive engine scores. Under each answer the page shows "VERITAS SCORE" on the 0–100 scale.

## Asset credits

- **Photo:** "A Houseboat in Backwaters of Kerala", Wikimedia Commons, **CC0** (upload.wikimedia.org/wikipedia/commons/3/38/A_Houseboat_in_Backwaters_of_Kerala.jpg). The team derived the spliced, noised and re-compressed versions.
- **Face mesh:** MediaPipe `canonical_face_model.obj` and `face_mesh_connections.py` (google-ai-edge/mediapipe, Apache-2.0), baked into `web/assets/story/face.json` by `web/assets/story/tools/bake_face.py`.
- **Math symbols:** a subset of IBM Plex Math (SIL OFL 1.1, `web/assets/story/fonts/OFL-IBM-Plex.txt`). It supplies ∑ √ ‖ 𝔼 𝒩 arrows and Greek, which the shared latin-only fonts lack.
- **Libraries (vendored):** GSAP 3.15.1 with ScrollTrigger and SplitText (standard no-charge license), Lenis 1.3.27 (MIT), three.js 0.187.0 (MIT).
