"""
Quote Image Generator API
Chang'e Aspirant Bot — by vy-lucyfer
Hugging Face Space: Python + Pillow + Flask

Layout:
  - Background: #000000
  - Avatar: chiếm ~42% trái, fade gradient sang phải
  - Text zone: 58% phải, căn giữa dọc
  - Font size: dynamic (fit vào text zone)
  - Emoji: render qua Pillow (NotoColorEmoji nếu có)
  - Output: PNG binary trả về thẳng
"""

import io
import os
import math
import textwrap
import urllib.request
import urllib.error
from flask import Flask, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
IMG_W       = 1200
IMG_H       = 630
AVATAR_W    = int(IMG_W * 0.42)   # 504px — vùng avatar
TEXT_X      = int(IMG_W * 0.46)   # 552px — bắt đầu text zone
TEXT_W      = IMG_W - TEXT_X - 40 # ~608px — chiều rộng text zone
FONT_MAX    = 64
FONT_MIN    = 20
FONT_STEP   = 2

# Màu
COLOR_BG        = (0, 0, 0, 255)
COLOR_TEXT      = (255, 255, 255, 255)
COLOR_USERNAME  = (136, 136, 136, 255)  # #888888
COLOR_NAME      = (220, 220, 220, 255)  # hơi xám nhẹ

# Font paths — HF Space có sẵn Noto fonts
FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    # Fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
FONT_ITALIC_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
]

def find_font(paths, size):
    """Tìm font đầu tiên có trong hệ thống."""
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

# ── Avatar fetch ───────────────────────────────────────────────────────────────
def fetch_avatar(url: str) -> Image.Image | None:
    """Fetch avatar từ URL, trả về RGBA Image hoặc None nếu lỗi."""
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ChangE-Bot/1.0 (quote-generator)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        return img
    except Exception as e:
        print(f"[avatar] fetch error: {e}")
        return None

# ── Gradient mask ──────────────────────────────────────────────────────────────
def make_fade_mask(width: int, height: int, fade_start: float = 0.55) -> Image.Image:
    """
    Tạo mask RGBA: trắng (opaque) bên trái → trong suốt bên phải.
    fade_start: tỉ lệ width bắt đầu fade (0.0–1.0)
    """
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    fade_px = int(width * fade_start)
    for x in range(width):
        if x <= fade_px:
            alpha = 255
        else:
            progress = (x - fade_px) / max(1, width - fade_px)
            # Ease-out curve
            alpha = int(255 * max(0.0, 1.0 - progress ** 0.6))
        draw.line([(x, 0), (x, height)], fill=alpha)
    return mask

# ── Dynamic font size ──────────────────────────────────────────────────────────
def fit_text(text: str, max_w: int, max_h: int, font_paths: list) -> tuple:
    """
    Tìm font size lớn nhất để text vừa trong (max_w × max_h).
    Trả về (font, lines, line_height, font_size).
    """
    for size in range(FONT_MAX, FONT_MIN - 1, -FONT_STEP):
        font = find_font(font_paths, size)
        # Wrap text theo chiều rộng
        # Ước tính số char mỗi dòng dựa trên average char width
        avg_char_w = size * 0.55
        chars_per_line = max(1, int(max_w / avg_char_w))
        wrapped = textwrap.fill(text, width=chars_per_line)
        lines = wrapped.split("\n")

        # Đo thực tế bằng dummy draw
        dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        line_heights = []
        line_widths  = []
        for line in lines:
            bbox = dummy.textbbox((0, 0), line, font=font)
            line_widths.append(bbox[2] - bbox[0])
            line_heights.append(bbox[3] - bbox[1])

        total_h    = sum(line_heights) + int(size * 0.35) * (len(lines) - 1)
        max_line_w = max(line_widths) if line_widths else 0

        if total_h <= max_h and max_line_w <= max_w:
            line_h = int(size * 1.35)
            return font, lines, line_h, size

    # fallback min size
    font  = find_font(font_paths, FONT_MIN)
    chars = max(1, int(max_w / (FONT_MIN * 0.55)))
    lines = textwrap.fill(text, width=chars).split("\n")
    return font, lines, int(FONT_MIN * 1.35), FONT_MIN

# ── Render quote image ─────────────────────────────────────────────────────────
def render_quote(
    text: str,
    display_name: str,
    username: str,
    avatar_url: str,
) -> bytes:
    """Render ảnh quote, trả về bytes PNG."""

    # 1. Canvas nền đen
    canvas = Image.new("RGBA", (IMG_W, IMG_H), COLOR_BG)

    # 2. Avatar
    avatar_img = fetch_avatar(avatar_url)
    if avatar_img:
        # Scale avatar fit chiều cao, giữ aspect ratio
        aw, ah = avatar_img.size
        scale  = IMG_H / ah
        new_aw = int(aw * scale)
        avatar_img = avatar_img.resize((new_aw, IMG_H), Image.LANCZOS)

        # Crop nếu quá rộng
        if new_aw > AVATAR_W + 60:
            avatar_img = avatar_img.crop((0, 0, AVATAR_W + 60, IMG_H))

        # Áp fade mask
        mask = make_fade_mask(avatar_img.width, IMG_H, fade_start=0.60)
        avatar_rgba = avatar_img.convert("RGBA")
        r, g, b, a = avatar_rgba.split()
        new_a = Image.composite(mask, Image.new("L", mask.size, 0), mask)
        avatar_rgba.putalpha(new_a)

        # Paste lên canvas
        canvas.paste(avatar_rgba, (0, 0), avatar_rgba)

    # 3. Draw text
    draw = ImageDraw.Draw(canvas)

    # Vùng text: từ TEXT_X đến cuối, với padding
    text_zone_w = TEXT_W
    text_zone_h = int(IMG_H * 0.55)  # 55% height cho quote chính
    text_zone_top = int(IMG_H * 0.12)

    # Dynamic font fit
    font, lines, line_h, font_size = fit_text(
        text, text_zone_w, text_zone_h, FONT_PATHS
    )

    # Tính tổng height của quote text
    total_text_h = line_h * len(lines)

    # Name + username fonts
    name_size     = max(FONT_MIN, int(font_size * 0.55))
    username_size = max(FONT_MIN - 2, int(font_size * 0.42))
    name_font     = find_font(FONT_ITALIC_PATHS, name_size)
    user_font     = find_font(FONT_PATHS, username_size)

    # Đo name/username
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    name_text  = f"— {display_name}"
    name_bbox  = dummy.textbbox((0, 0), name_text, font=name_font)
    name_h     = name_bbox[3] - name_bbox[1]
    user_text  = f"@{username}"
    user_bbox  = dummy.textbbox((0, 0), user_text, font=user_font)
    user_h     = user_bbox[3] - user_bbox[1]

    gap        = int(font_size * 0.5)   # gap giữa quote và name
    total_h    = total_text_h + gap + name_h + int(name_size * 0.3) + user_h

    # Căn giữa dọc toàn bộ text block
    start_y = (IMG_H - total_h) // 2

    # Vẽ từng dòng quote — căn giữa ngang trong text zone
    y = start_y
    for line in lines:
        bbox  = dummy.textbbox((0, 0), line, font=font)
        lw    = bbox[2] - bbox[0]
        x     = TEXT_X + (text_zone_w - lw) // 2
        draw.text((x, y), line, font=font, fill=COLOR_TEXT)
        y += line_h

    # Gap
    y += gap

    # Vẽ display_name (italic, căn giữa)
    name_bbox2 = dummy.textbbox((0, 0), name_text, font=name_font)
    name_w     = name_bbox2[2] - name_bbox2[0]
    name_x     = TEXT_X + (text_zone_w - name_w) // 2
    draw.text((name_x, y), name_text, font=name_font, fill=COLOR_NAME)
    y += name_h + int(name_size * 0.3)

    # Vẽ @username (xám, căn giữa)
    user_bbox2 = dummy.textbbox((0, 0), user_text, font=user_font)
    user_w     = user_bbox2[2] - user_bbox2[0]
    user_x     = TEXT_X + (text_zone_w - user_w) // 2
    draw.text((user_x, y), user_text, font=user_font, fill=COLOR_USERNAME)

    # 4. Convert sang RGB và export PNG
    out = canvas.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "quote-generator"})

@app.route("/quote", methods=["POST"])
def quote():
    """
    POST /quote
    Body JSON:
      text         : string (bắt buộc)
      display_name : string
      username     : string
      avatar       : string (URL)
    Response: PNG binary
    """
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
        return send_file(
            io.BytesIO(png_bytes),
            mimetype="image/png",
            as_attachment=False,
            download_name="quote.png"
        )

    except Exception as e:
        print(f"[quote] render error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
