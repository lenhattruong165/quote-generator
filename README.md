---
title: Quote Image Generator
emoji: 💬
colorFrom: gray
colorTo: gray
sdk: docker
pinned: false
---

# Quote Image Generator

API for Chang'e Aspirant Bot — by vy-lucyfer

## Endpoint

**POST** `/quote`

```json
{
  "text": "nội dung quote",
  "display_name": "Tên hiển thị",
  "username": "username",
  "avatar": "https://cdn.discordapp.com/avatars/..."
}
```

Response: PNG binary (`image/png`)

**GET** `/health` → `{"status": "ok"}`