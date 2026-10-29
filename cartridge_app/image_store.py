"""Validated local background image storage (JPEG, PNG and WebP)."""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
import warnings
from pathlib import Path


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DIMENSION = 6000
MAX_PIXELS = 24_000_000
_FORMATS = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}


class ImageStoreError(ValueError):
    """A user-correctable image selection or local storage error."""


def _pillow():
    try:
        from PIL import Image, ImageFile
        return Image, ImageFile
    except ImportError as error:
        raise ImageStoreError(
            'Поддержка фоновых изображений недоступна в этой сборке. '
            'Обратитесь к администратору приложения.'
        ) from error


class ImageStore:
    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.directory = self.root_dir / 'settings_assets'

    def _validate(self, path):
        Image, ImageFile = _pillow()
        source = Path(path)
        try:
            size = source.stat().st_size
        except OSError as error:
            raise ImageStoreError('Не удалось прочитать выбранный файл.') from error
        if not source.is_file() or size <= 0:
            raise ImageStoreError('Выберите непустой файл изображения.')
        if size > MAX_FILE_BYTES:
            raise ImageStoreError('Размер изображения превышает 10 МБ.')
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(str(source)) as image:
                    fmt = image.format
                    width, height = image.size
                    if fmt not in _FORMATS:
                        raise ImageStoreError('Поддерживаются только JPEG, PNG и WebP.')
                    if width < 1 or height < 1 or width > MAX_DIMENSION or height > MAX_DIMENSION:
                        raise ImageStoreError('Разрешение изображения не должно превышать 6000 × 6000.')
                    if width * height > MAX_PIXELS:
                        raise ImageStoreError('Изображение слишком большое (максимум 24 мегапикселя).')
                    image.verify()
                # verify() checks structure, while load() confirms actual decoding.
                with Image.open(str(source)) as image:
                    if image.format != fmt or image.size != (width, height):
                        raise ImageStoreError('Файл изображения повреждён.')
                    image.load()
        except ImageStoreError:
            raise
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as error:
            raise ImageStoreError('Файл повреждён или не является поддерживаемым изображением.') from error
        return fmt, width, height, size

    def validate_and_save(self, source_path):
        fmt, width, height, size = self._validate(source_path)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ImageStoreError('Не удалось сохранить изображение в каталоге данных приложения.') from error
        filename = 'background-' + uuid.uuid4().hex + _FORMATS[fmt]
        target = self.directory / filename
        fd, temp_name = tempfile.mkstemp(prefix='.background-', suffix='.tmp', dir=str(self.directory))
        try:
            with os.fdopen(fd, 'wb') as destination, open(source_path, 'rb') as source:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            # Detect source changes between validation and copy before committing.
            if Path(temp_name).stat().st_size != size:
                raise ImageStoreError('Файл изменился во время сохранения. Выберите его ещё раз.')
            copied_fmt, copied_width, copied_height, _ = self._validate(temp_name)
            if (copied_fmt, copied_width, copied_height) != (fmt, width, height):
                raise ImageStoreError('Файл изменился во время сохранения. Выберите его ещё раз.')
            os.replace(temp_name, target)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
        return {'filename': filename, 'width': width, 'height': height, 'size_bytes': size}

    def _resolve(self, path):
        candidate = Path(path)
        if not candidate.is_absolute():
            if candidate.name != str(candidate) or candidate.name in ('', '.', '..'):
                raise ImageStoreError('Некорректный путь к фону.')
            candidate = self.directory / candidate
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.directory.resolve())
        except (OSError, ValueError) as error:
            raise ImageStoreError('Файл фона не найден в хранилище приложения.') from error
        if resolved.parent != self.directory.resolve() or not resolved.name.startswith('background-'):
            raise ImageStoreError('Некорректный путь к фону.')
        return resolved

    def load_image(self, path, max_size):
        Image, _ = _pillow()
        resolved = self._resolve(path)
        self._validate(resolved)
        try:
            image = Image.open(str(resolved))
            image.load()
            image.thumbnail(tuple(max_size), Image.Resampling.LANCZOS)
            return image
        except (OSError, ValueError) as error:
            raise ImageStoreError('Не удалось открыть сохранённое фоновое изображение.') from error

    def remove(self, filename):
        target = self._resolve(filename)
        target.unlink(missing_ok=True)

    def reset(self):
        """Remove only app-managed background assets, never inventory/preferences."""
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.directory.iterdir():
            if path.is_file() and path.name.startswith('background-'):
                path.unlink()
