import os
import img2pdf
from PIL import Image    
with open("output.pdf", 'wb') as f:
    f.write(img2pdf.convert(sorted([i for i in os.listdir('.') if i.endswith(".jpg")], key=lambda fname: int(fname.rsplit('.',1)[0]))))