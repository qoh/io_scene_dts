import os

from colorsys import hsv_to_rgb
from itertools import count
from fractions import Fraction

texture_extensions = ("png", "jpg")

default_materials = {
    "black": (0, 0, 0),
    "black25": (191, 191, 191),
    "black50": (128, 128, 128),
    "black75": (64, 64, 64),
    "blank": (255, 255, 255),
    "blue": (0, 0, 255),
    "darkRed": (128, 0, 0),
    "gray25": (64, 64, 64),
    "gray50": (128, 128, 128),
    "gray75": (191, 191, 191),
    "green": (26, 128, 64),
    "lightBlue": (10, 186, 245),
    "lightYellow": (249, 249, 99),
    "palegreen": (125, 136, 104),
    "red": (213, 0, 0),
    "white": (255, 255, 255),
    "yellow": (255, 255, 0)
}

for name, color in default_materials.items():
    default_materials[name] = (color[0] / 255, color[1] / 255, color[2] / 255)

for key, value in tuple(default_materials.items()):
    default_materials[key.lower()] = value

def resolve_texture(filepath, name):
    dirname = os.path.dirname(filepath)

    while True:
        texbase = os.path.join(dirname, name)

        for extension in texture_extensions:
            texname = texbase + "." + extension

            if os.path.isfile(texname):
                return texname

        if os.path.ismount(dirname):
            break

        prevdir, dirname = dirname, os.path.dirname(dirname)

        if prevdir == dirname:
            break

def fractions():
    yield 0

    for k in count():
        i = 2 ** k

        for j in range(1, i, 2):
            yield j / i

def get_hsv_colors():
    for h in fractions():
        yield (h, 0.75, 0.75)

def get_rgb_colors():
    return map(lambda hsv: hsv_to_rgb(*hsv), get_hsv_colors())
