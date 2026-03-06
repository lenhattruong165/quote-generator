"""
Quote Image Generator API v6
Chang'e Aspirant Bot — by vy-lucyfer

v6: Emoji support + 2 gạch ngang + portrait fix
"""

import io
import os
import re
import urllib.request
import json
from flask import Flask, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════

STYLE_LANDSCAPE = "landscape"
STYLE_PORTRAIT = "portrait"

# Landscape
LANDSCAPE_W = 1200
LANDSCAPE_H = 630
LANDSCAPE_AVATAR_MAX_W = int(LANDSCAPE_W * 0.60)
LANDSCAPE_TEXT_X = int(LANDSCAPE_W * 0.52)
LANDSCAPE_TEXT_W = LANDSCAPE_W - LANDSCAPE_TEXT_X - 40

# Portrait
PORTRAIT_W = 800
PORTRAIT_AVATAR_RATIO = 0.65  # Avatar chiếm 65% chiều cao
PORTRAIT_FADE_START = 0.60    # Fade bắt đầu từ 60%

# Font
FONT_MAX = 68
FONT_MIN = 20
FONT_STEP = 2
LINE_HEIGHT_RATIO = 1.45

# Colors
COLOR_BG = (0, 0, 0, 255)
COLOR_TEXT = (255, 255, 255, 255)
COLOR_NAME = (230, 230, 230, 255)
COLOR_USERNAME = (140, 140, 140, 255)
COLOR_LINE = (100, 100, 100, 255)  # Màu gạch ngang

# Font URLs
FONT_URLS = {
    "regular": "https://github.com/miq4d/fonts/raw/main/GeistSans/Geist-Regular.ttf",
    "medium": "https://github.com/miq4d/fonts/raw/main/GeistSans/Geist-Medium.ttf",
    "emoji": "https://github.com/googlefonts/noto-emoji/raw/main/fonts/NotoColorEmoji.ttf",
}

_font_cache = {}
_emoji_cache = {}  # Cache emoji images

def get_font(style="regular", size=32):
    """Lấy font từ cache hoặc download"""
    key = f"{style}_{size}"
    if key in _font_cache:
        return _font_cache[key]

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

def fetch_emoji(emoji_id: str, animated: bool = False):
    """Tải Discord emoji ảnh"""
    if emoji_id in _emoji_cache:
        return _emoji_cache[emoji_id]

    ext = "gif" if animated else "png"
    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChangE-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data))
        if animated:
            img = img.convert("RGBA")
        _emoji_cache[emoji_id] = img
        return img
    except Exception as e:
        print(f"[emoji] Failed to fetch {emoji_id}: {e}")
        return None

def parse_emojis(text: str):
    """Parse text thành list (type, content) 
    type: 'text' | 'emoji'
    """
    # Pattern: <:name:id> hoặc <a:name:id>
    pattern = r'<(a?):(\w+):(\d+)>'
    result = []
    last_end = 0

    for match in re.finditer(pattern, text):
        start, end = match.span()

        # Text trước emoji
        if start > last_end:
            result.append(("text", text[last_end:start]))

        # Emoji
        animated = match.group(1) == "a"
        emoji_id = match.group(3)
        result.append(("emoji", emoji_id, animated))

        last_end = end

    # Text còn lại
    if last_end < len(text):
        result.append(("text", text[last_end:]))

    return result if result else [("text", text)]

def make_horizontal_fade(width: int, height: int, fade_start: float = 0.65):
    """Mask fade ngang cho landscape"""
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    fade_px = int(width * fade_start)
    fade_len = max(1, width - fade_px)

    for x in range(fade_px, width):
        p = (x - fade_px) / fade_len
        alpha = int(255 * max(0.0, (1.0 - p) ** 1.5))
        draw.line([(x, 0), (x, height)], fill=alpha)

    return mask

def make_vertical_fade(width: int, height: int, fade_start: float = 0.60):
    """Mask fade dọc cho portrait - gradient mượt"""
    mask = Image.new("L", (width, height), 255)
    pixels = mask.load()
    fade_px = int(height * fade_start)
    fade_len = max(1, height - fade_px)

    for y in range(height):
        if y < fade_px:
            alpha = 255
        else:
            p = (y - fade_px) / fade_len
            # Curve mượt hơn
            alpha = int(255 * (1.0 - p) ** 1.2)
        for x in range(width):
            pixels[x, y] = alpha

    return mask

def calculate_text_width(parsed_text, font, emoji_size, draw):
    """Tính chiều rộng text có emoji"""
    total_w = 0
    for item in parsed_text:
        if item[0] == "text":
            bbox = draw.textbbox((0, 0), item[1], font=font)
            total_w += bbox[2] - bbox[0]
        elif item[0] == "emoji":
            total_w += emoji_size
    return total_w

def wrap_text_with_emoji(text: str, font, max_w: int, emoji_size: int, draw: ImageDraw.ImageDraw):
    """Wrap text có emoji"""
    parsed = parse_emojis(text)
    lines = []
    current_line = []
    current_w = 0

    for item in parsed:
        if item[0] == "text":
            words = item[1].split(" ")
            for word in words:
                word_bbox = draw.textbbox((0, 0), word + " ", font=font)
                word_w = word_bbox[2] - word_bbox[0]

                if current_w + word_w > max_w and current_line:
                    lines.append(current_line)
                    current_line = [("text", word + " ")]
                    current_w = word_w
                else:
                    current_line.append(("text", word + " "))
                    current_w += word_w

        elif item[0] == "emoji":
            if current_w + emoji_size > max_w and current_line:
                lines.append(current_line)
                current_line = [item]
                current_w = emoji_size
            else:
                current_line.append(item)
                current_w += emoji_size

    if current_line:
        lines.append(current_line)

    return lines

def fit_text_portrait(text: str, max_w: int, draw: ImageDraw.ImageDraw):
    """Tìm font size phù hợp cho portrait"""
    for size in range(FONT_MAX, FONT_MIN - 1, -FONT_STEP):
        font = get_font("regular", size)
        emoji_size = int(size * 1.1)
        lines = wrap_text_with_emoji(text, font, max_w - 40, emoji_size, draw)
        line_h = int(size * LINE_HEIGHT_RATIO)

        # Tính chiều cao
        name_size = max(FONT_MIN, int(size * 0.55))
        user_size = max(14, int(size * 0.42))
        name_font = get_font("medium", name_size)
        user_font = get_font("regular", user_size)

        name_h = line_h
        user_h = int(user_size * 1.3)
        gap = int(size * 0.5)
        line_gap = int(size * 0.8)  # Gap giữa 2 gạch ngang

        # Tổng chiều cao = text + gạch1 + gap + gạch2 + tên + username + padding
        text_h = len(lines) * line_h
        total_h = text_h + (gap * 3) + line_gap + name_h + user_h + 40

        return {
            "font": font,
            "lines": lines,
            "line_h": line_h,
            "size": size,
            "emoji_size": emoji_size,
            "name_font": name_font,
            "user_font": user_font,
            "name_h": name_h,
            "user_h": user_h,
            "gap": gap,
            "line_gap": line_gap,
            "total_h": total_h
        }

    # Fallback
    font = get_font("regular", FONT_MIN)
    emoji_size = int(FONT_MIN * 1.1)
    lines = wrap_text_with_emoji(text, font, max_w - 40, emoji_size, draw)
    return {
        "font": font,
        "lines": lines,
        "line_h": int(FONT_MIN * LINE_HEIGHT_RATIO),
        "size": FONT_MIN,
        "emoji_size": emoji_size,
        "name_font": get_font("medium", FONT_MIN),
        "user_font": get_font("regular", 14),
        "name_h": FONT_MIN,
        "user_h": 18,
        "gap": 10,
        "line_gap": 15,
        "total_h": len(lines) * int(FONT_MIN * LINE_HEIGHT_RATIO) + 100
    }

def render_text_line(draw, line, x, y, font, emoji_size, color):
    """Render 1 dòng text có emoji"""
    curr_x = x
    for item in line:
        if item[0] == "text":
            draw.text((curr_x, y), item[1], font=font, fill=color)
            bbox = draw.textbbox((curr_x, y), item[1], font=font)
            curr_x += bbox[2] - bbox[0]
        elif item[0] == "emoji":
            emoji_img = fetch_emoji(item[1], item[2])
            if emoji_img:
                # Resize emoji
                es = emoji_size
                emoji_resized = emoji_img.resize((es, es), Image.LANCZOS)
                # Paste vào canvas
                draw._image.paste(emoji_resized, (int(curr_x), int(y)), emoji_resized)
                curr_x += es
            else:
                # Fallback: bỏ qua nếu không tải được
                curr_x += emoji_size

def render_portrait(text: str, display_name: str, username: str, avatar_url: str):
    """Render style portrait với 2 gạch ngang và emoji"""
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    # Tính toán text
    text_info = fit_text_portrait(text, PORTRAIT_W - 80, dummy)

    # Chiều cao các phần
    avatar_h = int(PORTRAIT_W * 1.2)  # Avatar cao hơn width một chút
    text_area_h = text_info["total_h"]
    canvas_h = avatar_h + text_area_h

    canvas = Image.new("RGBA", (PORTRAIT_W, canvas_h), COLOR_BG)

    # Avatar
    av = fetch_avatar(avatar_url)
    if av:
        aw, ah = av.size
        # Scale để fit width
        scale = PORTRAIT_W / aw
        new_ah = int(ah * scale)
        av = av.resize((PORTRAIT_W, new_ah), Image.LANCZOS)

        # Crop hoặc pad
        if new_ah >= avatar_h:
            av_crop = av.crop((0, 0, PORTRAIT_W, avatar_h))
        else:
            av_crop = Image.new("RGBA", (PORTRAIT_W, avatar_h), COLOR_BG)
            av_crop.paste(av, (0, 0))

        # Fade dọc mượt
        mask = make_vertical_fade(PORTRAIT_W, avatar_h, PORTRAIT_FADE_START)
        av_crop.putalpha(mask)
        canvas.paste(av_crop, (0, 0), av_crop)

    # Text area - solid black background
    draw = ImageDraw.Draw(canvas)
    text_start_y = avatar_h + 20

    # Vẽ background đen solid cho text area (tùy chọn, làm nổi text)
    # draw.rectangle([0, avatar_h, PORTRAIT_W, canvas_h], fill=(0, 0, 0, 255))

    y = text_start_y

    # Gạch ngang 1 (trên quote)
    line_width = int(PORTRAIT_W * 0.6)
    line_x = (PORTRAIT_W - line_width) // 2
    draw.line([(line_x, y), (line_x + line_width, y)], fill=COLOR_LINE, width=2)
    y += text_info["gap"]

    # Quote text (căn giữa)
    for line in text_info["lines"]:
        line_w = 0
        for item in line:
            if item[0] == "text":
                bbox = dummy.textbbox((0, 0), item[1], font=text_info["font"])
                line_w += bbox[2] - bbox[0]
            else:
                line_w += text_info["emoji_size"]

        x = (PORTRAIT_W - line_w) // 2
        render_text_line(draw, line, x, y, text_info["font"], 
                        text_info["emoji_size"], COLOR_TEXT)
        y += text_info["line_h"]

    # Gạch ngang 2 (dưới quote)
    y += text_info["gap"]
    draw.line([(line_x, y), (line_x + line_width, y)], fill=COLOR_LINE, width=2)
    y += text_info["line_gap"]

    # Tên
    name_text = f"— {display_name}"
    bbox = dummy.textbbox((0, 0), name_text, font=text_info["name_font"])
    name_w = bbox[2] - bbox[0]
    x = (PORTRAIT_W - name_w) // 2
    draw.text((x, y), name_text, font=text_info["name_font"], fill=COLOR_NAME)
    y += text_info["name_h"] + 5

    # Username
    user_text = f"@{username}"
    bbox = dummy.textbbox((0, 0), user_text, font=text_info["user_font"])
    user_w = bbox[2] - bbox[0]
    x = (PORTRAIT_W - user_w) // 2
    draw.text((x, y), user_text, font=text_info["user_font"], fill=COLOR_USERNAME)

    return canvas.convert("RGB")

def render_landscape(text: str, display_name: str, username: str, avatar_url: str):
    """Render style landscape (giữ nguyên v4)"""
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

        mask = make_horizontal_fade(paste_w, LANDSCAPE_H, 0.65)
        av_crop.putalpha(mask)
        canvas.paste(av_crop, (0, 0), av_crop)

    # Text
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font = get_font("regular", 48)
    name_font = get_font("medium", 28)
    user_font = get_font("regular", 22)

    # Simple wrap
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip() if current else word
        bbox = dummy.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= LANDSCAPE_TEXT_W - 30:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_h = int(48 * 1.4)
    total_text_h = len(lines) * line_h + 60 + 28 + 22
    start_y = (LANDSCAPE_H - total_text_h) // 2

    draw = ImageDraw.Draw(canvas)
    y = start_y

    for line in lines:
        bbox = dummy.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - lw) // 2
        draw.text((x, y), line, font=font, fill=COLOR_TEXT)
        y += line_h

    y += 30
    name_text = f"— {display_name}"
    bbox = dummy.textbbox((0, 0), name_text, font=name_font)
    name_w = bbox[2] - bbox[0]
    x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - name_w) // 2
    draw.text((x, y), name_text, font=name_font, fill=COLOR_NAME)
    y += 35

    user_text = f"@{username}"
    bbox = dummy.textbbox((0, 0), user_text, font=user_font)
    user_w = bbox[2] - bbox[0]
    x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - user_w) // 2
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
    return "Quote Generator API v6 is Running!", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "6", "styles": ["landscape", "portrait"], "features": ["emoji", "2-lines"]})

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