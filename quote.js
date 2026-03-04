/**
 * /quote — Tạo ảnh trích dẫn Discord
 * API: Hugging Face Space (self-hosted, thay thế voids.top đã chết)
 * Pattern: execFile curl — giống mbwinrate.js (KataBump block Node https)
 */

'use strict';

const { SlashCommandBuilder, EmbedBuilder, AttachmentBuilder } = require('discord.js');
const { execFile } = require('child_process');
const fs           = require('fs');
const path         = require('path');
const os           = require('os');

const { gl }      = require('../utils');
const { getLang } = require('../db');

// ── Config ────────────────────────────────────────────────────────────────────
// Đổi URL này sau khi deploy HF Space
// Ví dụ: https://vy-lucyfer-quote-generator.hf.space
const HF_API_URL  = process.env.QUOTE_API_URL || 'https://lenhattruong165-quote-generator.hf.space';
const ENDPOINT    = `${HF_API_URL}/quote`;
const TIMEOUT_S   = 30;  // HF Space cold start có thể chậm
const COOLDOWN_MS = 5_000;

const cooldowns = new Map();

// BUG 4 FIX: Cleanup cooldowns Map định kỳ — tránh RAM leak
setInterval(() => {
  const now = Date.now();
  let cleaned = 0;
  for (const [uid, last] of cooldowns.entries()) {
    if (now - last >= COOLDOWN_MS) { cooldowns.delete(uid); cleaned++; }
  }
  if (cleaned > 0)
    console.log(`[quote] Cooldown cleanup: removed ${cleaned} stale entries`);
}, 10 * 60_000);

// ── curl helper ───────────────────────────────────────────────────────────────
/**
 * Gọi HF Space API bằng curl, nhận binary PNG về file tạm.
 * Trả về path file tạm hoặc throw Error.
 */
function curlPostPng(url, bodyObj, timeoutSec) {
  return new Promise((resolve, reject) => {
    const tmpFile = path.join(os.tmpdir(), `quote_${Date.now()}_${Math.random().toString(36).slice(2)}.png`);
    const body    = JSON.stringify(bodyObj);

    const args = [
      '-s',
      '-L',
      '--max-time', String(timeoutSec),
      '-X', 'POST',
      '-H', 'Content-Type: application/json',
      '-H', 'Accept: image/png',
      '--data-raw', body,
      '-o', tmpFile,
      '-w', '%{http_code}',
      '--compressed',
      url,
    ];

    execFile('curl', args, { maxBuffer: 512 * 1024 }, (err, stdout, stderr) => {
      if (err) {
        fs.unlink(tmpFile, () => {});
        return reject(new Error(`curl error: ${err.message}`));
      }

      const httpCode = (stdout || '').trim();

      if (httpCode === '200') {
        try {
          const stat = fs.statSync(tmpFile);
          if (stat.size < 100) {
            fs.unlink(tmpFile, () => {});
            return reject(new Error(`Empty response (file size: ${stat.size})`));
          }
          return resolve(tmpFile);
        } catch (e) {
          return reject(new Error(`Output file not found: ${e.message}`));
        }
      }

      fs.readFile(tmpFile, 'utf8', (readErr, content) => {
        fs.unlink(tmpFile, () => {});
        let msg = `HTTP ${httpCode}`;
        if (!readErr && content) {
          try {
            const parsed = JSON.parse(content);
            msg = parsed.error || msg;
          } catch {}
        }
        reject(new Error(msg));
      });
    });
  });
}

// ── Command ───────────────────────────────────────────────────────────────────
module.exports = {

  data: new SlashCommandBuilder()
    .setName('quote')
    .setDescription('Tạo ảnh trích dẫn giả lập Discord')
    .setIntegrationTypes([0, 1])
    .setContexts([0, 1, 2])
    .addStringOption(o =>
      o.setName('text')
        .setDescription('Nội dung trích dẫn')
        .setRequired(true)
        .setMaxLength(500)
    ),

  async execute(interaction) {
    const gId  = interaction.guildId;
    const lang = getLang(gId);
    const t    = gl(lang);

    // ── Cooldown ─────────────────────────────────────────────────────────────
    const uid  = interaction.user.id;
    const now  = Date.now();
    const last = cooldowns.get(uid) || 0;
    const diff = now - last;

    if (diff < COOLDOWN_MS) {
      const remaining = ((COOLDOWN_MS - diff) / 1000).toFixed(1);
      return interaction.reply({
        content:   t.quoteCooldown(remaining),
        ephemeral: true,
      });
    }
    cooldowns.set(uid, now);

    await interaction.deferReply();

    const text        = interaction.options.getString('text');
    const displayName = interaction.member?.displayName
                        ?? interaction.user.globalName
                        ?? interaction.user.username;
    const username    = interaction.user.username;
    const avatarUrl   = interaction.user.displayAvatarURL({ extension: 'png', size: 512 });

    let tmpFile = null;
    try {
      tmpFile = await curlPostPng(
        ENDPOINT,
        { text, display_name: displayName, username, avatar: avatarUrl },
        TIMEOUT_S
      );

      const attachment = new AttachmentBuilder(tmpFile, { name: 'quote.png' });
      await interaction.editReply({ files: [attachment] });

    } catch (err) {
      const errMsg      = err.message || String(err);
      const isColdStart = errMsg.includes('28') || errMsg.toLowerCase().includes('timeout');
      console.error(`[quote] execute error — ${errMsg}`, err);

      await interaction.editReply({
        embeds: [
          new EmbedBuilder()
            .setTitle(t.quoteErrTitle)
            .setDescription(
              isColdStart
                ? (lang === 'vi'
                    ? `${t.quoteErrDesc}\n\n⏳ *Máy chủ ảnh đang khởi động, thử lại sau 30 giây.*`
                    : `${t.quoteErrDesc}\n\n⏳ *Image server is warming up, try again in 30 seconds.*`)
                : `${t.quoteErrDesc}\n\n${t.quoteErrApi(errMsg)}`
            )
            .setColor(0xFF0000)
            .setTimestamp(),
        ],
      });

    } finally {
      if (tmpFile) fs.unlink(tmpFile, () => {});
    }
  },
};
