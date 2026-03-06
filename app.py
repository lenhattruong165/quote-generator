"""
Quote Image Generator API v5
Chang'e Aspirant Bot — by vy-lucyfer

v5: Thêm style portrait + landscape, font GeistSans, dynamic height
"""

import io
import os
import urllib.request
import json
from flask import Flask, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════

# Style configs
STYLE_LANDSCAPE = "landscape"
STYLE_PORTRAIT = "portrait"

# Landscape (hình 1 style)
LANDSCAPE_W = 1200
LANDSCAPE_H = 630
LANDSCAPE_AVATAR_MAX_W = int(LANDSCAPE_W * 0.60)
LANDSCAPE_TEXT_X = int(LANDSCAPE_W * 0.52)
LANDSCAPE_TEXT_W = LANDSCAPE_W - LANDSCAPE_TEXT_X - 40

# Portrait (hình 2 style)  
PORTRAIT_W = 800
PORTRAIT_MIN_H = 1000
PORTRAIT_AVATAR_H = int(PORTRAIT_MIN_H * 0.60)  # Avatar chiếm 60% chiều cao

# Font settings
FONT_MAX = 72
FONT_MIN = 18
FONT_STEP = 2
LINE_HEIGHT_RATIO = 1.4

# Colors
COLOR_BG = (0, 0, 0, 255)
COLOR_TEXT = (255, 255, 255, 255)
COLOR_NAME = (230, 230, 230, 255)
COLOR_USERNAME = (140, 140, 140, 255)

# Font URLs từ miq4d/fonts repo (GeistSans)
FONT_URLS = {
    "regular": "https://github.com/miq4d/fonts/raw/main/GeistSans/Geist-Regular.ttf",
    "medium": "https://github.com/miq4d/fonts/raw/main/GeistSans/Geist-Medium.ttf",
    "semibold": "https://github.com/miq4d/fonts/raw/main/GeistSans/Geist-SemiBold.ttf",
}

# Cache font
_font_cache = {}

def get_font(style="regular", size=32):
    """Lấy font từ cache hoặc download"""
    key = f"{style}_{size}"
    if key in _font_cache:
        return _font_cache[key]

    # Thử download font từ GitHub
    try:
        url = FONT_URLS.get(style, FONT_URLS["regular"])
        req = urllib.request.Request(url, headers={"User-Agent": "ChangE-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            font_data = resp.read()

        font = ImageFont.truetype(io.BytesIO(font_data), size)
        _font_cache[key] = font
        return font
    except Exception as e:
        print(f"[font] Failed to load {style} size {size}: {e}")
        # Fallback to default
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except:
            return ImageFont.load_default()

def fetch_avatar(url: str):
    """Tải avatar từ URL"""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChangE-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        print(f"[avatar] Error: {e}")
        return None

def make_horizontal_fade(width: int, height: int, fade_start: float = 0.65):
    """Mask fade ngang (cho landscape) - từ trái sang phải"""
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    fade_px = int(width * fade_start)
    fade_len = max(1, width - fade_px)

    for x in range(fade_px, width):
        p = (x - fade_px) / fade_len
        alpha = int(255 * max(0.0, (1.0 - p) ** 1.5))
        draw.line([(x, 0), (x, height)], fill=alpha)

    return mask

def make_vertical_fade(width: int, height: int, fade_start: float = 0.55):
    """Mask fade dọc (cho portrait) - từ trên xuống dưới"""
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    fade_px = int(height * fade_start)
    fade_len = max(1, height - fade_px)

    for y in range(fade_px, height):
        p = (y - fade_px) / fade_len
        alpha = int(255 * max(0.0, (1.0 - p) ** 2.0))
        draw.line([(0, y), (width, y)], fill=alpha)

    return mask

def smart_wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw):
    """Wrap text thông minh, cắt từ nếu quá dài"""
    words = text.split()
    if not words:
        return [text] if text else [""]

    lines = []
    current = ""

    for word in words:
        # Kiểm tra nếu từ đơn lẻ đã quá dài
        word_bbox = draw.textbbox((0, 0), word, font=font)
        word_w = word_bbox[2] - word_bbox[0]

        if word_w > max_w:
            # Cắt từ dài thành nhiều phần
            if current:
                lines.append(current)
                current = ""

            # Cắt từ dài
            part = ""
            for char in word:
                test_part = part + char
                test_bbox = draw.textbbox((0, 0), test_part, font=font)
                if test_bbox[2] - test_bbox[0] > max_w and part:
                    lines.append(part)
                    part = char
                else:
                    part = test_part
            if part:
                lines.append(part)
            continue

        # Thử thêm từ vào dòng hiện tại
        test = (current + " " + word).strip() if current else word
        test_bbox = draw.textbbox((0, 0), test, font=font)
        test_w = test_bbox[2] - test_bbox[0]

        if test_w <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines if lines else [text]

def calculate_text_height(lines, line_h, name_h, user_h, gap):
    """Tính tổng chiều cao text area"""
    return (len(lines) * line_h) + gap + name_h + (name_h // 3) + user_h

def fit_text_portrait(text: str, max_w: int, max_h: int, draw: ImageDraw.ImageDraw):
    """Tìm font size phù hợp cho portrait (text ở dưới)"""
    for size in range(FONT_MAX, FONT_MIN - 1, -FONT_STEP):
        font = get_font("regular", size)
        lines = smart_wrap(text, font, max_w, draw)
        line_h = int(size * LINE_HEIGHT_RATIO)

        # Tính chiều cao tên và username
        name_size = max(FONT_MIN, int(size * 0.55))
        user_size = max(14, int(size * 0.42))
        name_font = get_font("medium", name_size)
        user_font = get_font("regular", user_size)

        name_bbox = draw.textbbox((0, 0), "Ty", font=name_font)
        name_h = name_bbox[3] - name_bbox[1]
        user_bbox = draw.textbbox((0, 0), "Ty", font=user_font)
        user_h = user_bbox[3] - user_bbox[1]

        gap = int(size * 0.6)
        total_h = calculate_text_height(lines, line_h, name_h, user_h, gap)

        if total_h <= max_h:
            return font, lines, line_h, size, name_font, user_font, name_h, user_h, gap, total_h

    # Fallback nhỏ nhất
    font = get_font("regular", FONT_MIN)
    lines = smart_wrap(text, font, max_w, draw)
    line_h = int(FONT_MIN * LINE_HEIGHT_RATIO)
    name_font = get_font("medium", FONT_MIN)
    user_font = get_font("regular", 14)
    name_h = user_h = FONT_MIN
    gap = int(FONT_MIN * 0.6)
    total_h = calculate_text_height(lines, line_h, name_h, user_h, gap)

    return font, lines, line_h, FONT_MIN, name_font, user_font, name_h, user_h, gap, total_h

def fit_text_landscape(text: str, max_w: int, max_h: int, draw: ImageDraw.ImageDraw):
    """Tìm font size phù hợp cho landscape (text bên phải)"""
    for size in range(FONT_MAX, FONT_MIN - 1, -FONT_STEP):
        font = get_font("regular", size)
        lines = smart_wrap(text, font, max_w, draw)
        line_h = int(size * LINE_HEIGHT_RATIO)

        name_size = max(FONT_MIN, int(size * 0.58))
        user_size = max(14, int(size * 0.44))
        name_font = get_font("medium", name_size)
        user_font = get_font("regular", user_size)

        name_bbox = draw.textbbox((0, 0), "Ty", font=name_font)
        name_h = name_bbox[3] - name_bbox[1]
        user_bbox = draw.textbbox((0, 0), "Ty", font=user_font)
        user_h = user_bbox[3] - user_bbox[1]

        gap = int(size * 0.55)
        total_h = calculate_text_height(lines, line_h, name_h, user_h, gap)

        if total_h <= max_h:
            return font, lines, line_h, size, name_font, user_font, name_h, user_h, gap

    # Fallback
    font = get_font("regular", FONT_MIN)
    lines = smart_wrap(text, font, max_w, draw)
    line_h = int(FONT_MIN * LINE_HEIGHT_RATIO)
    name_font = get_font("medium", FONT_MIN)
    user_font = get_font("regular", 14)
    name_h = user_h = FONT_MIN
    gap = int(FONT_MIN * 0.55)

    return font, lines, line_h, FONT_MIN, name_font, user_font, name_h, user_h, gap

def render_landscape(text: str, display_name: str, username: str, avatar_url: str):
    """Render style landscape (hình 1)"""
    canvas = Image.new("RGBA", (LANDSCAPE_W, LANDSCAPE_H), COLOR_BG)

    # Avatar
    av = fetch_avatar(avatar_url)
    if av:
        aw, ah = av.size
        scale = LANDSCAPE_H / ah
        new_aw = int(aw * scale)
        av = av.resize((new_aw, LANDSCAPE_H), Image.LANCZOS)

        paste_w = min(new_aw, LANDSCAPE_AVATAR_MAX_W)
        av_crop = av.crop((0, 0, paste_w, LANDSCAPE_H)).convert("RGBA")

        # Fade ngang
        mask = make_horizontal_fade(paste_w, LANDSCAPE_H, 0.65)
        av_crop.putalpha(mask)
        canvas.paste(av_crop, (0, 0), av_crop)

    # Text area
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_max_h = int(LANDSCAPE_H * 0.75)

    font, lines, line_h, fs, name_font, user_font, name_h, user_h, gap = fit_text_landscape(
        text, LANDSCAPE_TEXT_W - 30, text_max_h, dummy
    )

    # Tính toán vị trí căn giữa
    total_text_h = calculate_text_height(lines, line_h, name_h, user_h, gap)
    start_y = (LANDSCAPE_H - total_text_h) // 2

    draw = ImageDraw.Draw(canvas)
    y = start_y

    # Vẽ quote text
    for line in lines:
        bbox = dummy.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - lw) // 2
        draw.text((x, y), line, font=font, fill=COLOR_TEXT)
        y += line_h

    # Vẽ tên
    y += gap
    name_text = f"— {display_name}"
    bbox = dummy.textbbox((0, 0), name_text, font=name_font)
    name_w = bbox[2] - bbox[0]
    x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - name_w) // 2
    draw.text((x, y), name_text, font=name_font, fill=COLOR_NAME)
    y += name_h + (name_h // 3)

    # Vẽ username
    user_text = f"@{username}"
    bbox = dummy.textbbox((0, 0), user_text, font=user_font)
    user_w = bbox[2] - bbox[0]
    x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - user_w) // 2
    draw.text((x, y), user_text, font=user_font, fill=COLOR_USERNAME)

    return canvas.convert("RGB")

def render_portrait(text: str, display_name: str, username: str, avatar_url: str):
    """Render style portrait (hình 2) - dọc, avatar trên, text dưới"""
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    # Tính toán text trước để biết cần bao nhiêu chiều cao
    text_max_w = PORTRAIT_W - 80  # Padding 40 mỗi bên
    text_max_h = 400  # Dự trữ cho text

    font, lines, line_h, fs, name_font, user_font, name_h, user_h, gap, text_h = fit_text_portrait(
        text, text_max_w, text_max_h, dummy
    )

    # Tính chiều cao canvas cuối cùng
    text_area_h = text_h + 60  # Padding
    canvas_h = max(PORTRAIT_MIN_H, PORTRAIT_AVATAR_H + text_area_h)

    canvas = Image.new("RGBA", (PORTRAIT_W, canvas_h), COLOR_BG)

    # Avatar - full width, fit height
    av = fetch_avatar(avatar_url)
    if av:
        aw, ah = av.size
        # Scale để fit width
        scale = PORTRAIT_W / aw
        new_ah = int(ah * scale)
        av = av.resize((PORTRAIT_W, new_ah), Image.LANCZOS)

        # Crop hoặc pad để có chiều cao mong muốn
        if new_ah >= PORTRAIT_AVATAR_H:
            # Crop từ top
            av_crop = av.crop((0, 0, PORTRAIT_W, PORTRAIT_AVATAR_H))
        else:
            # Pad thêm đen ở dưới
            av_crop = Image.new("RGBA", (PORTRAIT_W, PORTRAIT_AVATAR_H), COLOR_BG)
            av_crop.paste(av, (0, 0))

        av_crop = av_crop.convert("RGBA")

        # Fade dọc từ 55% xuống
        mask = make_vertical_fade(PORTRAIT_W, PORTRAIT_AVATAR_H, 0.55)
        av_crop.putalpha(mask)
        canvas.paste(av_crop, (0, 0), av_crop)

    # Text area - ở dưới cùng
    draw = ImageDraw.Draw(canvas)

    # Vùng text bắt đầu từ dưới lên
    text_start_y = canvas_h - text_area_h + 30
    y = text_start_y

    # Căn giữa text
    for line in lines:
        bbox = dummy.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (PORTRAIT_W - lw) // 2
        draw.text((x, y), line, font=font, fill=COLOR_TEXT)
        y += line_h

    # Tên
    y += gap
    name_text = f"— {display_name}"
    bbox = dummy.textbbox((0, 0), name_text, font=name_font)
    name_w = bbox[2] - bbox[0]
    x = (PORTRAIT_W - name_w) // 2
    draw.text((x, y), name_text, font=name_font, fill=COLOR_NAME)
    y += name_h + (name_h // 3)

    # Username
    user_text = f"@{username}"
    bbox = dummy.textbbox((0, 0), user_text, font=user_font)
    user_w = bbox[2] - bbox[0]
    x = (PORTRAIT_W - user_w) // 2
    draw.text((x, y), user_text, font=user_font, fill=COLOR_USERNAME)

    return canvas.convert("RGB")

def render_quote(text: str, display_name: str, username: str, avatar_url: str, style: str = "landscape"):
    """Render quote theo style"""
    if style == STYLE_PORTRAIT:
        img = render_portrait(text, display_name, username, avatar_url)
    else:
        img = render_landscape(text, display_name, username, avatar_url)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()

# ═════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/", methods=["GET"])
def index():
    return "Quote Generator API v5 is Running!", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "5", "styles": ["landscape", "portrait"]})

@app.route("/quote", methods=["POST"])
def quote():
    try:
        data = request.get_json(force=True, silent=True) or {}
        text = (data.get("text") or "").strip()
        display_name = (data.get("display_name") or data.get("username") or "Unknown").strip()
        username = (data.get("username") or "unknown").strip()
        avatar_url = (data.get("avatar") or "").strip()
        style = (data.get("style") or "landscape").strip().lower()

        if not text:
            return jsonify({"error": "text is required"}), 400
        if len(text) > 500:
            return jsonify({"error": "text too long (max 500 chars)"}), 400
        if style not in [STYLE_LANDSCAPE, STYLE_PORTRAIT]:
            style = STYLE_LANDSCAPE

        png_bytes = render_quote(text, display_name, username, avatar_url, style)
        return send_file(
            io.BytesIO(png_bytes),
            mimetype="image/png",
            as_attachment=False,
            download_name=f"quote_{style}.png"
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)), debug=False)