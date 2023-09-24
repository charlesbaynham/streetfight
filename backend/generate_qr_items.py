import sys

import qrcode
from PIL import Image
from PIL import ImageDraw


# A4 dimensions in pixels (approximately)
a4_width = 2480
a4_height = 3508

# Create an eighth-sized image
image_width = a4_width // 4
image_height = a4_height // 2
img = Image.new("RGB", (image_width, image_height), "white")
draw = ImageDraw.Draw(img)


with Image.open("qr_grid.png") as im:

    draw = ImageDraw.Draw(im)
    draw.line((0, 0) + im.size, fill=128)
    draw.line((0, im.size[1], im.size[0], 0), fill=128)

    # write to stdout
    im.save(sys.stdout, "PNG")
