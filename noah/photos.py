"""Bounded photo import; embedded normalized PNG contains no external paths or metadata."""
import base64
import binascii
import io
from functools import lru_cache
from pathlib import Path
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

PHOTO_SIZE=(240,336)
MAX_SOURCE_BYTES=20*1024*1024
MAX_PIXELS=25_000_000
MAX_ENCODED=600_000


def read_photo(path):
    try:
        with Path(path).open('rb') as stream: raw=stream.read(MAX_SOURCE_BYTES+1)
        if len(raw)>MAX_SOURCE_BYTES: raise ValueError('图片超过20MB限制')
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'JPEG','PNG','WEBP','BMP','GIF'}: raise ValueError('仅支持JPEG、PNG、WebP、BMP、GIF图片')
                if image.width*image.height>MAX_PIXELS: raise ValueError('图片超过2500万像素限制')
                return ImageOps.exif_transpose(image).convert('RGB')
    except (OSError,UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('无法读取图片或图片尺寸过大') from exc


def encode_crop(image,box):
    x0,y0,x1,y1=box
    if not (0<=x0<x1<=image.width and 0<=y0<y1<=image.height): raise ValueError('裁剪区域超出图片范围')
    image=image.crop(box).resize(PHOTO_SIZE,Image.Resampling.LANCZOS).convert('RGB')
    image.info.clear()  # Do not carry EXIF or source metadata into the embedded PNG.
    output=io.BytesIO(); image.save(output,format='PNG',optimize=True)
    return {'mime':'image/png','data':base64.b64encode(output.getvalue()).decode('ascii')}


@lru_cache(maxsize=8)
def _decode(data):
    if len(data)>MAX_ENCODED: raise ValueError('证件照数据过大')
    try:
        raw=base64.b64decode(data,validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format!='PNG' or image.size!=PHOTO_SIZE: raise ValueError('证件照必须是240×336的PNG')
            image.load(); return image.convert('RGB')
    except (ValueError,OSError,binascii.Error,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('证件照数据无效，请重新上传') from exc


def validate_portrait(photo):
    if not isinstance(photo,dict) or set(photo)!={'mime','data'} or photo.get('mime')!='image/png' or not isinstance(photo.get('data'),str): raise ValueError('证件照结构不正确')
    if photo['data']: _decode(photo['data'])


def decode_portrait(photo):
    validate_portrait(photo)
    return _decode(photo['data']).copy() if photo['data'] else None

