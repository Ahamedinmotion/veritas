# Data sources and licences

Everything in `eval_data/` (gitignored, not shipped) was collected by `scripts/build_eval_data.py`,
`scripts/make_faceswap.py` and `scripts/make_synthetic_video.py`. The machine-readable list, one entry per file
with source URL and licence, is `eval_data/sources.json`. Only small, public, openly licensed sources were used.
We made no deepfake of anyone famous or anyone we know. Our own test fakes use research-dataset material only:
GAN faces of people who do not exist, pasted onto FFHQ/COCO photos (Flickr users); voice clones and vocoder
re-renderings of audiobook readers from LJ Speech and LibriSpeech (LibriVox, public-domain recordings); SpeechT5
voices conditioned on CMU-Arctic speakers; and one Wav2Lip lip-sync of Google DFD's consenting paid actor 07.
Every item is used only to test the detector.

## Images (171 files: 78 real, 93 synthetic)

| Set | n | Label | Source | Licence |
|---|---|---|---|---|
| FFHQ faces | 36 | real | Flickr-Faces-HQ (NVIDIA), via huggingface.co/datasets/marcosv/ffhq-dataset, 1024 px PNG | Individual photos CC BY 2.0 / CC BY-NC 2.0 / PD / CC0 (Flickr); dataset CC BY-NC-SA 4.0 |
| COCO scenes | 32 | real | MS-COCO val2017 via huggingface.co/datasets/LibreYOLO/coco-val2017-mini500 (16 with people, 16 without) | Flickr CC licences per image; COCO annotations CC BY 4.0 |
| Smartphone photos | 10 | real | Wikimedia Commons categories "Taken with Google Pixel 6 / Samsung Galaxy S21 5G / ..." - original files with camera EXIF | CC BY-SA 4.0 (authors listed below) |
| GAN faces | 36 | synthetic | StyleGAN2 faces from thispersondoesnotexist.com via huggingface.co/datasets/javi22/this-person-does-not-exist-10k | MIT (dataset card) |
| Diffusion images | 44 | synthetic | DALL-E 3, FLUX.1, Midjourney, Stable Diffusion - 11 each, about half with people; from huggingface.co/datasets/Rapidata/700k_Human_Preference_Dataset_FLUX_SD3_MJ_DALLE3 (COCO-style photo prompts) | CDLA-Permissive-2.0 |
| Face-swaps | 13 | synthetic | Made by our team with `scripts/make_faceswap.py`: a GAN face (non-existent person) warped onto a real FFHQ/COCO photo with MediaPipe landmarks, Delaunay triangles and Poisson blending. 3 composites whose target photo looked like a public figure (uniform with rank insignia, podium/stage) were deleted. | Derived from the two sources above |

## Audio (206 clips: 100 real, 106 synthetic)

| Set | n | Label | Source | Licence |
|---|---|---|---|---|
| LibriSpeech dev-clean | 12 | real | Read audiobook speech, ONE speaker (1272), via hf-internal-testing/librispeech_asr_dummy | CC BY 4.0 |
| LibriSpeech test-clean | 24 | real | One utterance from each of 24 different speakers (added 18 Nov after review: 12 clips of one narrator let the voice probe learn "this voice = real"), via openslr/librispeech_asr, trimmed to 14 s | CC BY 4.0 |
| FLEURS en_us dev | 24 | real | Volunteers reading Wikipedia sentences on their own microphones (varied rooms and mics), one clip per sentence, via google/fleurs, trimmed to 14 s | CC BY 4.0 |
| ASVspoof 2019 LA bona fide | 20 | real | VCTK speakers, evaluation set, via huggingface.co/datasets/SpeechAntiSpoofingBenchmarks/ASVspoof2019_LA | ODC-BY |
| UniData originals | 20 | real | Original recordings from huggingface.co/datasets/UniDataPro/real-vs-fake-human-voice-deepfake-audio | CC BY-NC-ND 4.0 - used for evaluation only, NOT redistributed |
| ASVspoof 2019 LA spoofs | 24 | synthetic | 13 TTS / voice-conversion systems (attacks A07-A19), 2 each | ODC-BY |
| UniData voice clones | 40 | synthetic | AI voice clones of the UniData speakers (2 per speaker) | CC BY-NC-ND 4.0 - evaluation only |
| MMS-TTS (VITS) | 8 | synthetic | Generated locally with facebook/mms-tts-eng, generic sentences | Model CC BY-NC 4.0 |
| SpeechT5 + HiFi-GAN | 8 | synthetic | Generated locally with microsoft/speecht5_tts, CMU-Arctic x-vector speaker embeddings | MIT |
| macOS `say` | 2 | synthetic | Samantha and Daniel system voices (classic concatenative/parametric TTS) | own recording |
| Vocoded LibriSpeech | 24 | synthetic | WaveFake-style matched pairs (added 18 Nov after review): each LibriSpeech test-clean clip above re-rendered from its own mel spectrogram by SpeechT5's HiFi-GAN vocoder. Same speaker, words and room - only the vocoder differs, so the voice probe cannot use "audiobook speech = real" as a shortcut. Evaluation only, never shipped | Derived from LibriSpeech (CC BY 4.0); vocoder MIT |

The calibration / held-out split is **group-aware** (`scripts/evalcommon.py assign_split`): all clips of one
speaker (and a real voice with its own clones), all images made from one text prompt, and every face-swap together
with its real target photo and its GAN donor face land on the same side of the split.

## External test media (`../_incoming/media/`, outside the repo; no number was fitted on them)

Collected by a separate sourcing job; full sources and licences in `../_incoming/media/SOURCES.md`.

| Set | n | What | Licence |
|---|---|---|---|
| Video | 10 | FaceForensics++ #069 original + Deepfakes / Face2Face / NeuralTextures; Google DFD actor 09 original + face-swap; Celeb-DF v2 real + synthesis; DFD actor 07 original + a Wav2Lip lip-sync | Research / non-commercial terms: shown offline at the fair only, **not redistributed** |
| Audio | 10 | LJSpeech real + WaveFake HiFi-GAN / WaveGlow + an F5-TTS clone; LibriSpeech speaker 260 real (x2) + Chatterbox / F5-TTS clones; ASVspoof 2019 bona fide + attack A10 | Per-source licences in SOURCES.md |

`scripts/evaluate.py` runs all 20 through the engine (results.json: `video.clips`, `audio.external`) and also
analyses 3 stills from each video as photos (`image_details.external_video_stills`).
Not fully unseen: LibriSpeech speaker 260 (4 of the 10 audio clips) and the HiFi-GAN vocoder type also appear in our
voice calibration split, and an earlier run on stills from these videos led us to redesign the image calibration.

## Video benchmark (75 clips: 35 real, 40 fake) - `eval_data/video_faceswap/` (gitignored), never shipped or shown
Used to choose and test the face-swap detector (docs/MODEL_SELECTION.md). Per-clip provenance (mirror, revision,
raw SHA-256, processing) is in `eval_data/video_faceswap/manifest.json`; why it is leak-free is in its `SPLITS.md`.
Every clip has `booth_display: false`: measurement only, never in `web/`, never redistributed.

| Set | n | What | Licence |
|---|---|---|---|
| FaceForensics++ c23, official **test** split | 20 real + 25 fake | YouTube originals; Deepfakes, FaceSwap, Face2Face, NeuralTextures, FaceShifter (5 each). Via the Hugging Face mirror gonnerthetooner/FaceForensics (re-upload of the Kaggle FF++ c23 bundle) | FaceForensics++ Terms of Use: non-commercial research and education only, no redistribution |
| Celeb-DF v2, official **test** list | 10 real + 10 fake | Celeb-real + YouTube-real; Celeb-DF synthesis. Via gonnerthetooner/deepfake_video_data | Celeb-DF Terms of Use: research only, no redistribution |
| Google DFD (DeepFakeDetection) | 5 real + 5 fake | Paid, consenting actors; fakes not in the Kaggle FF++ bundle | FaceForensics++ Terms of Use (DFD is distributed with FF++) |

All 75 were trimmed to 10 s and re-encoded identically (H.264 CRF 18, no audio, metadata stripped).

## Video tuning clips (6 clips: 3 real, 3 synthetic) - NOT a test

The hand-set video thresholds were chosen while looking at these, so they are listed in results.json as
`video.tuning_clips`, not as a result.

| Clip | Label | Source | Licence |
|---|---|---|---|
| `nasa_iss_message_crop.mp4` (18 s) | real | NASA astronaut graduation message from the ISS (2019), images.nasa.gov id `jsc2019m000386_Graduation_Message_2019-MP4`, trimmed 21-39 s and cropped around the face | Public domain (NASA) |
| `nasa_expert_blackhole_clip.mp4`, `nasa_expert_sun_clip.mp4` (3-4 s) | real | NASA "We Asked a NASA Scientist" videos ("What is a Black Hole", "Will the Sun Ever Burn Out"), talking-head segments | Public domain (NASA) |
| `animated_gan_face_1..3.mp4` (12-16 s) | synthetic | A StyleGAN face animated with a slow zoom/drift/tilt by `scripts/make_synthetic_video.py` ("talking photo" scam style) | MIT (source face dataset) |

**Real deepfake videos.** The research clips above (FaceForensics++, Google DFD, Celeb-DF, Wav2Lip) are the
honest video test. Our engine catches generated faces but misses most of them: its image network was never trained
on face-swaps, reenactment or lip-sync (see results.json `video`).

**Making your own ethical face-swap** (optional): record a consenting team member, then run
`uv run python scripts/make_faceswap.py --video real.mp4 --face eval_data/images/fake/tpdne_XXXXX.jpg --out fake.mp4`,
which pastes a StyleGAN face (a person who does not exist) onto every frame. Be ready for the engine to call the
result **authentic or only suspicious**: in the review test a visibly ghosted swap made this way scored 19, because
the classic Poisson-blended swap keeps the real video's skin texture and motion. It is a good demonstration of a
limitation, not of a detection.

## Demo samples shipped with the app (`web/samples/`)
Lab samples and game images are copies (game: re-encoded) of the files above; each `manifest.json` entry names
its source. CC BY-SA photos keep their licence and are credited in the manifest. UniData audio (NC-ND) is **not**
shipped. The game deliberately excludes photos of children, face-swaps made on photos of children, photos with a
public-figure context, crowds of identifiable bystanders (an inauguration ceremony) and political signage
(`scripts/game_exclude.json`); the private exhibit -> source key is `eval_data/game_key.json`. The game prefers
held-out files, but its engine score is not an evaluation result. It keeps one image per text prompt so a round
never shows the same scene twice (19 Nov: three near-duplicates of prompts 131 and 270 were replaced by
`diff_dalle-3_282_0`, `diff_flux_249_2` and `diff_stable_diffusion_230_0`; engine now right on 27 of 30).

Evidence locker (`web/samples/lab/`, 9 exhibits): the first 8 were **chosen to show each test working** (fakes the
engine scored above 70, reals below 20), so the locker is right on them by construction; the video exhibits are the
NASA clip and the animated-GAN recipe the video thresholds were tuned on (a demonstration, not a test). Exhibit I,
`missed-fake-voice.wav`, is a deliberate **miss**: WaveFake HiFi-GAN re-rendering of LJ Speech LJ001-0001
(WaveFake: CC BY-SA 4.0, Frank & Schönherr 2021; LJ Speech: public domain), engine score 34 = "authentic".

Attribution still to do before any public release: the game reveal cards credit FFHQ/COCO photos only as
"Real photo (FFHQ, Flickr)" / "(COCO, Flickr)". Each Flickr image's CC licence asks for the author's name, and
FFHQ itself is CC BY-NC-SA 4.0; per-image authors are in FFHQ's `ffhq-dataset-v2.json` and COCO's
`instances_val2017.json` (`license` field). Checked 19 Nov 2026 in COCO's `captions_val2017.json`: neither face-swap
target is NoDerivs. COCO 000000050811 (the lab face-swap) is licence 5, CC BY-SA 2.0 (Flickr photo 8133371246), so
our derivative `face-swap.jpg` is also CC BY-SA 2.0; COCO 000000012748 is licence 2, CC BY-NC 2.0 (Flickr 9090127695).

## Smartphone photo authors (CC BY-SA 4.0, Wikimedia Commons)

| File | Author | Licence | Page |
|---|---|---|---|
| `phone_1830_Sutter_Street__exterior__San_Francisco__March_202` | BriefEdits | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:1830_Sutter_Street,_exterior,_San_Francisco_(March_2024)_04.jpg |
| `phone_1_Chemin_Foret_Eisenborn_Luxembourg_2023_05__102__jpg.` | GilPe | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:1_Chemin_Foret_Eisenborn_Luxembourg_2023-05_(102).jpg |
| `phone_202104_WMTW_x_HPCF_workshop_415_jpg.jpg` | Natsu621 | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:202104_WMTW_x_HPCF_workshop_415.jpg |
| `phone_202104_WMTW_x_HPCF_workshop_416_jpg.jpg` | Natsu621 | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:202104_WMTW_x_HPCF_workshop_416.jpg |
| `phone_20220506TRA_EM903_4_Train_interiors_01_jpg.jpg` | 鐵路1 | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:20220506TRA_EM903_4_Train_interiors-01.jpg |
| `phone_20220507Changhua_Railway_Hospital_Interiors_02_jpg.jpg` | 鐵路1 | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:20220507Changhua_Railway_Hospital_Interiors-02.jpg |
| `phone_2024_09_10_80e_anniversaire_libération_ville_de_Luxemb` | GilPe | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:2024-09-10_80e_anniversaire_lib%C3%A9ration_ville_de_Luxembourg_(105).jpg |
| `phone_2025_03_02_Den_Tram_fiert_bis_op_de_Findel___inaugurat` | GilPe | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:2025-03-02_Den_Tram_fiert_bis_op_de_Findel_-_inauguration_(104).jpg |
| `phone__5_reliëfs__door_Oscar_Goedhart__Stadhuis__Nijmegen___` | FakirNL | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:%275_reli%C3%ABfs%27_door_Oscar_Goedhart,_Stadhuis,_Nijmegen_-_Reli%C3%ABf_1.jpg |
| `phone__Wächter_der_Bäume__Petrisberg_Trier_jpg.jpg` | Andy Dufresne & Red | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:%22W%C3%A4chter_der_B%C3%A4ume%22_Petrisberg_Trier.jpg |

## Models (see docs/MODEL_SELECTION.md)

| Role | Model | Licence |
|---|---|---|
| AI-generated image + face-crop detector | buildborderless/CommunityForensics-DeepfakeDet-ViT (Park & Owens, *Community Forensics*, CVPR 2025) | MIT |
| Synthetic speech detector | abhishtagatya/wav2vec2-base-960h-itw-deepfake (wav2vec2-base fine-tuned on In-the-Wild deepfake audio) | Apache-2.0 |
| Face detector | OpenCV Zoo YuNet `face_detection_yunet_2023mar.onnx` | MIT |
| Face landmarks | Google MediaPipe FaceLandmarker `face_landmarker.task` | Apache-2.0 |
| Face-swap detector, network 1 (video) | **GenD** CLIP ViT-L/14, huggingface.co/yermandy/GenD_CLIP_L_14 @891ce01 (Yermakov, Cech, Matas, Fritz, *Deepfake Detection that Generalizes Across Benchmarks*, WACV 2026), exported by us to ONNX (`models/face_swap/gend_clip.onnx`) | MIT (code and weights). Trained on FaceForensics++, so the FF++ Terms of Use (non-commercial research / education) apply to its use |
| CLIP backbone + preprocessing config | GenD's checkpoint **is** OpenAI's CLIP ViT-L/14 (Radford et al., ICML 2021) with only its LayerNorms and a linear head re-tuned, so 99.97 % of its weights are OpenAI's; they come inside GenD's checkpoint. `preprocessor_config.json` of openai/clip-vit-large-patch14 | MIT |
| Face-swap detector, network 2 (video) | **DFDC 1st-place EfficientNet-B7** (Selim Seferbekov, github.com/selimsef/dfdc_deepfake_challenge, release 0.0.1, checkpoint `final_999_DeepFakeClassifier_tf_efficientnet_b7_ns_0_23`), exported by us to ONNX (`dfdc_b7.onnx`). Its backbone started from the Noisy-Student ImageNet EfficientNet-B7 (`tf_efficientnet_b7_ns`; Q. Xie et al., *Self-training with Noisy Student improves ImageNet classification*, CVPR 2020) | MIT (code and weights). Trained on the DFDC dataset (Meta/Facebook DFDC terms: research) |
| GenD's face detector | **SCRFD-10G** `det_10g.onnx` from InsightFace `buffalo_l` (release v0.7), byte-identical | **InsightFace pretrained models: non-commercial research purposes only.** Fine for our offline, non-commercial school exhibit; must not be used commercially or redistributed with a product |
| B7's face detector | **MTCNN** from facenet-pytorch 2.6.0 (Tim Esler), code + `pnet/rnet/onet.pt` vendored in `server/vendor/facenet_pytorch/` | MIT |
| Runtime | ONNX Runtime 1.32 (MIT), torchvision 0.29 (BSD-3-Clause, for MTCNN's NMS) | MIT / BSD-3 |

None of the face-swap weights may be used commercially: GenD and B7 are MIT, but their training data (FaceForensics++,
DFDC) and the SCRFD detector are research/non-commercial. All of them allow an offline, non-commercial school
exhibit. If this repository is ever published, ship `scripts/download_models.py` (pinned upstream URLs + SHA-256),
not the weights.
