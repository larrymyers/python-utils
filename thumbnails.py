import os

from PIL import Image

def generate_square_thumbnail(filename, th_height=128, th_width=128):
    img = Image.open(filename)
    
    # crop the original img to a square
    
    width, height = img.size
    
    left = 0
    upper = 0
    right = 0
    lower = 0
    
    if width > height:
        delta = width - height
        left = int(delta/2)
        upper = 0
        right = height + left
        lower = height
    else:
        delta = height - width
        left = 0
        upper = int(delta/2)
        right = width
        lower = width + upper
    
    img = img.crop((left, upper, right, lower))
    
    parts = os.path.splitext(filename)
    
    thumb = img.copy()
    thumb.thumbnail((th_height, th_width), Image.ANTIALIAS)
    thumb.save(parts[0] + '-thumbnail.png')

