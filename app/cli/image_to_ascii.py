"""图片转 Braille dot art —— 终端高密度 ASCII 渲染。

使用 braille 字符集（每个字符表示 2x4 像素块），
在终端中以 2x 水平密度渲染灰度图，比普通 ASCII art 精细得多。
"""

from pathlib import Path


# 20 级灰度 braille 字符（从最暗到最亮）
BRAILLE_RAMP = [
    "⣿", "⣾", "⣽", "⣻", "⣺", "⣸", "⣷", "⣧",
    "⡇", "⠿", "⠾", "⠽", "⠼", "⠻", "⠺", "⠸",
    "⠷", "⠧", "⠇", " ",
]


def image_to_braille(image_path: str, width: int = 40) -> str:
    """将图片转换为 braille dot art 字符串。

    Args:
        image_path: 图片文件路径。
        width: 输出宽度（字符数，默认 40）。

    Returns:
        braille art 字符串，每行以换行符分隔。

    Raises:
        ImportError: Pillow 未安装。
        FileNotFoundError: 图片路径不存在。
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(
            "图片转 ASCII 需要 Pillow 库。请运行: pip install pillow"
        )

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    img = Image.open(path).convert("L")  # 灰度

    # 每个 braille 字符覆盖 2 像素宽 x 4 像素高
    # 因此画布宽 = width * 2，高的缩放保持宽高比
    pixel_w = width * 2
    aspect = img.height / img.width
    pixel_h = int(pixel_w * aspect * 0.5)  # braille 垂直密度 ≈ 0.5
    pixel_h = max(pixel_h, 4)

    img = img.resize((pixel_w, pixel_h), Image.LANCZOS)

    lines: list[str] = []
    pixels = list(img.getdata())

    for y in range(0, pixel_h - 3, 4):
        line_chars: list[str] = []
        for x in range(0, pixel_w - 1, 2):
            # 2x4 像素块 → braille 字符
            dots = 0
            pos = 0
            for dy in range(4):
                for dx in range(2):
                    py = y + dy
                    px = x + dx
                    idx = py * pixel_w + px
                    if idx < len(pixels) and pixels[idx] < 128:
                        dots |= 1 << pos
                    pos += 1
            line_chars.append(_dots_to_braille(dots))
        lines.append("".join(line_chars))

    return "\n".join(lines)


def image_to_ascii_simple(image_path: str, width: int = 40) -> str:
    """简单 ASCII art（纯文本字符，兼容性更好）。

    灰度映射到：@%#*+=-:. (10 级)
    降级方案，用于不支持 braille 字符的终端。
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("需要 Pillow 库。请运行: pip install pillow")

    ramp = "@%#*+=-:. "
    path = Path(image_path)
    img = Image.open(path).convert("L")

    aspect = img.height / img.width
    height = int(width * aspect * 0.5)
    height = max(height, 1)

    img = img.resize((width, height), Image.LANCZOS)

    lines = []
    pixels = list(img.getdata())
    for y in range(height):
        row = ""
        for x in range(width):
            gray = pixels[y * width + x]
            idx = int(gray / 256 * len(ramp))
            row += ramp[min(idx, len(ramp) - 1)]
        lines.append(row)

    return "\n".join(lines)


# ── Braille 点阵映射 ─────────────────────────────────────────

# Braille Unicode 编码从 U+2800 开始
# 点阵布局（标准 8-dot braille）：
#   1 4
#   2 5
#   3 6
#   7 8
#
# 我们只用 2x4 的 top-4 行（dots 1-8），映射到 8-bit bitmap

def _dots_to_braille(dots: int) -> str:
    """8-bit bitmap → braille Unicode 字符（U+2800 + offset）。"""
    # dots bit layout: 0=top-left, 1=middle-left, 2=bottom-left, 3=top-right, ...
    # Braille order: dot1(pos0), dot2(pos1), dot3(pos2), dot4(pos3), dot5(pos4), dot6(pos5), dot7(pos6), dot8(pos7)
    # 我们的扫描顺序:
    #   dx=0,dy=0 → dot1
    #   dx=0,dy=1 → dot2
    #   dx=0,dy=2 → dot3
    #   dx=1,dy=0 → dot4
    #   dx=1,dy=1 → dot5
    #   dx=1,dy=2 → dot6
    #   dx=0,dy=3 → dot7
    #   dx=1,dy=3 → dot8
    braille_order = [0, 3, 1, 4, 2, 5, 6, 7]
    value = 0
    for i, bi in enumerate(braille_order):
        if dots & (1 << i):
            value |= 1 << bi
    return chr(0x2800 + value)
