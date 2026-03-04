"""
Quote Image Generator API v4
Chang'e Aspirant Bot — by vy-lucyfer

Fix v4: Fade NGANG THUẦN — linear gradient X, đều từ trên xuống dưới.
Không vignette, không top/bottom effect. Giống "Make it a Quote" chuẩn.
"""

import io
import os
import urllib.request
from flask import Flask, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

IMG_W = 1200
IMG_H = 630
AVATAR_MAX_W = int(IMG_W * 0.60)  # 720px — avatar tối đa
TEXT_X   = int(IMG_W * 0.52)      # 624px — text bắt đầu (overlap nhẹ với avatar)
TEXT_W   = IMG_W - TEXT_X - 40    # ~536px
TEXT_PAD = 15

FONT_MAX  = 62
FONT_MIN  = 18
FONT_STEP = 2

COLOR_BG       = (0,   0,   0,   255)
COLOR_TEXT     = (255, 255, 255, 255)
COLOR_NAME     = (230, 230, 230, 255)
COLOR_USERNAME = (110, 110, 110, 255)

FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
FONT_ITALIC_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
]

def find_font(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
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
        print(f"[avatar] {e}")
        return None

def make_horizontal_fade(width: int, height: int, fade_start: float = 0.65) -> Image.Image:
    """
    Mask NGANG THUẦN:
    - Từ x=0 đến x=fade_start*width: alpha=255 (hiện ảnh)
    - Từ fade_start đến cuối: fade tuyến tính → 0 (đen)
    - Mỗi cột X có cùng alpha từ trên xuống dưới (đường thẳng đứng đều)
    """
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    fade_px  = int(width * fade_start)
    fade_len = max(1, width - fade_px)
    for x in range(fade_px, width):
        p     = (x - fade_px) / fade_len
        # Curve nhẹ để fade mượt nhưng vẫn ngang đều
        alpha = int(255 * max(0.0, (1.0 - p) ** 1.5))
        # Vẽ cột dọc toàn bộ height với cùng alpha
        draw.line([(x, 0), (x, height)], fill=alpha)
    return mask

def smart_wrap(text: str, font, max_w: int, dummy) -> list:
    """Wrap với hard-cut cho text không có space."""
    words = text.split()
    if not words:
        return [text]
    lines   = []
    current = ""
    for word in words:
        while True:
            b = dummy.textbbox((0, 0), word, font=font)
            if b[2] - b[0] <= max_w:
                break
            cut_found = False
            for cut in range(len(word) - 1, 0, -1):
                b2 = dummy.textbbox((0, 0), word[:cut], font=font)
                if b2[2] - b2[0] <= max_w:
                    lines.append(word[:cut])
                    word = word[cut:]
                    cut_found = True
                    break
            if not cut_found:
                break
        test = (current + " " + word).strip() if current else word
        b    = dummy.textbbox((0, 0), test, font=font)
        if b[2] - b[0] <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]

def fit_text(text: str, max_w: int, max_h: int):
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in range(FONT_MAX, FONT_MIN - 1, -FONT_STEP):
        font   = find_font(FONT_PATHS, size)
        lines  = smart_wrap(text, font, max_w, dummy)
        line_h = int(size * 1.38)
        total_h = line_h * len(lines)
        max_lw  = 0
        for l in lines:
            b = dummy.textbbox((0, 0), l, font=font)
            max_lw = max(max_lw, b[2] - b[0])
        if total_h <= max_h and max_lw <= max_w:
            return font, lines, line_h, size
    font  = find_font(FONT_PATHS, FONT_MIN)
    lines = smart_wrap(text, font, max_w, dummy)
    return font, lines, int(FONT_MIN * 1.38), FONT_MIN

def render_quote(text: str, display_name: str, username: str, avatar_url: str) -> bytes:
    canvas = Image.new("RGBA", (IMG_W, IMG_H), COLOR_BG)

    # ── Avatar ────────────────────────────────────────────────────────────────
    av = fetch_avatar(avatar_url)
    if av:
        aw, ah = av.size
        # Scale fit chiều cao
        scale  = IMG_H / ah
        new_aw = int(aw * scale)
        av = av.resize((new_aw, IMG_H), Image.LANCZOS)

        # Crop về AVATAR_MAX_W
        paste_w = min(new_aw, AVATAR_MAX_W)
        av_crop = av.crop((0, 0, paste_w, IMG_H)).convert("RGBA")

        # Áp fade ngang thuần — mỗi cột X đều nhau từ trên xuống dưới
        mask = make_horizontal_fade(paste_w, IMG_H, fade_start=0.65)
        av_crop.putalpha(mask)
        canvas.paste(av_crop, (0, 0), av_crop)

    # ── Text ──────────────────────────────────────────────────────────────────
    font, lines, line_h, fs = fit_text(text, TEXT_W, int(IMG_H * 0.62))

    name_size = max(FONT_MIN, int(fs * 0.58))
    user_size = max(14,       int(fs * 0.44))
    name_font = find_font(FONT_ITALIC_PATHS, name_size)
    user_font = find_font(FONT_PATHS,        user_size)

    dummy     = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    name_text = f"- {display_name}"
    user_text = f"@{username}"

    nb     = dummy.textbbox((0, 0), name_text, font=name_font)
    name_h = nb[3] - nb[1]
    ub     = dummy.textbbox((0, 0), user_text, font=user_font)
    user_h = ub[3] - ub[1]

    gap      = int(fs * 0.55)
    name_gap = int(name_size * 0.28)
    total_h  = line_h * len(lines) + gap + name_h + name_gap + user_h
    start_y  = (IMG_H - total_h) // 2

    draw = ImageDraw.Draw(canvas)
    y    = start_y

    for line in lines:
        b  = dummy.textbbox((0, 0), line, font=font)
        lw = b[2] - b[0]
        x  = TEXT_X + TEXT_PAD + (TEXT_W - lw) // 2
        draw.text((x, y), line, font=font, fill=COLOR_TEXT)
        y += line_h

    y += gap
    nb2    = dummy.textbbox((0, 0), name_text, font=name_font)
    name_w = nb2[2] - nb2[0]
    draw.text((TEXT_X + TEXT_PAD + (TEXT_W - name_w) // 2, y),
              name_text, font=name_font, fill=COLOR_NAME)
    y += name_h + name_gap

    ub2    = dummy.textbbox((0, 0), user_text, font=user_font)
    user_w = ub2[2] - ub2[0]
    draw.text((TEXT_X + TEXT_PAD + (TEXT_W - user_w) // 2, y),
              user_text, font=user_font, fill=COLOR_USERNAME)

    out = canvas.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()

@app.route("/", methods=["GET"])
def index():
    return "Quote Generator API is Running!", 200
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "4"})

@app.route("/quote", methods=["POST"])
def quote():
    try:
        data         = request.get_json(force=True, silent=True) or {}
        text         = (data.get("text") or "").strip()
        display_name = (data.get("display_name") or data.get("username") or "Unknown").strip()
        username     = (data.get("username") or "unknown").strip()
        avatar_url   = (data.get("avatar") or "").strip()

        if not text:
            return jsonify({"error": "text is required"}), 400
        if len(text) > 500:
            return jsonify({"error": "text too long (max 500 chars)"}), 400

        png_bytes = render_quote(text, display_name, username, avatar_url)
        return send_file(io.BytesIO(png_bytes), mimetype="image/png",
                         as_attachment=False, download_name="quote.png")
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)), debug=False)