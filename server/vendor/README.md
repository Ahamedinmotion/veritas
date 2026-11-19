# Vendored third-party code

| folder | from | licence | why vendored |
|---|---|---|---|
| `facenet_pytorch/` | facenet-pytorch 2.6.0 wheel (github.com/timesler/facenet-pytorch): `models/mtcnn.py`, `models/utils/detect_face.py` (unchanged), `data/{pnet,rnet,onet}.pt` (MTCNN weights) | MIT, (c) 2019 Timothy Esler (`facenet_pytorch/LICENSE.md`) | The face detector of the DFDC-winning EfficientNet-B7 in the face-swap test (`server/forensics/face_swap.py`). The wheel's metadata pins torch<2.3 / numpy<2 / Pillow<10.3, so it cannot be installed normally next to the engine's locked versions; the code works unchanged with them. |

SHA-256 of the weights (identical to the wheel):

```
a2a71925e0b9996a42f63e47efc1ca19043e69558b5c523b978d611dfae49c8f  facenet_pytorch/data/pnet.pt
bbb937de72efc9ef83b186c49f5f558467a1d7e3453a8ece0d71a886633f6a86  facenet_pytorch/data/rnet.pt
165bfbe42940416ccfb977545cf0e976d5bf321f67083ae2aaaa5c764280118d  facenet_pytorch/data/onet.pt
```
