"""Synthetic fixture for reproducible integration checks; not a real accuracy dataset."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
out = root / 'tests' / 'fixtures'
out.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype(str(root/'static/vendor/NotoSansThai-Regular.ttf'), 38)
latin = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 34)
bold = ImageFont.truetype(str(root/'static/vendor/NotoSansThai-Bold.ttf'), 46)
image = Image.new('RGB', (1000,1300), 'white')
draw = ImageDraw.Draw(image)
draw.text((80,65), 'ร้านทดสอบ', font=bold, fill='black')
draw.text((80,150), 'SYNTHETIC TEST / NOT A REAL PURCHASE', font=latin, fill='black')
draw.text((80,230), 'DATE 2026-10-19', font=latin, fill='black')
draw.line((80,320,920,320),fill='black',width=2)
draw.text((80,370),'ขนมปัง',font=font,fill='black')
draw.text((420,375),'BREAD            15.50',font=latin,fill='black')
draw.text((80,470),'นม',font=font,fill='black')
draw.text((420,475),'MILK               30.00',font=latin,fill='black')
draw.line((80,570,920,570),fill='black',width=2)
for index,line in enumerate(['TOTAL                 45.50','CASH                  50.00','CHANGE                 4.50']):
    draw.text((80,620+index*90),line,font=latin,fill='black')
draw.text((80,1000),'ขอบคุณ',font=font,fill='black')
image.save(out/'synthetic_receipt.png')
print(out/'synthetic_receipt.png')
