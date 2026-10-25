import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from noah.domain import new_card,validate,CardError,ELEMENTS_PRIMARY,ELEMENTS_SECONDARY,SLOTS
from noah.photos import read_photo,encode_crop,decode_portrait,PHOTO_SIZE
from noah.storage import save,load

class RevisionTests(unittest.TestCase):
    def test_dropdown_lists(self):
        self.assertEqual(ELEMENTS_PRIMARY,['火','水','冰','电','磁','音','气','风','岩','金','光','暗'])
        self.assertEqual(ELEMENTS_SECONDARY,ELEMENTS_PRIMARY+['生命','情绪','社会','语言','概念'])
        c=new_card(); c['crystal']['属性一']='生命'
        with self.assertRaises(CardError): validate(c)
        c['crystal']['属性一']='火'; c['crystal']['属性二']='生命'; validate(c)
    def test_signed_fields_validate_independently(self):
        c=new_card()
        for name in ['活跃度','烈性','适配度']:
            c['crystal'][name+'符号']='-'; c['crystal'][name]=30; validate(c)
            c['crystal'][name]=-30
            with self.assertRaises(CardError): validate(c)
            c['crystal'][name]=30; c['crystal'][name+'符号']='invalid'
            with self.assertRaises(CardError): validate(c)
            c['crystal'][name+'符号']='+'
    def test_removed_fields_are_not_active(self):
        c=new_card(); self.assertNotIn('skills',c); self.assertNotIn('开发描述',c['crystal']); self.assertNotIn('证件照路径',c['basic'])
        self.assertEqual(SLOTS,['赋能笔','蓄能器','抑制器','变形重组器','中枢核心'])
        c['skills']={}
        with self.assertRaises(CardError): validate(c)
    def test_photo_crop_uses_selected_region(self):
        image=Image.new('RGB',(200,140),'red'); image.paste('blue',(100,0,200,140))
        photo=encode_crop(image,(100,0,200,140)); output=decode_portrait(photo)
        self.assertEqual(output.size,PHOTO_SIZE); self.assertEqual(output.getpixel((120,168)),(0,0,255))
    def test_photo_survives_json_without_source_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'photo.jpg'; Image.new('RGB',(400,560),'green').save(source)
            image=read_photo(source); c=new_card(); c['portrait']=encode_crop(image,(0,0,400,560)); save(root/'人物.json',c); source.unlink()
            restored=load(root/'人物.json'); self.assertEqual(restored,c); self.assertEqual(decode_portrait(restored['portrait']).size,PHOTO_SIZE)
            self.assertEqual(json.loads((root/'人物.json').read_text(encoding='utf-8'))['version'],2)
    def test_photo_formats_and_broken_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for suffix,fmt in [('jpg','JPEG'),('png','PNG'),('bmp','BMP'),('gif','GIF'),('webp','WEBP')]:
                path=root/('image.'+suffix); Image.new('RGB',(100,140),'white').save(path,format=fmt)
                self.assertEqual(read_photo(path).size,(100,140))
            path=root/'invalid.jpg'; path.write_bytes(b'not an image')
            with self.assertRaises(ValueError): read_photo(path)
    def test_embedded_image_rejects_bad_data_and_dimensions(self):
        c=new_card()
        for data in ['not!base64',base64.b64encode(b'bad').decode(),'A'*600001]:
            c['portrait']['data']=data
            with self.assertRaises(CardError): validate(c)
        output=io.BytesIO(); Image.new('RGB',(500,500)).save(output,format='PNG'); c['portrait']['data']=base64.b64encode(output.getvalue()).decode()
        with self.assertRaises(CardError): validate(c)
    def test_unsupported_old_schema_is_rejected_without_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'old.json'; c=new_card(); c['version']=1; path.write_text(json.dumps(c),encoding='utf-8')
            with self.assertRaises(CardError): load(path)
    def test_normalized_photo_strips_exif(self):
        image=Image.new('RGB',(200,280),'white'); exif=Image.Exif(); exif[315]='private source metadata'; image.info['exif']=exif.tobytes()
        photo=encode_crop(image,(0,0,200,280))
        with Image.open(io.BytesIO(base64.b64decode(photo['data']))) as normalized:
            self.assertNotIn('exif',normalized.info)
