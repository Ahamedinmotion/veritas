"""Vendored from facenet-pytorch 2.6.0 (https://github.com/timesler/facenet-pytorch, MIT, (c) 2019 Timothy Esler).

Only the MTCNN face detector is kept: models/mtcnn.py and models/utils/detect_face.py are byte-for-byte copies of the
2.6.0 wheel, data/{pnet,rnet,onet}.pt are its bundled weights (SHA-256 in server/vendor/README.md). We vendor it
instead of `pip install facenet-pytorch` because that wheel's metadata pins torch<2.3, numpy<2 and Pillow<10.3,
which would fight the engine's locked versions; the MTCNN code itself works unchanged with them (verified in the
19 Nov 2026 benchmark). It needs torchvision (batched_nms) - in pyproject.toml. Nothing here downloads anything.
"""
import warnings

warnings.filterwarnings(action="ignore", message="This overload of nonzero is deprecated:\n\tnonzero()",
                        category=UserWarning)

from .models.mtcnn import MTCNN  # noqa: E402,F401
