"""Quote Image Generator API v9 - Chang'e Aspirant Bot"""
import io
import os
import re
import urllib.request
from flask import Flask, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

STYLE_LANDSCAPE = "landscape"
STYLE_PORTRAIT = "portrait"

# Landscape config
LANDSCAPE_W = 1200
LANDSCAPE_H = 630
LANDSCAPE_AVATAR_MAX_W = int(LANDSCAPE_W * 0.55)
LANDSCAPE_TEXT_X = int(LANDSCAPE_W * 0.50)
LANDSCAPE_TEXT_W = LANDSCAPE_W - LANDSCAPE_TEXT_X - 60

# Portrait config
PORTRAIT_W = 800
PORTRAIT_TEXT_PAD = 60

# Font config
FONT_MAX = 64
FONT_MIN = 18
FONT_STEP = 2
LINE_HEIGHT_RATIO = 1.5

# Colors
COLOR_BG = (0, 0, 0, 255)
COLOR_TEXT = (255, 255, 255, 255)
COLOR_NAME = (230, 230, 230, 255)
COLOR_USERNAME = (140, 140, 140, 255)
COLOR_LINE = (100, 100, 100, 255)
COLOR_SERVER = (120, 120, 120, 255)

# Font path — upload MPLUSRounded1c-Light.ttf vào HF Space Files tab tại fonts/MPLUSRounded1c-Light.ttf
FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "MPLUSRounded1c-Light.ttf")
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

_font_cache = {}
_emoji_cache = {}

def get_font(style="regular", size=32):
    key = f"{style}_{size}"
    if key in _font_cache:
        return _font_cache[key]
    try:
        font = ImageFont.truetype(FONT_PATH, size)
        _font_cache[key] = font
        return font
    except Exception as e:
        print(f"[font] Failed local {size}: {e}")
        try:
            font = ImageFont.truetype(FONT_FALLBACK, size)
            _font_cache[key] = font
            return font
        except:
            return ImageFont.load_default()

def fetch_avatar(url: str):
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
    cache_key = f"{emoji_id}_{animated}"
    if cache_key in _emoji_cache:
        return _emoji_cache[cache_key]
    ext = "gif" if animated else "png"
    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=64"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChangE-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        _emoji_cache[cache_key] = img
        return img
    except Exception as e:
        print(f"[emoji] Failed {emoji_id}: {e}")
        return None

def parse_text_with_emoji(text: str):
    pattern = r'<(a?):([^:]+):(\d+)>'
    segments = []
    last_end = 0
    for match in re.finditer(pattern, text):
        start, end = match.span()
        if start > last_end:
            segments.append(("text", text[last_end:start]))
        animated = match.group(1) == "a"
        emoji_id = match.group(3)
        segments.append(("emoji", emoji_id, animated))
        last_end = end
    if last_end < len(text):
        segments.append(("text", text[last_end:]))
    return segments if segments else [("text", text)]

def get_segment_width(seg, font, emoji_size, draw):
    if seg[0] == "text":
        bbox = draw.textbbox((0, 0), seg[1], font=font)
        return bbox[2] - bbox[0]
    else:
        return emoji_size

def wrap_segments(segments, font, max_w, emoji_size, draw):
    """
    Wrap segments into lines respecting max_w.
    Text segments split on word (space) boundaries first to avoid cutting
    in the middle of Vietnamese words (e.g. 'tình' → 'tì'+'nh').
    Falls back to character-level cut only when a single word > max_w.
    """
    import unicodedata

    # Expand all text segments into word-level tokens
    tokens = []
    for seg in segments:
        if seg[0] != "text":
            tokens.append(seg)
            continue
        words = seg[1].split(" ")
        for i, word in enumerate(words):
            if not word:
                continue
            # Prepend space between words (except very first token overall)
            text = (" " + word) if tokens else word
            tokens.append(("text", text))

    lines = []
    current_line = []
    current_w = 0

    for tok in tokens:
        tok_text = unicodedata.normalize("NFC", tok[1]) if tok[0] == "text" else tok[1]
        tok = (tok[0], tok_text) if tok[0] == "text" else tok
        tok_w = get_segment_width(tok, font, emoji_size, draw)

        # Single word wider than max_w → character-level hard cut
        if tok[0] == "text" and tok_w > max_w:
            if current_line:
                lines.append(current_line)
                current_line = []
                current_w = 0
            text = tok[1].lstrip(" ")
            while text:
                remaining = max_w
                cut = 0
                for i in range(1, len(text) + 1):
                    w = get_segment_width(("text", text[:i]), font, emoji_size, draw)
                    if w > remaining:
                        cut = i - 1
                        break
                    cut = i
                if cut == 0:
                    cut = 1
                current_line.append(("text", text[:cut]))
                current_w = get_segment_width(("text", text[:cut]), font, emoji_size, draw)
                text = text[cut:]
                if text:
                    lines.append(current_line)
                    current_line = []
                    current_w = 0
            continue

        # Normal word: check if it fits on current line
        if current_w + tok_w > max_w and current_line:
            lines.append(current_line)
            # Strip leading space when starting new line
            stripped = tok[1].lstrip(" ")
            tok = ("text", stripped)
            tok_w = get_segment_width(tok, font, emoji_size, draw)
            current_line = [tok]
            current_w = tok_w
        else:
            current_line.append(tok)
            current_w += tok_w

    if current_line:
        lines.append(current_line)
    return lines

def make_horizontal_fade(width: int, height: int, fade_start: float = 0.60):
    mask = Image.new("L", (width, height), 255)
    pixels = mask.load()
    fade_px = int(width * fade_start)
    fade_len = max(1, width - fade_px)
    for x in range(width):
        if x < fade_px:
            alpha = 255
        else:
            p = (x - fade_px) / fade_len
            alpha = int(255 * (1.0 - p) ** 1.5)
        for y in range(height):
            pixels[x, y] = alpha
    return mask

def make_vertical_fade_light(width: int, height: int):
    """
    Fade dọc: sáng từ trên → bắt đầu fade ở 60% height → đen hoàn toàn.
    curve 2.0 = fade nhanh và rõ ràng.
    """
    mask = Image.new("L", (width, height), 255)
    pixels = mask.load()
    fade_start = int(height * 0.60)
    fade_end = height
    fade_len = max(1, fade_end - fade_start)
    for y in range(height):
        if y < fade_start:
            alpha = 255
        else:
            p = (y - fade_start) / fade_len
            alpha = int(255 * max(0.0, (1.0 - p) ** 2.0))
        for x in range(width):
            pixels[x, y] = alpha
    return mask

def render_line(canvas, line, x, y, font, emoji_size, color):
    draw = ImageDraw.Draw(canvas)
    curr_x = x
    for seg in line:
        if seg[0] == "text":
            draw.text((curr_x, y), seg[1], font=font, fill=color)
            bbox = draw.textbbox((curr_x, y), seg[1], font=font)
            curr_x += bbox[2] - bbox[0]
        elif seg[0] == "emoji":
            emoji_img = fetch_emoji(seg[1], seg[2])
            if emoji_img:
                es = min(emoji_size, 64)
                emoji_resized = emoji_img.resize((es, es), Image.LANCZOS)
                y_offset = (font.size - es) // 2
                canvas.paste(emoji_resized, (int(curr_x), int(y + y_offset)), emoji_resized)
                curr_x += es + 2
            else:
                curr_x += emoji_size

def get_line_width(line, font, emoji_size, draw):
    total = 0
    for seg in line:
        total += get_segment_width(seg, font, emoji_size, draw)
    return total

def fit_text(segments, max_w, max_h, draw, is_portrait=False, has_server=False):
    for size in range(FONT_MAX, FONT_MIN - 1, -FONT_STEP):
        font = get_font("regular", size)
        emoji_size = int(size * 1.2)
        line_h = int(size * LINE_HEIGHT_RATIO)
        lines = wrap_segments(segments, font, max_w - 20, emoji_size, draw)
        total_h = len(lines) * line_h
        name_size = max(FONT_MIN, int(size * 0.55))
        user_size = max(14, int(size * 0.42))
        server_size = max(12, int(size * 0.38))
        name_h = int(name_size * 1.3)
        user_h = int(user_size * 1.3)
        server_h = int(server_size * 1.3)
        if is_portrait:
            extra_h = name_h + user_h + 100
            if has_server:
                extra_h += server_h + 10
            total_h += extra_h
        else:
            total_h += (name_h + user_h + 50)
        if total_h <= max_h or size == FONT_MIN:
            return {
                "font": font,
                "emoji_size": emoji_size,
                "line_h": line_h,
                "lines": lines,
                "size": size,
                "name_font": get_font("medium", name_size),
                "user_font": get_font("regular", user_size),
                "server_font": get_font("regular", server_size),
                "name_h": name_h,
                "user_h": user_h,
                "server_h": server_h,
            }
    return None

def render_landscape(text: str, display_name: str, username: str, avatar_url: str, server_name: str = None):
    canvas = Image.new("RGBA", (LANDSCAPE_W, LANDSCAPE_H), COLOR_BG)
    av = fetch_avatar(avatar_url)
    if av:
        aw, ah = av.size
        scale = LANDSCAPE_H / ah
        new_aw = int(aw * scale)
        av = av.resize((new_aw, LANDSCAPE_H), Image.LANCZOS)
        paste_w = min(new_aw, LANDSCAPE_AVATAR_MAX_W)
        av_crop = av.crop((0, 0, paste_w, LANDSCAPE_H)).convert("RGBA")
        mask = make_horizontal_fade(paste_w, LANDSCAPE_H, 0.60)
        av_crop.putalpha(mask)
        canvas.paste(av_crop, (0, 0), av_crop)
    segments = parse_text_with_emoji(text)
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_info = fit_text(segments, LANDSCAPE_TEXT_W, int(LANDSCAPE_H * 0.7), dummy, False, False)
    if not text_info:
        text_info = {
            "font": get_font("regular", FONT_MIN),
            "emoji_size": 24,
            "line_h": 30,
            "lines": wrap_segments(segments, get_font("regular", FONT_MIN), LANDSCAPE_TEXT_W - 20, 24, dummy),
            "name_font": get_font("medium", FONT_MIN),
            "user_font": get_font("regular", 14),
            "server_font": get_font("regular", 12),
            "name_h": 20,
            "user_h": 16,
            "server_h": 14
        }
    total_content_h = (len(text_info["lines"]) * text_info["line_h"]) + 40 + text_info["name_h"] + text_info["user_h"]
    start_y = (LANDSCAPE_H - total_content_h) // 2
    y = start_y
    for line in text_info["lines"]:
        line_w = get_line_width(line, text_info["font"], text_info["emoji_size"], dummy)
        x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - line_w) // 2
        render_line(canvas, line, x, y, text_info["font"], text_info["emoji_size"], COLOR_TEXT)
        y += text_info["line_h"]
    else:
        y += 25
        draw = ImageDraw.Draw(canvas)
    name_text = f"— {display_name}"
    bbox = dummy.textbbox((0, 0), name_text, font=text_info["name_font"])
    name_w = bbox[2] - bbox[0]
    x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - name_w) // 2
    draw.text((x, y), name_text, font=text_info["name_font"], fill=COLOR_NAME)
    y += text_info["name_h"] + 8
    user_text = f"@{username}"
    bbox = dummy.textbbox((0, 0), user_text, font=text_info["user_font"])
    user_w = bbox[2] - bbox[0]
    x = LANDSCAPE_TEXT_X + (LANDSCAPE_TEXT_W - user_w) // 2
    draw.text((x, y), user_text, font=text_info["user_font"], fill=COLOR_USERNAME)
    return canvas.convert("RGB")

def render_portrait(text: str, display_name: str, username: str, avatar_url: str, server_name: str = None):
    segments = parse_text_with_emoji(text)
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_w = PORTRAIT_W - (PORTRAIT_TEXT_PAD * 2)
    # has_server=False vì server_name giờ nằm trên avatar, không tính vào text area
    text_info = fit_text(segments, text_w, 500, dummy, True, False)
    if not text_info:
        text_info = {
            "font": get_font("regular", FONT_MIN),
            "emoji_size": 24,
            "line_h": 30,
            "lines": wrap_segments(segments, get_font("regular", FONT_MIN), text_w - 20, 24, dummy),
            "name_font": get_font("medium", FONT_MIN),
            "user_font": get_font("regular", 14),
            "server_font": get_font("regular", 12),
            "name_h": 20,
            "user_h": 16,
            "server_h": 14
        }
    quote_h = len(text_info["lines"]) * text_info["line_h"]
    text_area_h = quote_h + text_info["name_h"] + text_info["user_h"] + 100
    avatar_h = int(PORTRAIT_W * 1.2)
    canvas_h = avatar_h + text_area_h
    canvas = Image.new("RGBA", (PORTRAIT_W, canvas_h), COLOR_BG)

    av = fetch_avatar(avatar_url)
    if av:
        aw, ah = av.size
        scale = PORTRAIT_W / aw
        new_ah = int(ah * scale)
        av = av.resize((PORTRAIT_W, new_ah), Image.LANCZOS)
        if new_ah >= avatar_h:
            av_crop = av.crop((0, 0, PORTRAIT_W, avatar_h))
        else:
            av_crop = Image.new("RGBA", (PORTRAIT_W, avatar_h), COLOR_BG)
            av_crop.paste(av, (0, 0))

        # ── server_name: vẽ lên av_crop TRƯỚC fade, sát trái, ngay trên điểm fade bắt đầu ──
        if server_name:
            fade_start_y = int(avatar_h * 0.60)
            server_font  = text_info["server_font"]
            server_text  = f"@{server_name}"
            sb     = dummy.textbbox((0, 0), server_text, font=server_font)
            s_h    = sb[3] - sb[1]
            # Y: ngay trên điểm fade bắt đầu, lùi lên 1 dòng + padding nhỏ
            s_y    = fade_start_y - s_h - 10
            s_x    = PORTRAIT_TEXT_PAD  # sát trái
            av_draw = ImageDraw.Draw(av_crop)
            av_draw.text((s_x, s_y), server_text, font=server_font, fill=COLOR_SERVER)

        # Áp fade mask SAU khi đã vẽ server_name
        mask = make_vertical_fade_light(PORTRAIT_W, avatar_h)
        av_crop.putalpha(mask)
        canvas.paste(av_crop, (0, 0), av_crop)

    draw = ImageDraw.Draw(canvas)
    y = avatar_h + 20

    # Line kẻ ngang trên
    line_w = int(PORTRAIT_W * 0.5)
    line_x = (PORTRAIT_W - line_w) // 2
    draw.line([(line_x, y), (line_x + line_w, y)], fill=COLOR_LINE, width=2)
    y += 25

    # Quote text (không còn server_name ở đây)
    for line in text_info["lines"]:
        line_w_actual = get_line_width(line, text_info["font"], text_info["emoji_size"], dummy)
        x = (PORTRAIT_W - line_w_actual) // 2
        render_line(canvas, line, x, y, text_info["font"], text_info["emoji_size"], COLOR_TEXT)
        y += text_info["line_h"]

    y += 15
    # Line kẻ ngang dưới
    draw.line([(line_x, y), (line_x + line_w, y)], fill=COLOR_LINE, width=2)
    y += 25

    # DisplayName
    name_text = f"— {display_name}"
    bbox = dummy.textbbox((0, 0), name_text, font=text_info["name_font"])
    name_w = bbox[2] - bbox[0]
    x = (PORTRAIT_W - name_w) // 2
    draw.text((x, y), name_text, font=text_info["name_font"], fill=COLOR_NAME)
    y += text_info["name_h"] + 5

    # @username
    user_text = f"@{username}"
    bbox = dummy.textbbox((0, 0), user_text, font=text_info["user_font"])
    user_w = bbox[2] - bbox[0]
    x = (PORTRAIT_W - user_w) // 2
    draw.text((x, y), user_text, font=text_info["user_font"], fill=COLOR_USERNAME)
    return canvas.convert("RGB")

def render_quote(text: str, display_name: str, username: str, avatar_url: str, style: str = "landscape", server_name: str = None):
    if style == STYLE_PORTRAIT:
        img = render_portrait(text, display_name, username, avatar_url, server_name)
    else:
        img = render_landscape(text, display_name, username, avatar_url, server_name)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()

@app.route("/", methods=["GET"])
def index():
    return "Quote Generator API v9 is Running!", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "version": "9",
        "styles": ["landscape", "portrait"],
        "features": ["emoji", "server-name", "black-bg-from-line"]
    })

@app.route("/quote", methods=["POST"])
def quote():
    try:
        data = request.get_json(force=True, silent=True) or {}
        text = (data.get("text") or "").strip()
        display_name = (data.get("display_name") or data.get("username") or "Unknown").strip()
        username = (data.get("username") or "unknown").strip()
        avatar_url = (data.get("avatar") or "").strip()
        style = (data.get("style") or "landscape").strip().lower()
        server_name = (data.get("server_name") or "").strip() or None
        if not text:
            return jsonify({"error": "text is required"}), 400
        if len(text) > 500:
            return jsonify({"error": "text too long (max 500 chars)"}), 400
        if style not in [STYLE_LANDSCAPE, STYLE_PORTRAIT]:
            style = STYLE_LANDSCAPE
        png_bytes = render_quote(text, display_name, username, avatar_url, style, server_name)
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
