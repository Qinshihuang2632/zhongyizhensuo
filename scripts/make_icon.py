"""生成应用图标：深青绿圆角底 + 白色葫芦剪影（悬壶济世）+ 叶柄点缀。

输出：
  assets/app.ico        多尺寸 Windows 图标（256/128/64/48/32/16）
  assets/icon_256.png   预览与 favicon 用
  frontend/public/favicon.ico  前端站点图标
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024  # 画布尺寸（超采样前）
FINAL = 256


def rounded_gradient_bg(size: int) -> Image.Image:
    """圆角方形背景，纵向双色渐变。"""
    top, bottom = (16, 122, 105), (4, 66, 57)  # #107a69 -> #044239
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    px = grad.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b, 255)
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def draw_gourd(img: Image.Image) -> None:
    """白色葫芦剪影 + 叶柄。坐标按 1024 画布。"""
    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    cx = S // 2
    # 上球（略小）、下球（略大），少量重叠形成葫芦腰
    top_r = 150
    bot_r = 205
    top_cy = 385
    bot_cy = 660
    d.ellipse([cx - top_r, top_cy - top_r * 0.92, cx + top_r, top_cy + top_r * 0.92], fill=white)
    d.ellipse([cx - bot_r, bot_cy - bot_r * 0.88, cx + bot_r, bot_cy + bot_r * 0.88], fill=white)
    # 葫腰收束：用背景色细弧在交叠处压出一条缝
    bg = (11, 94, 84, 255)
    d.arc([cx - 170, 455, cx + 170, 605], start=15, end=165, fill=bg, width=26)
    # 葫芦嘴（顶部小圆台）
    d.rounded_rectangle([cx - 52, 195, cx + 52, 265], radius=26, fill=white)
    # 叶柄：绿色短杆 + 两片小叶
    stem = (183, 226, 145, 255)  # 浅绿
    d.rounded_rectangle([cx - 12, 130, cx + 12, 205], radius=12, fill=stem)
    d.ellipse([cx - 110, 120, cx - 10, 180], fill=stem)
    d.ellipse([cx + 10, 120, cx + 110, 180], fill=stem)


def main() -> None:
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    img = rounded_gradient_bg(S)
    draw_gourd(img)
    final = img.resize((FINAL, FINAL), Image.LANCZOS)
    final.save(out / "icon_256.png")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    final.save(out / "app.ico", sizes=sizes)
    # favicon 供前端使用
    pub = ROOT / "frontend" / "public"
    pub.mkdir(exist_ok=True)
    final.save(pub / "favicon.ico", sizes=sizes)
    final.save(pub / "favicon.png")
    print("icon generated:", out / "app.ico")


if __name__ == "__main__":
    main()
