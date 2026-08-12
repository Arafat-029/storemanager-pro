"""Fast, cached thumbnails for product and category photos.

Photos are stored exactly as the user picked them — straight from a phone or a
stock-photo site — so the files here run to 4000x5000 and beyond. Rendering a
66px category icon or a 220px card image from those cost ~100 ms apiece, and
both the Caisse and the Produits page rebuild their whole grid on every visit,
which turned into roughly a second of lag per page change.

Two levels fix that:

* decode at the target size (`_decode`) — QImageReader.setScaledSize() lets the
  JPEG decoder rescale while decoding, so cost no longer tracks the source
  file's resolution;
* cache the result on disk (`load_thumbnail`) — thumbnails are tiny and fully
  derived from the source file, so they survive restarts. The cache key carries
  the source's mtime and size, so replacing a photo invalidates its thumbnail
  on its own; the directory can be deleted at any time and is simply rebuilt.
"""
from __future__ import annotations

import hashlib
import math
import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImageReader, QPixmap

from config import THUMBNAIL_CACHE_DIR


def _decode(path: str, width: int, height: int) -> QPixmap:
    """Decode `path` straight to a centre-cropped width x height pixmap."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    source = reader.size()
    if source.isValid() and source.width() > 0 and source.height() > 0:
        ratio = max(width / source.width(), height / source.height())
        reader.setScaledSize(
            QSize(
                max(1, math.ceil(source.width() * ratio)),
                max(1, math.ceil(source.height() * ratio)),
            )
        )

    image = reader.read()
    if image.isNull():
        return QPixmap()

    pix = QPixmap.fromImage(image)
    if pix.width() < width or pix.height() < height:
        # Reader ignored the size hint (some formats do): plain rescale.
        pix = pix.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    return pix.copy(
        max(0, (pix.width() - width) // 2),
        max(0, (pix.height() - height) // 2),
        width,
        height,
    )


def load_thumbnail(path: str, width: int, height: int) -> QPixmap:
    """Centre-cropped width x height thumbnail of `path`, cached on disk.

    Returns a null pixmap if the file is missing or cannot be decoded.
    """
    try:
        stat = os.stat(path)
    except OSError:
        return QPixmap()

    key = f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{width}x{height}"
    cache_file = THUMBNAIL_CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()}.png"

    if cache_file.exists():
        cached = QPixmap(str(cache_file))
        if not cached.isNull():
            return cached

    pix = _decode(path, width, height)
    if pix.isNull():
        return pix

    try:
        THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        pix.save(str(cache_file), "PNG")
    except OSError:
        pass  # a read-only data dir must not break rendering

    return pix
